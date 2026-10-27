"""Rotas de registro e consulta de avanços."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from .midias import ErroMidia
from .service import ErroAvanco, criar_avanco, consultar_avanco, consultar_avancos

avancos_bp = Blueprint("avancos", __name__)


@avancos_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


def _erro(erro):
    return jsonify(mensagem=str(erro), campos=getattr(erro, "campos", ["midias"])), getattr(erro, "status", 503)


@avancos_bp.post("/marcos/<string:marco_id>/avancos")
def cadastrar_avanco(marco_id):
    try:
        avanco = criar_avanco(marco_id, request.form.to_dict(), request.files.getlist("midias"), get_jwt_identity())
    except (ErroAvanco, ErroMidia, ErroArmazenamento, ErroLimpeza) as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.exception("Falha no banco durante cadastro de avanço")
        return jsonify(mensagem="Não foi possível salvar o avanço"), 500
    resposta = jsonify(avanco)
    resposta.status_code = 201
    resposta.headers["Location"] = url_for("avancos.consultar_avanco", avanco_id=avanco["id"])
    return resposta


@avancos_bp.get("/marcos/<string:marco_id>/avancos")
def listar_avancos(marco_id):
    try:
        return jsonify(consultar_avancos(marco_id)), 200
    except ErroAvanco as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.exception("Falha no banco durante consulta de avanços")
        return jsonify(mensagem="Não foi possível consultar os avanços"), 500


@avancos_bp.get("/avancos/<string:avanco_id>")
def consultar_avanco_route(avanco_id):
    try:
        return jsonify(consultar_avanco(avanco_id)), 200
    except ErroAvanco as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.exception("Falha no banco durante consulta do avanço")
        return jsonify(mensagem="Não foi possível consultar o avanço"), 500
