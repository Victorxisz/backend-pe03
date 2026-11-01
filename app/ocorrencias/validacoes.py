"""Validação dos comandos de cadastro, edição, transição e aceitação."""

import re

from app.dominio.comum import ErroDominio

ESTADOS_OCORRENCIA = ("aberta", "resolvida", "sem solução")


def validar_atualizacao(dados):
    if not isinstance(dados, dict):
        raise ErroDominio("Envie um objeto JSON", ["corpo"])
    erros = sorted(set(dados) - {"versao", "alteracoes", "transicao"})
    if type(dados.get("versao")) is not int or dados["versao"] < 0:
        erros.append("versao")
    if not ({"alteracoes", "transicao"} & set(dados)):
        erros.append("corpo")
    alteracoes = dados.get("alteracoes", {})
    if "alteracoes" in dados:
        if not isinstance(alteracoes, dict) or not alteracoes:
            erros.append("alteracoes")
        else:
            erros.extend("alteracoes." + campo for campo in sorted(
                set(alteracoes) - {"titulo", "descricao", "marco_id", "responsavel_id"}))
            for campo in ("titulo", "descricao"):
                if campo in alteracoes and (not isinstance(alteracoes[campo], str) or not alteracoes[campo].strip()):
                    erros.append("alteracoes." + campo)
    transicao = dados.get("transicao")
    if "transicao" in dados:
        if not isinstance(transicao, dict):
            erros.append("transicao")
        else:
            erros.extend("transicao." + campo for campo in sorted(set(transicao) - {"estado", "motivo"}))
            if not isinstance(transicao.get("estado"), str) or transicao["estado"] not in ESTADOS_OCORRENCIA:
                erros.append("transicao.estado")
            if not isinstance(transicao.get("motivo"), str) or not transicao["motivo"].strip():
                erros.append("transicao.motivo")
    if erros:
        raise ErroDominio("Informe versão e alterações descritivas ou transição com estado e motivo válidos", erros)
    return ({campo: valor.strip() if isinstance(valor, str) else valor for campo, valor in alteracoes.items()},
            {**transicao, "motivo": transicao["motivo"].strip()} if transicao is not None else None)


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


def validar_chave_reenvio(chave):
    if chave is not None and (not isinstance(chave, str)
                              or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", chave)):
        raise ErroDominio("Idempotency-Key deve ter de 1 a 128 caracteres: letras, números, ponto, hífen, sublinhado ou dois-pontos",
                          ["Idempotency-Key"])
