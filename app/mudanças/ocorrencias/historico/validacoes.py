"""Validação do conteúdo persistido antes da publicação."""

from datetime import date

from bson import ObjectId


def validar_rascunho(documento):
    campos = []
    valor = documento.get("data")
    try:
        if not isinstance(valor, str) or date.fromisoformat(valor).isoformat() != valor:
            campos.append("data")
    except ValueError:
        campos.append("data")
    descricao = documento.get("descricao")
    if not isinstance(descricao, str) or not descricao.strip():
        campos.append("descricao")
    if not isinstance(documento.get("marco_id"), ObjectId):
        campos.append("marco_id")
    return campos


def validar_midias(midias):
    tipos = {"foto": {"image/jpeg", "image/png"}, "video": {"video/mp4"},
             "documento": {"application/pdf"}}
    if not midias:
        return False
    for midia in midias:
        referencia = midia.get("referencia_externa")
        if (not isinstance(referencia, dict) or referencia.get("provedor") != "cloudinary"
                or not isinstance(midia.get("nome"), str) or not midia["nome"].strip()
                or type(midia.get("tamanho")) is not int or midia["tamanho"] <= 0
                or not isinstance(midia.get("tipo"), str)
                or not isinstance(midia.get("mime"), str)
                or midia.get("mime") not in tipos.get(midia.get("tipo"), set())):
            return False
    return True
