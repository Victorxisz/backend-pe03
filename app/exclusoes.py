"""Cascata durável: remoção atômica no Atlas e limpeza externa repetível.

A remoção dos documentos é uma única transação; os arquivos do provedor são
tratados depois, a partir de um diário durável em ``tbl_exclusoes_pendentes``.
Enquanto esse diário existir, a exclusão não está concluída e pode ser retomada
pelo mesmo DELETE. Isso é compensação retomável, não uma transação distribuída
entre MongoDB e Cloudinary.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable
from uuid import uuid4
import logging

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

import db
from app.avancos.midias import preparar_limpeza, remover_arquivo
from app.avancos.rascunhos_repository import RepositorioRascunhos
from app.dominio.comum import Relogio
from app.integracoes.armazenamento import ErroArmazenamento

COLECAO_PENDENCIAS = "tbl_exclusoes_pendentes"
TEMPO_BLOQUEIO = timedelta(minutes=5)

logger = logging.getLogger(__name__)


class ErroExclusao(Exception):
    """Falha já traduzida para o contrato HTTP das rotas de exclusão."""

    def __init__(self, mensagem, status, campos=(), *, codigo="EXCLUSAO_INVALIDA",
                 alvo=None, perda=None, pendencia=None, pendentes=None):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.codigo = codigo
        self.alvo = alvo
        self.perda = perda
        self.pendencia = pendencia
        self.pendentes = pendentes

    def corpo(self):
        from app.serializacao import serializar

        corpo = {"mensagem": str(self), "campos": self.campos, "codigo": self.codigo}
        for nome, valor in (("alvo", self.alvo), ("perda", self.perda),
                            ("pendentes", self.pendentes)):
            if valor is not None:
                corpo[nome] = serializar(valor)
        if self.pendencia is not None:
            # Identificador interno da pendência, para localizar a limpeza.
            corpo["pendencia"] = str(self.pendencia)
        return corpo


class ConflitoExclusao(Exception):
    """O conjunto mudou ou outra requisição já está excluindo o mesmo alvo."""


class ReferenciaOrfa(Exception):
    """Um registro fora do conjunto continuaria apontando para o que foi removido."""


class LimpezaPendente(Exception):
    """Os documentos saíram do banco, mas arquivos externos continuam pendentes."""

    def __init__(self, pendencia_id, pendentes):
        super().__init__("Exclusão registrada; a limpeza dos arquivos ainda não terminou")
        self.pendencia_id = pendencia_id
        self.pendentes = pendentes


class ExclusaoIndeterminada(Exception):
    """O commit pode ter ocorrido; nenhum arquivo é removido sem confirmação."""

    def __init__(self, pendencia_id):
        super().__init__("Não foi possível confirmar a exclusão; repita a requisição")
        self.pendencia_id = pendencia_id


@dataclass(frozen=True)
class Conjunto:
    """Tudo que a cascata remove, mapeado antes de qualquer escrita.

    ``remover`` e ``relistar`` recebem a sessão da transação. ``relistar``
    devolve as mídias do conjunto na visão transacional, para detectar uma
    mídia criada entre o mapeamento e a remoção.
    """

    alvo: dict
    perda: dict
    ids: tuple
    midias: tuple
    remover: Callable[[Any], None]
    relistar: Callable[[Any], list]


def menciona(valor, identificadores):
    """Procura um identificador, em ObjectId ou texto, a qualquer profundidade."""
    if isinstance(valor, dict):
        return any(menciona(item, identificadores) for item in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(menciona(item, identificadores) for item in valor)
    return isinstance(valor, (ObjectId, str)) and str(valor) in identificadores


class ServicoExclusoes:
    def __init__(self, banco=None, cliente=None, relogio=None, rascunhos=None):
        self.banco = banco if banco is not None else db.banco_dados
        self.cliente = cliente if cliente is not None else db.cliente_mongo
        self.relogio = relogio if relogio is not None else Relogio()
        self.rascunhos = rascunhos if rascunhos is not None else RepositorioRascunhos(banco=self.banco)

    @property
    def pendencias(self):
        return self.banco[COLECAO_PENDENCIAS]

    def pendencia_do_alvo(self, tipo, alvo_id):
        return self.pendencias.find_one({"alvo.tipo": tipo, "alvo.id": alvo_id})

    def excluir(self, conjunto):
        """Remove o conjunto e trata os arquivos; retorna apenas se tudo terminou."""
        # Valida o lote inteiro antes da primeira escrita: uma referência
        # inválida não deve deixar metade do conjunto removido.
        arquivos = preparar_limpeza(conjunto.midias)
        agora = self.relogio.agora()
        token = uuid4().hex
        pendencia = {
            "_id": ObjectId(),
            "alvo": dict(conjunto.alvo),
            "perda": dict(conjunto.perda),
            "arquivos": arquivos,
            "pendentes": list(arquivos),
            "iniciada_em": agora,
            "token": token,
            "ate": agora + TEMPO_BLOQUEIO,
            "tentativas": 1,
        }
        esperadas = {str(midia["_id"]) for midia in conjunto.midias}

        def gravar(sessao):
            atuais = {str(midia["_id"]) for midia in conjunto.relistar(sessao)}
            if atuais != esperadas:
                raise ConflitoExclusao("As mídias do conjunto mudaram durante a exclusão")
            self.pendencias.insert_one(dict(pendencia), session=sessao)
            conjunto.remover(sessao)
            self._exigir_sem_orfaos(conjunto, sessao)

        confirmado = False
        try:
            with self.cliente.start_session() as sessao:
                sessao.with_transaction(gravar)
                confirmado = True
        except PyMongoError as erro:
            if not confirmado and erro.has_error_label("UnknownTransactionCommitResult"):
                logger.error(
                    "Exclusão com commit indeterminado; pendência %s do %s %s",
                    pendencia["_id"], conjunto.alvo["tipo"], conjunto.alvo["id"],
                )
                raise ExclusaoIndeterminada(pendencia["_id"]) from None
            if not confirmado:
                raise
            logger.warning("Exclusão confirmada; falha ao encerrar a sessão do MongoDB")
        self._limpar(pendencia["_id"], token)

    def retomar(self, tipo, alvo_id):
        """Continua a limpeza externa de um alvo que já saiu do banco."""
        agora = self.relogio.agora()
        token = uuid4().hex
        pendencia = self.pendencias.find_one_and_update(
            {"alvo.tipo": tipo, "alvo.id": alvo_id,
             "$or": [{"token": None}, {"ate": {"$lte": agora}}]},
            {"$set": {"token": token, "ate": agora + TEMPO_BLOQUEIO},
             "$inc": {"tentativas": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if pendencia is None:
            if self.pendencia_do_alvo(tipo, alvo_id) is None:
                return False
            raise ConflitoExclusao("Uma limpeza do mesmo alvo está em andamento")
        self._limpar(pendencia["_id"], token)
        return True

    def _exigir_sem_orfaos(self, conjunto, sessao):
        """Nenhum documento restante pode citar o que acabou de ser removido.

        A varredura roda depois da remoção e dentro da transação: o que sobrou
        é exatamente o lado de fora do conjunto, inclusive os vínculos que a
        cascata reescreve em vez de apagar. Para o volume do MVP a busca
        conservadora percorre as coleções; um volume maior exigirá um índice de
        referências. O diário da exclusão guarda os identificadores de propósito.
        """
        identificadores = {str(valor) for valor in conjunto.ids}
        for nome in self.banco.list_collection_names():
            if nome == COLECAO_PENDENCIAS:
                continue
            for documento in self.banco[nome].find({}, session=sessao):
                if menciona(documento, identificadores):
                    raise ReferenciaOrfa("Um registro fora do conjunto ainda aponta para o alvo")

    def _operacao(self, pendencia_id, token):
        return {"_id": pendencia_id, "token": token}

    def _renovar(self, pendencia_id, token):
        return self.pendencias.update_one(
            self._operacao(pendencia_id, token),
            {"$set": {"ate": self.relogio.agora() + TEMPO_BLOQUEIO}},
        ).matched_count == 1

    def _concluir_arquivo(self, pendencia_id, token, chave):
        return self.pendencias.update_one(
            self._operacao(pendencia_id, token),
            {"$pull": {"pendentes": {"chave": chave}}},
        ).matched_count == 1

    def _registrar_falha(self, pendencia_id, token):
        self.pendencias.update_one(
            self._operacao(pendencia_id, token),
            {"$set": {"ultima_falha_em": self.relogio.agora(),
                      "ultimo_erro": "Não foi possível remover um arquivo no provedor"}},
        )

    def _liberar(self, pendencia_id, token):
        self.pendencias.update_one(
            self._operacao(pendencia_id, token),
            {"$set": {"token": None, "ate": None}},
        )

    def _limpar(self, pendencia_id, token):
        retomada = "A limpeza foi retomada por outra requisição"
        concluido = False
        try:
            pendencia = self.pendencias.find_one(self._operacao(pendencia_id, token))
            if pendencia is None:
                raise ConflitoExclusao(retomada)
            for arquivo in list(pendencia["pendentes"]):
                if not self._renovar(pendencia_id, token):
                    raise ConflitoExclusao(retomada)
                if not self.rascunhos.referencia_em_uso(
                    arquivo["referencia"], ids_midias=arquivo["midia_ids"]
                ):
                    try:
                        remover_arquivo(arquivo["referencia"])
                    except (ErroArmazenamento, ValueError):
                        # Mensagem neutra: nada do provedor chega ao cliente.
                        self._registrar_falha(pendencia_id, token)
                        continue
                if not self._concluir_arquivo(pendencia_id, token, arquivo["chave"]):
                    raise ConflitoExclusao(retomada)
            atual = self.pendencias.find_one(self._operacao(pendencia_id, token))
            if atual is None:
                raise ConflitoExclusao(retomada)
            if atual["pendentes"]:
                raise LimpezaPendente(pendencia_id, len(atual["pendentes"]))
            removida = self.pendencias.delete_one(
                {**self._operacao(pendencia_id, token), "pendentes": {"$size": 0}}
            ).deleted_count == 1
            if not removida:
                raise ConflitoExclusao(retomada)
            concluido = True
        finally:
            if not concluido:
                self._liberar(pendencia_id, token)


def exigir_confirmacao(dados, alvo, perda):
    """RN-09: a tela mostra nome e perda; o servidor ainda exige o campo.

    O corpo recusado devolve alvo e perda para que a interface possa montar o
    aviso a partir da própria resposta, sem que cancelar envie outro DELETE.
    """
    if (not isinstance(dados, dict) or set(dados) != {"confirmar"}
            or dados["confirmar"] is not True):
        raise ErroExclusao(
            "Confirme a exclusão definitiva enviando somente {\"confirmar\": true}",
            422, ["confirmar"], codigo="CONFIRMACAO_OBRIGATORIA",
            alvo=alvo, perda=perda,
        )


def resumo_dos_avancos(avancos):
    """Contagens que descrevem a perda dos avanços e do que vive neles."""
    return {
        "avancos": len(avancos),
        "publicacoes": sum(1 for avanco in avancos if "publicacao" in avanco),
        "versoes": sum(len(avanco.get("correcoes", [])) for avanco in avancos),
        "exemplos_simulados": sum(1 for avanco in avancos if "origem_simulada" in avanco),
    }


def resumo_das_ocorrencias(ocorrencias):
    return {
        "ocorrencias": len(ocorrencias),
        "aceitacoes": sum(len(item.get("aceitacoes", [])) for item in ocorrencias),
    }


def _traduzir(acao):
    """Converte as falhas do mecanismo no contrato visível das rotas."""
    from app.avancos.midias import ErroMidia

    try:
        return acao()
    except ErroMidia as erro:
        raise ErroExclusao(str(erro), erro.status, erro.campos, codigo=erro.codigo) from erro
    except ConflitoExclusao as erro:
        raise ErroExclusao(str(erro), 409, codigo="CONFLITO_EXCLUSAO") from erro
    except ReferenciaOrfa as erro:
        raise ErroExclusao(str(erro), 409, codigo="REFERENCIA_EXTERNA") from erro
    except LimpezaPendente as erro:
        raise ErroExclusao(
            "Exclusão registrada; repita a requisição para retomar a limpeza dos arquivos",
            503, ["midias"], codigo="LIMPEZA_PENDENTE",
            pendencia=erro.pendencia_id, pendentes=erro.pendentes,
        ) from erro
    except ExclusaoIndeterminada as erro:
        raise ErroExclusao(
            str(erro), 503, codigo="EXCLUSAO_INDETERMINADA", pendencia=erro.pendencia_id,
        ) from erro


_servico = ServicoExclusoes()


def aplicar(conjunto, servico=None):
    """Executa a cascata; só retorna quando banco e provedor estão limpos."""
    mecanismo = servico if servico is not None else _servico
    _traduzir(lambda: mecanismo.excluir(conjunto))


def retomar_pendencia(tipo, alvo_id, servico=None):
    """Repetir o DELETE continua a limpeza de um alvo já fora do banco."""
    mecanismo = servico if servico is not None else _servico
    return _traduzir(lambda: mecanismo.retomar(tipo, alvo_id))
