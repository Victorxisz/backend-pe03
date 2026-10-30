"""Contrato HTTP do cadastro, consulta e edição de obras."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from app.auth.permissions import sessao_obrigatoria
from pymongo.errors import PyMongoError

from .service import ErroObra, buscar_obra, criar_obra, editar_descricao, listar_obras

obras_bp = Blueprint("obras", __name__, url_prefix="/obras")
@obras_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@obras_bp.post("")
def cadastrar_obra():
    try:
        obra = criar_obra(request.get_json(silent=True), get_jwt_identity())
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro da obra")
        return jsonify(mensagem="Não foi possível salvar a obra"), 500

    resposta = jsonify(obra)
    resposta.status_code = 201
    resposta.headers["Location"] = url_for("obras.consultar_obra", obra_id=obra["id"])
    return resposta


@obras_bp.get("/<string:obra_id>")
def consultar_obra(obra_id):
    try:
        obra = buscar_obra(obra_id)
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante consulta da obra")
        return jsonify(mensagem="Não foi possível consultar a obra"), 500
    return jsonify(obra), 200


@obras_bp.get("")
def consultar_obras():
    try:
        obras = listar_obras(request.args)
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante listagem de obras")
        return jsonify(mensagem="Não foi possível consultar as obras"), 500
    return jsonify(obras=obras), 200


@obras_bp.patch("/<string:obra_id>")
def corrigir_descricao(obra_id):
    try:
        documento = editar_descricao(obra_id, request.get_json(silent=True))
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        # Não expõe mensagens do driver, URI ou credenciais.
        current_app.logger.error("Falha no banco durante edição descritiva da obra")
        return jsonify(mensagem="Não foi possível salvar a correção da obra"), 500

    return (
        jsonify(
            id=str(documento["_id"]),
            **{
                campo: documento.get(campo)
                for campo in ("nome", "descricao", "localizacao", "cliente")
            },
        ),
        200,
    )
