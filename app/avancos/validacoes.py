"""Validação dos campos recebidos na edição de um rascunho."""

from datetime import date

from bson import ObjectId
from bson.errors import InvalidId


CAMPOS_EDITAVEIS = {"data", "descricao", "midias_manter"}


def validar_edicao(dados, *, possui_novas_midias=False):
    """
    Retorna (mensagem, campos) se houver erro.
    Retorna None quando os dados forem válidos.

    Os arquivos novos são validados pelo serviço de mídias.
    """
    if not isinstance(dados, dict):
        return "Envie um objeto com os dados da edição", []

    desconhecidos = set(dados) - CAMPOS_EDITAVEIS

    if desconhecidos:
        return (
            "Campos permitidos: data, descricao e midias_manter",
            sorted(desconhecidos),
        )

    if not dados and not possui_novas_midias:
        return "Envie pelo menos uma alteração", []

    if "data" in dados:
        valor = dados["data"]

        if not isinstance(valor, str):
            return "Informe a data no formato AAAA-MM-DD", ["data"]

        try:
            data_convertida = date.fromisoformat(valor)
        except ValueError:
            return "Informe uma data válida no formato AAAA-MM-DD", ["data"]

        if data_convertida.isoformat() != valor:
            return "Informe a data no formato AAAA-MM-DD", ["data"]

    if "descricao" in dados:
        descricao = dados["descricao"]

        if not isinstance(descricao, str) or not descricao.strip():
            return "Preencha a descrição do avanço", ["descricao"]

    if "midias_manter" in dados:
        identificadores = dados["midias_manter"]

        if not isinstance(identificadores, list):
            return "midias_manter deve ser uma lista de IDs", ["midias_manter"]

        vistos = set()

        for identificador in identificadores:
            if not isinstance(identificador, str):
                return "Cada ID de mídia deve ser um texto", ["midias_manter"]

            try:
                object_id = ObjectId(identificador)
            except (InvalidId, TypeError):
                return "Existe um ID de mídia inválido", ["midias_manter"]

            if object_id in vistos:
                return "Não repita IDs em midias_manter", ["midias_manter"]

            vistos.add(object_id)

    return None


def normalizar_edicao(dados):
    """Prepara somente os campos enviados, após a validação."""
    normalizados = {}

    if "data" in dados:
        normalizados["data"] = dados["data"]

    if "descricao" in dados:
        normalizados["descricao"] = dados["descricao"].strip()

    if "midias_manter" in dados:
        normalizados["midias_manter"] = [
            ObjectId(identificador)
            for identificador in dados["midias_manter"]
        ]

    return normalizados