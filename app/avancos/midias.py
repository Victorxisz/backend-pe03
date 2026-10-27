"""Mídias de avanço: metadados, vínculo com o avanço e acesso ao arquivo.

O provedor de armazenamento fica atrás de uma porta do servidor, com as
operações enviar, obter_acesso e remover, para que a escolha do serviço externo
não entre nas regras de publicação. Enquanto nenhum provedor for aprovado, a
única implementação é ArmazenamentoLocal; o adaptador de um serviço externo
entra em app/integracoes/ sem mudar rotas nem regras.

Nada do provedor é devolvido ao navegador: a referência externa, o nome do
provedor e suas credenciais ficam no servidor. O React recebe apenas rotas
próprias do Flask, que exigem sessão em cada leitura.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, has_app_context

from . import repository


# Tipos aceitos e os formatos que cada um pode devolver ao navegador.
TIPOS = {
    "foto": ("image/jpeg", "image/png", "image/webp"),
    "video": ("video/mp4", "video/webm"),
    "documento": ("application/pdf",),
}

# Campos que podem sair do servidor. Lista fechada: um campo novo com endereço
# ou credencial do provedor não vaza por esquecimento.
PUBLICOS = ("tipo", "nome", "tamanho", "formato", "visibilidade")

PROVEDOR_PADRAO = "local"
DIRETORIO_PADRAO = Path(__file__).resolve().parents[2] / "var" / "midias"

# Um endereço do provedor só é repassado se expirar logo; endereço permanente
# seria um atalho em volta da sessão da construtora.
VALIDADE_MAXIMA = timedelta(minutes=10)


class ErroMidia(Exception):
    """Falha com resposta HTTP definida; o código é estável para o React."""

    def __init__(self, mensagem, status, codigo, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.campos = list(campos)


class FalhaDoProvedor(Exception):
    """Falha ao falar com o armazenamento, distinta de mídia inexistente."""


class ConteudoAusenteNoProvedor(FalhaDoProvedor):
    """O provedor respondeu que o objeto referenciado não existe."""


class ProvedorIndisponivel(FalhaDoProvedor):
    """Indisponibilidade, cota ou limite do provedor."""


class Acesso:
    """Resultado de obter_acesso: bytes para o Flask servir ou URL efêmera."""

    def __init__(self, conteudo=None, url_temporaria=None, expira_em=None):
        self.conteudo = conteudo
        self.url_temporaria = url_temporaria
        self.expira_em = expira_em


class ArmazenamentoLocal:
    """Única implementação da primeira versão: arquivos no disco do servidor."""

    nome = "local"

    def __init__(self, raiz):
        self.raiz = Path(raiz).resolve()

    def _caminho(self, referencia):
        # A referência é opaca e gerada aqui; ainda assim nenhum valor gravado
        # pode apontar para fora da raiz do armazenamento.
        caminho = (self.raiz / str(referencia)).resolve()
        if caminho.parent != self.raiz:
            raise ProvedorIndisponivel("Referência fora do armazenamento")
        return caminho

    def enviar(self, conteudo, nome=None, formato=None):
        referencia = uuid4().hex
        caminho = self._caminho(referencia)
        try:
            self.raiz.mkdir(parents=True, exist_ok=True)
            # Grava e só então renomeia: o objeto nunca é visto pela metade.
            parcial = caminho.with_name(caminho.name + ".parcial")
            parcial.write_bytes(conteudo)
            parcial.replace(caminho)
        except OSError:
            raise ProvedorIndisponivel("Não foi possível gravar a mídia")
        return referencia

    def obter_acesso(self, referencia):
        caminho = self._caminho(referencia)
        try:
            return Acesso(conteudo=caminho.read_bytes())
        except FileNotFoundError:
            raise ConteudoAusenteNoProvedor("Objeto ausente no armazenamento")
        except OSError:
            raise ProvedorIndisponivel("Não foi possível ler a mídia")

    def remover(self, referencia):
        caminho = self._caminho(referencia)
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            raise ProvedorIndisponivel("Não foi possível remover a mídia")


def _configuracao(chave, padrao):
    # Configuração vem do ambiente; nenhum valor de provedor fica no código.
    if has_app_context() and current_app.config.get(chave):
        return current_app.config[chave]
    return os.getenv(chave) or padrao


def armazenamento():
    """Instancia o provedor configurado em MIDIA_PROVEDOR."""
    provedor = _configuracao("MIDIA_PROVEDOR", PROVEDOR_PADRAO)
    if provedor != PROVEDOR_PADRAO:
        # Falha controlada: um provedor sem adaptador não pode parecer ausência
        # de mídia nem derrubar a requisição com detalhe interno.
        raise ErroMidia(
            "O armazenamento de mídias não está configurado neste servidor",
            502,
            "PROVEDOR_NAO_CONFIGURADO",
        )
    return ArmazenamentoLocal(_configuracao("MIDIA_DIRETORIO", DIRETORIO_PADRAO))


def _identificador(valor, campo, recurso):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroMidia("ID " + recurso + " inválido", 400, "ID_INVALIDO", [campo])


def midia_para_dict(documento):
    """Representação pública da mídia, sem referência nem nome do provedor."""
    midia = {campo: documento.get(campo) for campo in PUBLICOS}
    midia["id"] = str(documento["_id"])
    midia["avanco_id"] = str(documento.get("avanco_id"))
    envio = documento.get("data_envio")
    if isinstance(envio, datetime):
        # O PyMongo pode devolver UTC sem tzinfo; a API sempre informa o fuso.
        if envio.tzinfo is None:
            envio = envio.replace(tzinfo=timezone.utc)
        midia["data_envio"] = envio.isoformat()
    return midia


def formato_para_resposta(documento):
    """Devolve o Content-Type permitido e se o arquivo pode abrir embutido.

    O valor gravado nunca vai cru ao cabeçalho: um formato fora da lista é
    entregue como binário para download, não como página interpretável.
    """
    formato = documento.get("formato")
    if formato in TIPOS.get(documento.get("tipo"), ()):
        return formato, documento.get("tipo") in ("foto", "video")
    return "application/octet-stream", False


def nome_para_resposta(documento):
    nome = documento.get("nome")
    if isinstance(nome, str) and nome.strip():
        return nome
    return str(documento["_id"])


def listar_midias(avanco_id):
    """Mídias de um avanço, rascunho ou publicado, para a própria construtora."""
    identificador = _identificador(avanco_id, "avanco_id", "do avanço")
    # Avanço inexistente é 404; avanço sem mídia é lista vazia.
    if not repository.avanco_existe(identificador):
        raise ErroMidia(
            "Avanço não encontrado", 404, "AVANCO_NAO_ENCONTRADO", ["avanco_id"]
        )
    return [
        midia_para_dict(documento)
        for documento in repository.consultar_midias(identificador)
    ]


def _midia_vinculada(midia_id):
    identificador = _identificador(midia_id, "midia_id", "da mídia")
    documento = repository.buscar_midia_por_id(identificador)
    nao_encontrada = ErroMidia(
        "Mídia não encontrada", 404, "MIDIA_NAO_ENCONTRADA", ["midia_id"]
    )
    if documento is None:
        raise nao_encontrada
    # Mídia sem avanço vivo é referência órfã, não conteúdo acessível.
    vinculo = documento.get("avanco_id")
    if not isinstance(vinculo, ObjectId) or not repository.avanco_existe(vinculo):
        raise nao_encontrada
    return documento


def buscar_midia(midia_id):
    return midia_para_dict(_midia_vinculada(midia_id))


def abrir_conteudo(midia_id):
    """Devolve o documento e o acesso ao arquivo, já validado o vínculo.

    Falha do provedor não é convertida em mídia inexistente: quem consulta
    precisa distinguir registro ausente de armazenamento inacessível.
    """
    documento = _midia_vinculada(midia_id)
    referencia = documento.get("referencia_externa")
    ausente = ErroMidia(
        "O arquivo desta mídia não está disponível no armazenamento",
        502,
        "CONTEUDO_AUSENTE_NO_PROVEDOR",
        ["midia_id"],
    )
    if not isinstance(referencia, str) or not referencia:
        raise ausente

    try:
        acesso = armazenamento().obter_acesso(referencia)
    except ConteudoAusenteNoProvedor:
        raise ausente
    except FalhaDoProvedor:
        # A mensagem do provedor pode conter rota interna ou credencial.
        raise ErroMidia(
            "Não foi possível acessar o armazenamento de mídias agora",
            502,
            "PROVEDOR_INDISPONIVEL",
            ["midia_id"],
        )

    if acesso.conteudo is None and not acesso.url_temporaria:
        raise ausente
    if acesso.url_temporaria:
        _exigir_validade_curta(acesso.expira_em)
    return documento, acesso


def _exigir_validade_curta(expira_em):
    agora = datetime.now(timezone.utc)
    valido = (
        isinstance(expira_em, datetime)
        and expira_em.tzinfo is not None
        and agora < expira_em <= agora + VALIDADE_MAXIMA
    )
    if not valido:
        raise ErroMidia(
            "O armazenamento devolveu um endereço sem validade curta; "
            "o acesso foi recusado",
            502,
            "ACESSO_TEMPORARIO_INVALIDO",
            ["midia_id"],
        )
