"""Validação dos comandos de aceitação de ocorrência."""

from app.dominio.comum import ErroDominio


def validar_cadastro(dados):
    if not isinstance(dados, dict):
        raise ErroDominio("Envie um objeto com os dados da ocorrência", ["corpo"])
    permitidos = {"titulo", "descricao", "estado", "marco_id", "responsavel_id"}
    erros = sorted(set(dados) - permitidos)
    for campo in ("titulo", "descricao"):
        if not isinstance(dados.get(campo), str) or not dados[campo].strip():
            erros.append(campo)
    if not isinstance(dados.get("estado"), str) or dados["estado"] not in ("aberta", "sem solução"):
        erros.append("estado")
    if erros:
        raise ErroDominio("Informe título, descrição e estado inicial aberta ou sem solução", erros)
    return {campo: valor.strip() if isinstance(valor, str) else valor
            for campo, valor in dados.items()}


def validar_aceitacao(dados):
    if not isinstance(dados, dict):
        raise ErroDominio("Envie um objeto JSON", ["corpo"])
    extras = sorted(set(dados) - {"justificativa", "medida_compensatoria"})
    ausentes = ["justificativa"] if "justificativa" not in dados else []
    if extras or ausentes:
        raise ErroDominio("Informe justificativa e, opcionalmente, medida compensatória", extras + ausentes)
    if not isinstance(dados["justificativa"], str) or not dados["justificativa"].strip():
        raise ErroDominio("A justificativa deve ser um texto preenchido", ["justificativa"])
    if "medida_compensatoria" in dados:
        medida = dados["medida_compensatoria"]
        if medida is not None and (not isinstance(medida, str) or not medida.strip()):
            raise ErroDominio("A medida compensatória deve ser um texto preenchido", ["medida_compensatoria"])
