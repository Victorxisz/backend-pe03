"""Contrato HTTP do cadastro autenticado de obras."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from pymongo.errors import PyMongoError

from app.obras.obras import criar_obra, validar_obra
from app.obras.service import ErroObra

obras_bp = Blueprint("cadastro_obras", __name__, url_prefix="/obras")


@obras_bp.post("")
@jwt_required()
def cadastrar_obra():
    dados_da_obra = request.get_json(silent=True)
    try:
        validar_obra(dados_da_obra)
        obra = criar_obra(dados_da_obra, get_jwt_identity())
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro da obra")
        return jsonify(mensagem="Não foi possível salvar a obra"), 500
    resposta = jsonify(obra)
    resposta.status_code = 201
    resposta.headers["Location"] = f"{request.path}/{obra['id']}"
    return resposta
