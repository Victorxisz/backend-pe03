"""Validação do contrato de criação de marcos."""

from datetime import date


CAMPOS = ("nome", "descricao", "inicio_previsto", "fim_previsto")
ESTADOS_MARCO = ("a iniciar", "em andamento", "concluído")


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


def validar_alteracao_estado(dados):
    if not isinstance(dados, dict):
        return "Envie um objeto JSON", ["corpo"]

    campos_extra = sorted(set(dados) - {"estado", "motivo", "confirmar_dependencias"})
    campos_ausentes = [campo for campo in ("estado", "motivo") if campo not in dados]
    if campos_extra or campos_ausentes:
        return "Envie estado e motivo; confirmação de dependências é opcional", campos_extra + campos_ausentes

    if dados["estado"] not in ESTADOS_MARCO:
        return "Estado deve ser 'a iniciar', 'em andamento' ou 'concluído'", ["estado"]
    if not isinstance(dados["motivo"], str) or not dados["motivo"].strip():
        return "O campo 'motivo' deve ser um texto preenchido", ["motivo"]
    if "confirmar_dependencias" in dados and not isinstance(dados["confirmar_dependencias"], bool):
        return "O campo 'confirmar_dependencias' deve ser booleano", ["confirmar_dependencias"]
    return None
