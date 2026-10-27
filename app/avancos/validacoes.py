"""Validações dos dados recebidos para registrar um avanço."""

from datetime import date


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
