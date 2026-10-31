"""Contrato HTTP do UC-14, com a mesma autenticação dos demais módulos."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .service import (
    ErroOcorrencia,
    consultar_ocorrencia,
    consultar_ocorrencias,
    registrar_ocorrencia,
)
from .validacoes import CAMPOS_OBRIGATORIOS, CAMPOS_OPCIONAIS


ocorrencias_bp = Blueprint("ocorrencias", __name__)

CAMPO_DOS_ARQUIVOS = "midias"
FORMULARIOS = ("multipart/form-data", "application/x-www-form-urlencoded")


@ocorrencias_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@ocorrencias_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@ocorrencias_bp.errorhandler(ErroOcorrencia)
def responder_erro(erro):
    return jsonify(codigo=erro.codigo, mensagem=str(erro), campos=erro.campos), erro.status


@ocorrencias_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante registro ou consulta de ocorrências")
    return jsonify(codigo="FALHA_NO_BANCO",
                   mensagem="Não foi possível concluir a solicitação", campos=[]), 503


def _entrada():
    """JSON quando não há mídia; multipart com arquivos em `midias` quando há."""
    if request.mimetype not in FORMULARIOS:
        corpo = request.get_json(silent=True)
        if not isinstance(corpo, dict):
            return corpo, []
        # Opcional nulo equivale a ausente, como no formulário sem o campo.
        return {campo: valor for campo, valor in corpo.items() if valor is not None}, []

    permitidos = set(CAMPOS_OBRIGATORIOS) | set(CAMPOS_OPCIONAIS)
    desconhecidos = sorted((set(request.form) - permitidos)
                           | (set(request.files) - {CAMPO_DOS_ARQUIVOS}))
    if desconhecidos:
        raise ErroOcorrencia(
            f"Envie os campos da ocorrência e os arquivos em '{CAMPO_DOS_ARQUIVOS}'",
            422,
            desconhecidos,
        )
    dados = {}
    for campo in permitidos:
        if campo not in request.form:
            continue
        valor = request.form[campo]
        if campo in CAMPOS_OPCIONAIS and not valor.strip():
            continue
        dados[campo] = valor
    return dados, request.files.getlist(CAMPO_DOS_ARQUIVOS)


@ocorrencias_bp.post("/obras/<string:obra_id>/ocorrencias")
def registrar(obra_id):
    # ID, autoria e data de registro são do servidor, nunca aceitos do cliente.
    dados, arquivos = _entrada()
    ocorrencia = registrar_ocorrencia(obra_id, dados, arquivos, get_jwt_identity())
    return jsonify(ocorrencia), 201, {
        "Location": url_for("ocorrencias.consultar", ocorrencia_id=ocorrencia["id"])
    }


@ocorrencias_bp.get("/obras/<string:obra_id>/ocorrencias")
def listar(obra_id):
    return jsonify(ocorrencias=consultar_ocorrencias(obra_id)), 200


@ocorrencias_bp.get("/ocorrencias/<string:ocorrencia_id>")
def consultar(ocorrencia_id):
    return jsonify(consultar_ocorrencia(ocorrencia_id)), 200
