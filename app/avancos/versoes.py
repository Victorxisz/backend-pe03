"""Leitura de versões de publicações e diferenças estruturadas."""

from datetime import datetime, timezone
from difflib import SequenceMatcher

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .service import ErroAvanco
from app.serializacao import serializar


def _instante(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor).isoformat()
    return valor


def _conteudo(valor):
    # Esta forma canônica também é usada na escrita. Disponibilidade de mídia
    # fica só na resposta HTTP: uma remoção não pode mudar o snapshot histórico.
    if (not isinstance(valor, dict) or not isinstance(valor.get("data"), str)
            or not isinstance(valor.get("descricao"), str)
            or not isinstance(valor.get("midias", []), list)
            or any(not isinstance(item, dict)
                   or ("id" in item and not isinstance(item["id"], (str, ObjectId)))
                   for item in valor.get("midias", []))):
        _indisponivel()
    campos = ("id", "avanco_id", "tipo", "nome", "tamanho", "mime", "formato", "visibilidade", "data_envio", "conteudo")
    midias = [{chave: serializar(item[chave]) for chave in campos if chave in item}
              for item in valor.get("midias", [])]
    return {"data": valor["data"], "descricao": valor["descricao"], "midias": midias}


def _diferencas(antes, depois):
    return [{"tipo": {"equal": "igual", "insert": "inserido", "delete": "removido", "replace": "substituido"}[op],
             "antes": antes[i:j], "depois": depois[k:l]}
            for op, i, j, k, l in SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes()]


def _indisponivel():
    raise ErroAvanco("Histórico de correções indisponível ou inconsistente", 409,
                     ["versoes"], codigo="HISTORICO_INDISPONIVEL")


def reconstruir_versoes(documento):
    """Reconstrói uma única leitura do avanço, sem consultar ou alterar o banco."""
    if documento is None or documento.get("estado") == "exclusao_pendente":
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    identificador = documento["_id"]
    if documento.get("estado") != "publicado":
        return {"avanco_id": str(identificador), "versoes": []}
    if not isinstance(documento.get("publicacao"), dict) or not documento["publicacao"]:
        _indisponivel()
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
            if (antes != anterior or not isinstance(correcao["motivo"], str)
                    or not correcao["motivo"].strip()
                    or not isinstance(correcao["autor"], (str, ObjectId)) or not str(correcao["autor"]).strip()
                    or not isinstance(correcao["instante"], (datetime, str)) or not correcao["instante"]):
                _indisponivel()
            campos = [campo for campo in ("data", "descricao", "midias") if antes[campo] != depois[campo]]
            if not campos:
                _indisponivel()
            if "campos" in correcao and correcao["campos"] != campos:
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
    return serializar({"avanco_id": str(identificador), "versoes": versoes})


def consultar_versoes(avanco_id):
    try:
        if not isinstance(avanco_id, (str, ObjectId)):
            raise TypeError
        identificador = ObjectId(avanco_id)
    except (InvalidId, TypeError):
        raise ErroAvanco("Identificador inválido", 400, ["avanco_id"]) from None
    resultado = reconstruir_versoes(repository.buscar_avanco(identificador))
    # Uma só consulta do acervo; não consulta o provedor nem regrava snapshots.
    midias = []
    for versao in resultado["versoes"]:
        midias.extend(versao["conteudo"]["midias"])
        if versao["correcao"]:
            for lado in ("antes", "depois"):
                midias.extend(versao["correcao"][lado]["midias"])
    if not midias:
        return resultado
    ids = set()
    for midia in midias:
        valor = midia.get("id")
        if isinstance(valor, str) and ObjectId.is_valid(valor):
            ids.add(ObjectId(valor))
    retidas = repository.consultar_midias_retidas(identificador, ids) if ids else set()
    for midia in midias:
        # Metadados permanecem consultáveis após o fim da retenção. Links só
        # apontam para a rota autenticada e para mídias do próprio avanço.
        retida = midia.get("id") in retidas
        midia["retida"] = retida
        midia["conteudo"] = f"/midias/{midia['id']}/conteudo" if retida else None
    return resultado
