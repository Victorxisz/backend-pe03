"""Consulta autenticada da trilha de decisões da obra."""

from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .service import ErroHistorico, consultar_mudanca, listar_mudancas

historico_bp = Blueprint("historico", __name__)


@historico_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@historico_bp.after_request
def impedir_cache(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@historico_bp.errorhandler(ErroHistorico)
def responder_erro(erro):
    corpo = {"mensagem": str(erro), "campos": erro.campos}
    if erro.codigo:
        corpo["codigo"] = erro.codigo
    return jsonify(corpo), erro.status


@historico_bp.errorhandler(PyMongoError)
def responder_erro_banco(erro):
    current_app.logger.error("Falha ao consultar histórico")
    return jsonify(mensagem="Não foi possível consultar o histórico", campos=[]), 503


@historico_bp.get("/obras/<string:obra_id>/mudancas")
def listar(obra_id):
    # Correções entram na lista e apontam para a comparação de versões.
    return jsonify(mudancas=listar_mudancas(obra_id))


@historico_bp.get("/mudancas/<string:mudanca_id>")
def consultar(mudanca_id):
    return jsonify(consultar_mudanca(mudanca_id))
