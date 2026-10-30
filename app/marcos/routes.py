"""Contrato HTTP de marcos e suas dependências."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria

from .service import (
    ErroMarco,
    alterar_estado_marco,
    buscar_marco,
    criar_dependencia,
    criar_marco,
    listar_dependencias,
    listar_marcos,
    remover_dependencia,
)


marcos_bp = Blueprint("marcos", __name__)
estado_marcos_bp = Blueprint("estado_marcos", __name__, url_prefix="/marcos")


def _responder_erro_marco(erro):
    corpo = {"mensagem": str(erro), "campos": erro.campos}
    corpo.update(erro.detalhes)
    return jsonify(corpo), erro.status


def _responder_erro_banco(mensagem):
    current_app.logger.exception(mensagem)
    return jsonify(mensagem=mensagem), 500


@marcos_bp.get("/obras/<string:obra_id>/marcos/<string:marco_id>")
@sessao_obrigatoria
def consultar_marco(obra_id, marco_id):
    try:
        marco = buscar_marco(obra_id, marco_id)
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante busca de marco")
        return jsonify(mensagem="Não foi possível buscar o marco"), 500
    return jsonify(marco), 200


@marcos_bp.get("/obras/<string:obra_id>/marcos")
@sessao_obrigatoria
def consultar_marcos(obra_id):
    try:
        lista_marcos = listar_marcos(obra_id)
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante consulta de marcos")
        return jsonify(mensagem="Não foi possível consultar os marcos da obra"), 500
    return jsonify(lista_marcos), 200


@marcos_bp.post("/obras/<string:obra_id>/marcos")
@jwt_required()
def cadastrar_marco(obra_id):
    try:
        marco = criar_marco(obra_id, request.get_json(silent=True))
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro de marco")
        return jsonify(mensagem="Não foi possível salvar o marco"), 500

    resposta = jsonify(marco)
    resposta.status_code = 201
    resposta.headers["Location"] = f"/obras/{obra_id}/marcos/{marco['id']}"
    return resposta


@marcos_bp.get("/marcos/<string:marco_id>/dependencias")
@jwt_required()
def consultar_dependencias(marco_id):
    try:
        dependencias = listar_dependencias(marco_id)
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco("Não foi possível consultar as dependências")
    return jsonify(dependencias), 200


@marcos_bp.post("/marcos/<string:marco_id>/dependencias")
@jwt_required()
def cadastrar_dependencia(marco_id):
    try:
        dependencia = criar_dependencia(marco_id, request.get_json(silent=True))
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        return _responder_erro_banco("Não foi possível salvar a dependência")

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
        return _responder_erro_banco("Não foi possível remover a dependência")
    return "", 204


@estado_marcos_bp.patch("/<string:marco_id>")
@jwt_required()
def atualizar_marco(marco_id):
    try:
        marco = alterar_estado_marco(
            marco_id, request.get_json(silent=True), get_jwt_identity()
        )
    except ErroMarco as erro:
        return _responder_erro_marco(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante alteração de estado do marco")
        return jsonify(mensagem="Não foi possível salvar o estado do marco"), 500
    except Exception:
        current_app.logger.exception("Falha ao persistir alteração de estado do marco")
        return jsonify(mensagem="Não foi possível salvar o estado do marco"), 500
    return jsonify(marco), 200
