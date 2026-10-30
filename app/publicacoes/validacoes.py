"""Validação do conteúdo persistido antes da publicação."""

from datetime import date

from bson import ObjectId
from app.dominio.avancos import Midia
from app.dominio.comum import ErroDominio


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
    recursos = {
        "foto":"image",
        "video":"video",
        "documento":"raw",
    }

    if not midias:
        return False

    for midia in midias:
        if not isinstance(midia, dict):
            return False

        try:
            entidade = Midia.de_documento(midia)
        except ErroDominio:
            return False
        tipo = entidade.tipo
        referencia = midia.get("referencia_externa")

        if not isinstance(referencia, dict):
            return False

        public_id = referencia.get("public_id")
        recurso = referencia.get("resource_type")

        if (
            referencia.get("provedor") != "cloudinary"
            or not isinstance(public_id, str)
            or not public_id.strip()
            or not isinstance(recurso, str)
            or recurso != recursos[tipo]
            or referencia.get("delivery_type") != "authenticated"
        ):
            return False

    return True
