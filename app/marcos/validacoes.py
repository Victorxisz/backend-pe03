"""Validação do contrato de criação de marcos."""

from datetime import date


CAMPOS = ("nome", "descricao", "inicio_previsto", "fim_previsto")


def validar_marco(dados):
    if not isinstance(dados, dict):
        return "Envie um objeto JSON", ["corpo"]

    campos_extra = sorted(set(dados) - set(CAMPOS))
    campos_ausentes = [campo for campo in CAMPOS if campo not in dados]
    if campos_extra or campos_ausentes:
        return "Envie somente os campos obrigatórios do marco", campos_extra + campos_ausentes

    for campo in ("nome", "descricao"):
        valor = dados[campo]
        if not isinstance(valor, str) or not valor.strip():
            return f"O campo '{campo}' deve ser um texto preenchido", [campo]

    datas = {}
    for campo in ("inicio_previsto", "fim_previsto"):
        valor = dados[campo]
        if not isinstance(valor, str):
            return f"O campo '{campo}' deve ser uma data no formato AAAA-MM-DD", [campo]
        try:
            parseada = date.fromisoformat(valor)
        except ValueError:
            return f"O campo '{campo}' deve ser uma data no formato AAAA-MM-DD", [campo]
        if parseada.isoformat() != valor:
            return f"O campo '{campo}' deve ser uma data no formato AAAA-MM-DD", [campo]
        datas[campo] = parseada

    if datas["fim_previsto"] < datas["inicio_previsto"]:
        return "A data final prevista não pode anteceder a inicial", ["inicio_previsto", "fim_previsto"]
    return None
