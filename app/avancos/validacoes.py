"""Validação de cadastro e edição de avanços."""

from datetime import date

from bson import ObjectId
from bson.errors import InvalidId


CAMPOS_EDITAVEIS = {"data", "descricao", "midias_manter"}


def validar_avanco(dados):
    campos = []
    if not isinstance(dados, dict):
        return ["data", "descricao"]
    valor_data = dados.get("data")
    if not isinstance(valor_data, str):
        campos.append("data")
    else:
        try:
            if date.fromisoformat(valor_data).isoformat() != valor_data:
                campos.append("data")
        except ValueError:
            campos.append("data")
    descricao = dados.get("descricao")
    if not isinstance(descricao, str) or not descricao.strip():
        campos.append("descricao")
    return campos


def validar_edicao(dados, *, possui_novas_midias=False):
    if not isinstance(dados, dict):
        return "Envie um objeto com os dados da edição", []
    desconhecidos = set(dados) - CAMPOS_EDITAVEIS
    if desconhecidos:
        return "Campos permitidos: data, descricao e midias_manter", sorted(desconhecidos)
    if not dados and not possui_novas_midias:
        return "Envie pelo menos uma alteração", []
    if "data" in dados:
        valor = dados["data"]
        if not isinstance(valor, str):
            return "Informe a data no formato AAAA-MM-DD", ["data"]
        try:
            convertida = date.fromisoformat(valor)
        except ValueError:
            return "Informe uma data válida no formato AAAA-MM-DD", ["data"]
        if convertida.isoformat() != valor:
            return "Informe a data no formato AAAA-MM-DD", ["data"]
    if "descricao" in dados and (not isinstance(dados["descricao"], str) or not dados["descricao"].strip()):
        return "Preencha a descrição do avanço", ["descricao"]
    if "midias_manter" in dados:
        ids = dados["midias_manter"]
        if not isinstance(ids, list):
            return "midias_manter deve ser uma lista de IDs", ["midias_manter"]
        vistos = set()
        for identificador in ids:
            if not isinstance(identificador, str):
                return "Cada ID de mídia deve ser um texto", ["midias_manter"]
            try:
                oid = ObjectId(identificador)
            except (InvalidId, TypeError):
                return "Existe um ID de mídia inválido", ["midias_manter"]
            if oid in vistos:
                return "Não repita IDs em midias_manter", ["midias_manter"]
            vistos.add(oid)
    return None


def normalizar_edicao(dados):
    normalizados = {}
    if "data" in dados:
        normalizados["data"] = dados["data"]
    if "descricao" in dados:
        normalizados["descricao"] = dados["descricao"].strip()
    if "midias_manter" in dados:
        normalizados["midias_manter"] = [ObjectId(valor) for valor in dados["midias_manter"]]
    return normalizados
