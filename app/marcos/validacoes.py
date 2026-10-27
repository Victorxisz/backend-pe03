"""Validação do contrato de criação de marcos."""

from datetime import date


CAMPOS_DO_MARCO = ("nome", "descricao", "inicio_previsto", "fim_previsto")


def validar_marco(dados_do_marco):
    if not isinstance(dados_do_marco, dict):
        return "Envie um objeto JSON", ["corpo"]
    return (
        validar_campos_do_marco(dados_do_marco)
        or validar_textos_do_marco(dados_do_marco)
        or validar_periodo_previsto(dados_do_marco)
    )


def validar_campos_do_marco(dados_do_marco):
    campos_desconhecidos = sorted(set(dados_do_marco) - set(CAMPOS_DO_MARCO))
    campos_ausentes = [campo for campo in CAMPOS_DO_MARCO if campo not in dados_do_marco]
    if campos_desconhecidos or campos_ausentes:
        return (
            "Envie somente os campos obrigatórios do marco",
            campos_desconhecidos + campos_ausentes,
        )
    return None


def validar_textos_do_marco(dados_do_marco):
    for campo in ("nome", "descricao"):
        texto_do_marco = dados_do_marco[campo]
        if not isinstance(texto_do_marco, str) or not texto_do_marco.strip():
            return f"O campo '{campo}' deve ser um texto preenchido", [campo]
    return None


def validar_periodo_previsto(dados_do_marco):
    for campo in ("inicio_previsto", "fim_previsto"):
        erro_data = validar_data_prevista(dados_do_marco[campo], campo)
        if erro_data:
            return erro_data
    # Datas válidas em AAAA-MM-DD mantêm a ordem cronológica na comparação.
    if dados_do_marco["fim_previsto"] < dados_do_marco["inicio_previsto"]:
        return (
            "A data final prevista não pode anteceder a inicial",
            ["inicio_previsto", "fim_previsto"],
        )
    return None


def validar_data_prevista(data_prevista, campo):
    mensagem = f"O campo '{campo}' deve ser uma data no formato AAAA-MM-DD"
    if not isinstance(data_prevista, str):
        return mensagem, [campo]
    try:
        if date.fromisoformat(data_prevista).isoformat() != data_prevista:
            return mensagem, [campo]
    except ValueError:
        return mensagem, [campo]
    return None
