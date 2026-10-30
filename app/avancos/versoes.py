"""Reconstrução e comparação da cadeia de versões de um avanço publicado.

UC-11/RN-06: uma correção não apaga o conteúdo anterior. Cada entrada de
``correcoes`` guarda o conteúdo completo que existia antes dela, além do motivo,
do autor e do instante; o conteúdo corrigido permanece em ``publicacao``. A
sequência de versões é, portanto, a lista dos conteúdos anteriores seguida do
atual, e os campos alterados são calculados a partir desses conteúdos, nunca de
um resumo gravado que poderia divergir deles.

Forma esperada de cada correção::

    {"autor": "<id da construtora>", "instante": datetime, "motivo": "texto",
     "anterior": {"data": ..., "descricao": ..., "marco": {...}, "midias": [...]}}
"""

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from bson import ObjectId
from bson.errors import InvalidId

from . import repository


# Campos corrigíveis de uma publicação, na ordem usada para relatar alterações.
CAMPOS_CONTEUDO = ("data", "descricao", "midias")
# Lista fechada: a referência externa e suas credenciais nunca são devolvidas.
CAMPOS_MIDIA = ("id", "tipo", "nome", "mime", "tamanho")
PALAVRAS = re.compile(r"\s+|\S+")


class ErroVersoes(Exception):
    def __init__(self, mensagem, status=404, codigo="AVANCO_NAO_ENCONTRADO", campos=None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.campos = ["avanco_id"] if campos is None else list(campos)


def _identificador(valor):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroVersoes("ID inválido", 400, "ID_INVALIDO") from None


def _instante(valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.isoformat()
    return valor if isinstance(valor, str) else None


def diferenca_texto(anterior, posterior):
    """Trechos consecutivos marcados como ``igual``, ``removido`` ou ``inserido``.

    Concatenar ``igual`` com ``removido`` reproduz o texto anterior; concatenar
    ``igual`` com ``inserido`` reproduz o posterior. A interface destaca os
    trechos alterados sem repetir o cálculo.
    """
    antes = PALAVRAS.findall(anterior if isinstance(anterior, str) else "")
    depois = PALAVRAS.findall(posterior if isinstance(posterior, str) else "")
    trechos = []
    comparador = SequenceMatcher(None, antes, depois, autojunk=False)
    for operacao, inicio, fim, inicio_novo, fim_novo in comparador.get_opcodes():
        if operacao == "equal":
            trechos.append(("igual", antes[inicio:fim]))
            continue
        if inicio != fim:
            trechos.append(("removido", antes[inicio:fim]))
        if inicio_novo != fim_novo:
            trechos.append(("inserido", depois[inicio_novo:fim_novo]))
    return [{"operacao": operacao, "texto": "".join(tokens)} for operacao, tokens in trechos]


def _midia(bruto, disponiveis):
    midia = {campo: bruto.get(campo) for campo in CAMPOS_MIDIA}
    identificador = midia["id"]
    if isinstance(identificador, ObjectId):
        identificador = str(identificador)
        midia["id"] = identificador
    # Política de retenção: os metadados da versão anterior continuam
    # rastreáveis mesmo quando o arquivo já não está no acervo.
    disponivel = isinstance(identificador, str) and identificador in disponiveis
    midia["disponivel"] = disponivel
    midia["conteudo"] = f"/midias/{identificador}/conteudo" if disponivel else None
    midia["data_envio"] = _instante(bruto.get("data_envio"))
    return midia


def _conteudo(bruto, disponiveis):
    marco = bruto.get("marco")
    if isinstance(marco, dict) and marco.get("id") is not None:
        marco = {"id": str(marco["id"]), "nome": marco.get("nome")}
    else:
        marco = None
    midias = bruto.get("midias")
    return {
        "data": bruto.get("data"),
        "descricao": bruto.get("descricao"),
        "marco": marco,
        "midias": [_midia(item, disponiveis) for item in midias or [] if isinstance(item, dict)],
    }


def _diferencas(anterior, posterior):
    diferencas = {}
    for campo in ("data", "descricao"):
        if anterior[campo] == posterior[campo]:
            continue
        diferencas[campo] = {
            "tipo": "texto",
            "anterior": anterior[campo],
            "posterior": posterior[campo],
            "trechos": diferenca_texto(anterior[campo], posterior[campo]),
        }
    antes = [midia["id"] for midia in anterior["midias"]]
    depois = [midia["id"] for midia in posterior["midias"]]
    # Corrigir uma mídia gera outro envio e outro identificador; comparar os
    # identificadores detecta substituição, inclusão, remoção e reordenação.
    if antes != depois:
        diferencas["midias"] = {
            "tipo": "midias",
            "removidas": [midia for midia in anterior["midias"] if midia["id"] not in depois],
            "adicionadas": [midia for midia in posterior["midias"] if midia["id"] not in antes],
            "mantidas": [identificador for identificador in depois if identificador in antes],
        }
    return diferencas


def _correcao(registro, anterior, posterior):
    diferencas = _diferencas(anterior, posterior)
    autor = registro.get("autor")
    return {
        "motivo": registro.get("motivo"),
        "autor": str(autor) if autor is not None else None,
        "instante": _instante(registro.get("instante")),
        "campos": [campo for campo in CAMPOS_CONTEUDO if campo in diferencas],
        "anterior": anterior,
        "posterior": posterior,
        "diferencas": diferencas,
    }


def _correcoes(documento):
    registros = documento.get("correcoes", [])
    if not isinstance(registros, list) or any(
        not isinstance(registro, dict) or not isinstance(registro.get("anterior"), dict)
        for registro in registros
    ):
        # Sem o conteúdo anterior completo a cadeia não pode ser reconstruída, e
        # devolver uma sequência incompleta afirmaria um histórico que não houve.
        raise ErroVersoes("Cadeia de versões inconsistente", 500, "VERSOES_INCONSISTENTES")
    # A lista só é acrescida a cada correção, então sua ordem é a cronológica.
    return registros


def _disponiveis(brutos):
    identificadores = set()
    for bruto in brutos:
        for midia in bruto.get("midias") or []:
            if not isinstance(midia, dict):
                continue
            try:
                identificadores.add(ObjectId(midia.get("id")))
            except (InvalidId, TypeError):
                continue
    return {str(encontrada) for encontrada in repository.midias_existentes(identificadores)}


def _origem_simulada(documento, publicacao):
    for origem in (documento.get("origem"), publicacao.get("origem")):
        if isinstance(origem, dict) and origem.get("simulado"):
            # RN-10: o exemplo pré-carregado é sinalizado como simulação e não
            # transforma o engenheiro em usuário real do sistema.
            return {"simulado": True, "perfil": origem.get("perfil") or "engenheiro",
                    "nome": origem.get("nome")}
    return None


def consultar_versoes(avanco_id):
    documento = repository.buscar_avanco(_identificador(avanco_id))
    if documento is None:
        raise ErroVersoes("Avanço não encontrado")
    publicacao = documento.get("publicacao")
    if documento.get("estado") != "publicado" or not isinstance(publicacao, dict):
        # O avanço existe, mas ainda não há publicação a versionar.
        return {"avanco_id": str(documento["_id"]), "estado": documento.get("estado"),
                "versao_atual": None, "total_versoes": 0, "autoria": None, "versoes": []}
    correcoes = _correcoes(documento)
    brutos = [registro["anterior"] for registro in correcoes] + [publicacao]
    disponiveis = _disponiveis(brutos)
    conteudos = [_conteudo(bruto, disponiveis) for bruto in brutos]
    versoes = []
    for indice, conteudo in enumerate(conteudos):
        versoes.append({
            "versao": indice + 1,
            "atual": indice == len(conteudos) - 1,
            "conteudo": conteudo,
            "correcao": None if indice == 0 else _correcao(
                correcoes[indice - 1], conteudos[indice - 1], conteudo),
        })
    simulada = _origem_simulada(documento, publicacao)
    autor = publicacao.get("autor")
    return {
        "avanco_id": str(documento["_id"]),
        "estado": "publicado",
        "versao_atual": len(conteudos),
        "total_versoes": len(conteudos),
        "autoria": {
            "original": {
                "autor": str(autor) if autor is not None else None,
                "perfil": simulada["perfil"] if simulada else "construtora",
                "instante": _instante(publicacao.get("instante")),
                "simulado": simulada is not None,
            },
            "origem_simulada": simulada,
            "correcoes": [
                {"versao": versao["versao"], "autor": versao["correcao"]["autor"],
                 "instante": versao["correcao"]["instante"],
                 "motivo": versao["correcao"]["motivo"], "perfil": "construtora"}
                for versao in versoes if versao["correcao"]
            ],
            "editado_pela_construtora": bool(correcoes),
        },
        "versoes": versoes,
    }
