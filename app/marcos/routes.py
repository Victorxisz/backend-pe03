"""Contrato HTTP do cadastro de marcos."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from pymongo.errors import PyMongoError

from .service import ErroMarco, alterar_estado_marco, criar_marco


marcos_bp = Blueprint("marcos", __name__, url_prefix="/api/v1/obras")
estado_marcos_bp = Blueprint("estado_marcos", __name__, url_prefix="/api/v1/marcos")


@marcos_bp.post("/<string:obra_id>/marcos")
@jwt_required()
def cadastrar_marco(obra_id):
    try:
        marco = criar_marco(obra_id, request.get_json(silent=True))
    except ErroMarco as erro:
        corpo = {"mensagem": str(erro), "campos": erro.campos}
        corpo.update(erro.detalhes)
        return jsonify(corpo), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro de marco")
        return jsonify(mensagem="Não foi possível salvar o marco"), 500

    resposta = jsonify(marco)
    resposta.status_code = 201
    resposta.headers["Location"] = f"/api/v1/obras/{obra_id}/marcos/{marco['id']}"
    return resposta


@estado_marcos_bp.patch("/<string:marco_id>")
@jwt_required()
def atualizar_marco(marco_id):
    dados = request.get_json(silent=True)
    try:
        marco = alterar_estado_marco(marco_id, dados, get_jwt_identity())
    except ErroMarco as erro:
        corpo = {"mensagem": str(erro), "campos": erro.campos}
        corpo.update(erro.detalhes)
        return jsonify(corpo), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante alteração de estado do marco")
        return jsonify(mensagem="Não foi possível salvar o estado do marco"), 500
    except Exception:
        current_app.logger.exception("Falha ao persistir alteração de estado do marco")
        return jsonify(mensagem="Não foi possível salvar o estado do marco"), 500
    return jsonify(marco), 200
