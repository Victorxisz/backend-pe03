"""Contrato HTTP de marcos e suas dependências."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pymongo.errors import PyMongoError

from .service import (
    ErroMarco,
    criar_dependencia,
    criar_marco,
    listar_dependencias,
    remover_dependencia,
)


marcos_bp = Blueprint("marcos", __name__)


def _responder_erro_marco(erro):
    return jsonify(
        mensagem=str(erro),
        campos=erro.campos,
    ), erro.status


def _responder_erro_banco(mensagem):
    current_app.logger.exception(mensagem)
    return jsonify(mensagem=mensagem), 500


@marcos_bp.post("/obras/<string:obra_id>/marcos")
@jwt_required()
def cadastrar_marco(obra_id):
    try:
        marco = criar_marco(obra_id, request.get_json(silent=True))
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco("Não foi possível salvar o marco")

    resposta = jsonify(marco)
    resposta.status_code = 201
    resposta.headers["Location"] = (
        f"/obras/{obra_id}/marcos/{marco['id']}"
    )
    return resposta


@marcos_bp.get("/marcos/<string:marco_id>/dependencias")
@jwt_required()
def consultar_dependencias(marco_id):
    try:
        dependencias = listar_dependencias(marco_id)
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco(
            "Não foi possível consultar as dependências"
        )

    return jsonify(dependencias), 200


@marcos_bp.post("/marcos/<string:marco_id>/dependencias")
@jwt_required()
def cadastrar_dependencia(marco_id):
    try:
        dependencia = criar_dependencia(
            marco_id,
            request.get_json(silent=True),
        )
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco(
            "Não foi possível salvar a dependência"
        )

    resposta = jsonify(dependencia)
    resposta.status_code = 201
    resposta.headers["Location"] = (
        f"/marcos/{marco_id}/dependencias/{dependencia['id']}"
    )
    return resposta


@marcos_bp.delete(
    "/marcos/<string:marco_id>/dependencias/<string:dependencia_id>"
)
@jwt_required()
def excluir_dependencia(marco_id, dependencia_id):
    try:
        remover_dependencia(marco_id, dependencia_id)
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco(
            "Não foi possível remover a dependência"
        )

    return "", 204