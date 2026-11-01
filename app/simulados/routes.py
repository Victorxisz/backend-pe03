"""Consulta autenticada; não oferece criação de mensagens pelo produto."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.auth.permissions import sessao_obrigatoria
from .service import ErroSimulado, ServicoSimulados

simulados_bp = Blueprint("simulados", __name__)


@simulados_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@simulados_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@simulados_bp.errorhandler(ErroSimulado)
def responder_erro(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@simulados_bp.get("/obras/<string:obra_id>/feedback-simulado")
def consultar(obra_id):
    if set(request.args) - {"marco_id", "atualizacao_id"}:
        raise ErroSimulado("Parâmetros desconhecidos", 422, ["filtros"])
    if any(len(request.args.getlist(campo)) != 1 for campo in request.args):
        raise ErroSimulado("Não repita filtros", 422, ["filtros"])
    return jsonify(feedbacks=ServicoSimulados().consultar(
        obra_id, get_jwt_identity(), **request.args.to_dict()))
