"""Leitura de versões de publicações e diferenças estruturadas."""

from datetime import datetime, timezone
from difflib import SequenceMatcher

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .service import ErroAvanco


def _instante(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor).isoformat()
    return valor


def _conteudo(valor):
    # Apenas metadados públicos; nunca devolve referências do provedor.
    campos = ("id", "avanco_id", "tipo", "nome", "tamanho", "mime", "formato", "visibilidade", "data_envio", "conteudo")
    midias = [{chave: _instante(item[chave]) for chave in campos if chave in item}
              for item in valor.get("midias", [])]
    return {"data": valor["data"], "descricao": valor["descricao"], "midias": midias}


def _diferencas(antes, depois):
    return [{"tipo": {"equal": "igual", "insert": "inserido", "delete": "removido", "replace": "substituido"}[op],
             "antes": antes[i:j], "depois": depois[k:l]}
            for op, i, j, k, l in SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes()]


def _indisponivel():
    raise ErroAvanco("Histórico de correções indisponível ou inconsistente", 409,
                     ["versoes"], codigo="HISTORICO_INDISPONIVEL")


def consultar_versoes(avanco_id):
    try:
        identificador = ObjectId(avanco_id)
    except (InvalidId, TypeError):
        raise ErroAvanco("Identificador inválido", 400, ["avanco_id"]) from None
    documento = repository.buscar_avanco(identificador)
    if documento is None or documento.get("estado") == "exclusao_pendente":
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    if documento.get("estado") != "publicado" or not documento.get("publicacao"):
        return {"avanco_id": str(identificador), "versoes": []}
    fato = documento["publicacao"]
    try:
        original = _conteudo(fato)
        correcoes = documento.get("correcoes", [])
        if not isinstance(correcoes, list):
            _indisponivel()
        versoes = [{"numero": 1, "atual": False, "conteudo": original,
                    "autor_original": documento.get("autor"), "origem_simulada": documento.get("origem_simulada"),
                    "correcao": None}]
        anterior = original
        for indice, correcao in enumerate(correcoes, 2):
            antes = _conteudo(correcao["antes"])
            depois = _conteudo(correcao["depois"])
            if antes != anterior or not correcao["motivo"] or not correcao["autor"] or not correcao["instante"]:
                _indisponivel()
            campos = [campo for campo in ("data", "descricao", "midias") if antes[campo] != depois[campo]]
            if not campos:
                _indisponivel()
            versoes.append({"numero": indice, "atual": False, "conteudo": depois,
                            "autor_original": documento.get("autor"), "origem_simulada": documento.get("origem_simulada"),
                            "correcao": {"antes": antes, "depois": depois, "campos": campos,
                                         "motivo": correcao["motivo"], "autor": correcao["autor"],
                                         "instante": _instante(correcao["instante"]),
                                         "diferencas_texto": _diferencas(antes["descricao"], depois["descricao"])}})
            anterior = depois
        atual = _conteudo({"data": documento.get("data", fato["data"]),
                           "descricao": documento.get("descricao", fato["descricao"]),
                           "midias": documento.get("midias", fato.get("midias", []))})
        if atual != anterior or (documento.get("editado") is True and not correcoes):
            _indisponivel()
        versoes[-1]["atual"] = True
    except (KeyError, TypeError, AttributeError):
        _indisponivel()
    return {"avanco_id": str(identificador), "versoes": versoes}
