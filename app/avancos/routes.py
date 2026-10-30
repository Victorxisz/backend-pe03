"""UC-09: retirada autenticada de rascunhos."""

from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .midias import ErroMidia
from .service import ErroAvanco, excluir_rascunho

avancos_bp = Blueprint("avancos", __name__)


@avancos_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@avancos_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@avancos_bp.errorhandler(ErroAvanco)
@avancos_bp.errorhandler(ErroMidia)
def responder_erro(erro):
    corpo = dict(mensagem=str(erro), codigo=erro.codigo, campos=erro.campos)
    if getattr(erro, "pendentes", None) is not None:
        corpo["pendentes"] = erro.pendentes
    resposta = jsonify(corpo)
    if erro.status == 503 or erro.codigo == "CONFLITO_EXCLUSAO":
        resposta.headers["Retry-After"] = "30"
    return resposta, erro.status


@avancos_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante exclusão de rascunho")
    return jsonify(mensagem="Não foi possível concluir a exclusão. Tente novamente",
                   codigo="FALHA_NO_BANCO", campos=[]), 503


@avancos_bp.delete("/avancos/<string:avanco_id>")
def excluir(avanco_id):
    excluir_rascunho(avanco_id)
    return "", 204
