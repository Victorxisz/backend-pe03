"""Validação do contrato de registro de ocorrências."""


# UC-15 ainda decide o conjunto completo de estados; o registro aceita só estes dois.
ESTADOS_INICIAIS = ("aberta", "sem solução")

CAMPOS_OBRIGATORIOS = ("titulo", "descricao", "estado")
CAMPOS_OPCIONAIS = ("marco_id", "responsavel_id")


def validar_registro(dados):
    if not isinstance(dados, dict):
        return "Envie os dados da ocorrência", ["corpo"]
    return (
        validar_campos_do_registro(dados)
        or validar_textos_do_registro(dados)
        or validar_estado_inicial(dados)
        or validar_vinculos_informados(dados)
    )


def validar_campos_do_registro(dados):
    desconhecidos = sorted(set(dados) - set(CAMPOS_OBRIGATORIOS) - set(CAMPOS_OPCIONAIS))
    ausentes = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in dados]
    if desconhecidos or ausentes:
        return (
            "Envie título, descrição e estado inicial; marco, responsável e mídia são opcionais",
            desconhecidos + ausentes,
        )
    return None


def validar_textos_do_registro(dados):
    for campo in ("titulo", "descricao"):
        texto = dados[campo]
        if not isinstance(texto, str) or not texto.strip():
            return f"O campo '{campo}' deve ser um texto preenchido", [campo]
    return None


def validar_estado_inicial(dados):
    if dados["estado"] not in ESTADOS_INICIAIS:
        return "O estado inicial deve ser 'aberta' ou 'sem solução'", ["estado"]
    return None


def validar_vinculos_informados(dados):
    # Opcional ausente e opcional nulo são equivalentes; texto vazio é erro de envio.
    for campo in CAMPOS_OPCIONAIS:
        if campo not in dados or dados[campo] is None:
            continue
        valor = dados[campo]
        if not isinstance(valor, str) or not valor.strip():
            return f"O campo '{campo}' deve ser um identificador ou ficar ausente", [campo]
    return None
