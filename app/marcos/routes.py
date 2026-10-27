"""Contrato HTTP do cadastro de marcos."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pymongo.errors import PyMongoError

from .service import ErroMarco, criar_marco


marcos_bp = Blueprint("marcos", __name__, url_prefix="/obras")


@marcos_bp.post("/<string:obra_id>/marcos")
@jwt_required()
def cadastrar_marco(obra_id):
    try:
        marco = criar_marco(obra_id, request.get_json(silent=True))
    except ErroMarco as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro de marco")
        return jsonify(mensagem="Não foi possível salvar o marco"), 500
    return responder_marco_cadastrado(marco)


def responder_marco_cadastrado(marco):
    resposta = jsonify(marco)
    resposta.status_code = 201
    resposta.headers["Location"] = f"/obras/{marco['obra_id']}/marcos/{marco['id']}"
    return resposta
