"""Rotas autenticadas de cadastro, consulta e manutenção de avanços."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from .midias import ErroMidia
from .service import ErroAvanco, criar_avanco, consultar_avanco, consultar_avancos, excluir_rascunho

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
    corpo = {"mensagem": str(erro), "campos": getattr(erro, "campos", ["midias"])}
    codigo = getattr(erro, "codigo", None)
    if codigo:
        corpo["codigo"] = codigo
    pendentes = getattr(erro, "pendentes", None)
    if pendentes is not None:
        corpo["pendentes"] = pendentes
    resposta = jsonify(corpo)
    if getattr(erro, "status", 500) == 503 or codigo == "CONFLITO_EXCLUSAO":
        resposta.headers["Retry-After"] = "30"
    return resposta, getattr(erro, "status", 500)


@avancos_bp.errorhandler(ErroArmazenamento)
@avancos_bp.errorhandler(ErroLimpeza)
def responder_erro_armazenamento(erro):
    return jsonify(mensagem=str(erro), codigo=getattr(erro, "codigo", "FALHA_ARMAZENAMENTO"), campos=["midias"]), getattr(erro, "status", 503)


@avancos_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.exception("Falha no banco durante operação de avanço")
    return jsonify(mensagem="Não foi possível concluir a solicitação", codigo="FALHA_NO_BANCO", campos=[]), 503


@avancos_bp.post("/marcos/<string:marco_id>/avancos")
def cadastrar_avanco(marco_id):
    avanco = criar_avanco(marco_id, request.form.to_dict(), request.files.getlist("midias"), get_jwt_identity())
    resposta = jsonify(avanco)
    resposta.status_code = 201
    resposta.headers["Location"] = url_for("avancos.consultar_avanco_route", avanco_id=avanco["id"])
    return resposta


@avancos_bp.get("/marcos/<string:marco_id>/avancos")
def listar_avancos(marco_id):
    return jsonify(consultar_avancos(marco_id)), 200


@avancos_bp.get("/avancos/<string:avanco_id>")
def consultar_avanco_route(avanco_id):
    return jsonify(consultar_avanco(avanco_id)), 200


@avancos_bp.delete("/avancos/<string:avanco_id>")
def excluir(avanco_id):
    excluir_rascunho(avanco_id)
    return "", 204
