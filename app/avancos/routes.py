"""Contrato HTTP do UC-11: consulta das versões de um avanço corrigido."""

from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .versoes import ErroVersoes, consultar_versoes


avancos_bp = Blueprint("avancos", __name__)


@avancos_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@avancos_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@avancos_bp.errorhandler(ErroVersoes)
def responder_erro(erro):
    return jsonify(codigo=erro.codigo, mensagem=str(erro), campos=erro.campos), erro.status


@avancos_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante consulta das versões do avanço")
    return jsonify(codigo="FALHA_NO_BANCO", mensagem="Não foi possível consultar as versões",
                   campos=[]), 503


@avancos_bp.get("/avancos/<string:avanco_id>/versoes")
def consultar(avanco_id):
    return jsonify(consultar_versoes(avanco_id)), 200
