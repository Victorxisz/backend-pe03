from datetime import datetime, timezone

import re
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pymongo.errors import PyMongoError

from db import cliente_mongo, colecao_trabalhadores, colecao_obras
from validacoes import (
    normalizar_dados_trabalhador,
    validar_dados_trabalhador,
)


# Todas as rotas deste grupo começam com /trabalhadores.
trabalhadores_bp = Blueprint(
    "trabalhadores",
    __name__,
    url_prefix="/trabalhadores"
)


# Todas as rotas de trabalhadores necessitam de uma sessão válida do usuário.
@trabalhadores_bp.before_request
@jwt_required()
def exigir_autenticacao():
    pass


def trabalhador_para_dict(documento):
    """Prepara um documento para as futuras rotas de consulta."""
    if documento is None:
        return None

    return {
        "id": str(documento["_id"]),
        "nome": documento.get("nome", ""),
        "email": documento.get("email"),
        "telefone": documento.get("telefone"),
        "cargo": documento.get("cargo"),
        "obras": documento.get("obras", []),
        "ativo": documento.get("ativo"),
        # Compatibilidade com o nome usado nos cadastros antigos.
        "data_cadastro": documento.get(
            "data_cadastro",
            documento.get("criado_em")
        )
    }


@trabalhadores_bp.route(
    "/obra/<string:obra_id>/",
    methods=["POST"]
)
def cadastrar_trabalhador_em_obra (obra_id):
    """Cria um trabalhador vinculado à obra informada na URL."""
    try:
        id_obra = ObjectId(obra_id)
    except (InvalidId, TypeError):
        return jsonify({"erro":"ID da obra inválido"}), 400

    dados_recebidos = request.get_json(silent=True)

    erro_validacao = validar_dados_trabalhador(dados_recebidos)

    if erro_validacao:
        mensagem, status_http = erro_validacao
        return jsonify(mensagem), status_http

    novo_trabalhador = normalizar_dados_trabalhador(
        dados_recebidos
    )

    # Estes campos são definidos pela API.
    novo_trabalhador.update({
        "obras": [str(id_obra)],
        "ativo": True,
        "data_cadastro": datetime.now(timezone.utc)
    })

    try:
        with cliente_mongo.start_session() as sessao:
            with sessao.start_transaction():
                obra = colecao_obras.find_one(
                    {"_id":id_obra},
                    session = sessao
                )

                if obra is None:
                    return jsonify(
                        {"erro":"Obra não encontrada"}, 404
                    )

                resultado = colecao_trabalhadores.insert_one(
                    novo_trabalhador,
                    session=sessao
                )

                colecao_obras.update_one(
                    {"_id": id_obra},
                    {
                        "$addToSet": {
                            "trabalhadores": novo_trabalhador["email"]
                        }
                    },

                    session=sessao
                )
    except PyMongoError:
        current_app.logger.exception(
            "Erro ao cadastrar trabalhador na obra"
        )
        return jsonify({
            "erro": "Não foi possível salvar o trabalhador na obra"
        }), 500

    return jsonify({
        "mensagem": "Trabalhador criado com sucesso e vinculado à obra",
        "id": str(resultado.inserted_id),
        "obra_id": str(id_obra)
    }), 201


@trabalhadores_bp.route(
    "/<trabalhador_id>/",
    methods=["PATCH"]
)
def atualizar_trabalhador(trabalhador_id):
    """
    Atualiza somente os campos enviados.

    Se 'obras' for enviado, substitui a lista atual.
    Uma lista vazia remove todos os vínculos.
    """
    try:
        id_mongo = ObjectId(trabalhador_id)
    except (InvalidId, TypeError):
        return jsonify({
            "erro": "ID do trabalhador inválido"
        }), 400

    dados_recebidos = request.get_json(silent=True)

    erro_validacao = validar_dados_trabalhador(
        dados_recebidos,
        atualizacao=True
    )

    if erro_validacao:
        mensagem, status_http = erro_validacao
        return jsonify(mensagem), status_http

    campos_para_atualizar = normalizar_dados_trabalhador(
        dados_recebidos,
        incluir_obras=True
    )

    try:
        resultado = colecao_trabalhadores.update_one(
            {"_id": id_mongo},
            {"$set": campos_para_atualizar}
        )
    except PyMongoError:
        current_app.logger.exception(
            "Erro ao atualizar trabalhador"
        )
        return jsonify({
            "erro": "Não foi possível atualizar o trabalhador"
        }), 500

    if resultado.matched_count == 0:
        return jsonify({
            "erro": "Trabalhador não encontrado"
        }), 404

    # Também retorna sucesso se os valores já estavam salvos.
    return jsonify({
        "mensagem": "Trabalhador atualizado com sucesso",
        "id": str(id_mongo)
    }), 200

@trabalhadores_bp.route(
    "/<trabalhador_id>/",
    methods = ["DELETE"]
)
def deletar_trabalhador(trabalhador_id):
    try:
        id_mongo = ObjectId(trabalhador_id)
    except (InvalidId, TypeError):
        return jsonify({"erro":"ID do trabalhador inválido"}), 400

    try:
        resultado = colecao_trabalhadores.delete_one(
            {"_id": id_mongo},
        )
    except (PyMongoError):
        current_app.logger.exception("Erro ao excluir o trabalhador")
        return jsonify({"erro":"Não foi possível excluir o trabalhador"}),500

    if resultado.deleted_count == 0:
        return jsonify({"erro":"Trabalhador não encontrado"}), 404

    return jsonify({"mensagem":"Trabalhador excluído com sucesso"}), 200

@trabalhadores_bp.route(
    "/nome/<string:nome_usuario>/",
    methods = ["GET"]
)
def filtrar_usuario_por_nome (nome_usuario):
    nome_busca = nome_usuario.strip()

    if not nome_busca:
        return jsonify({"erro":"Digite algum usuário para pesquisa"}), 422

    filtro = {
            "nome": {
                "$regex":re.escape(nome_busca), # Escapa de caracteres especiais jogados no meio da string. Como: ?, *, ...
                "$options": "i"
           }
        }

    try:
        cursor = colecao_trabalhadores.find(filtro)

        trabalhadores = [
            trabalhador_para_dict(documento)
            for documento in cursor
        ]
    except (PyMongoError):
        current_app.logger.exception("Erro ao encontrar o trabalhador")
        return jsonify({"erro": "Não foi possível encontrar o trabalhador"}), 500

    return jsonify(trabalhadores), 200

@trabalhadores_bp.route("/cargo/<string:cargo>/", methods = ["GET"])
def filtrar_usuario_por_cargo (cargo):
    cargo = cargo.strip()

    if not cargo:
        return jsonify({"erro":"Digite algum cargo para pesquisar"}), 422

    filtro = {
        "cargo":
        {
            "$regex":re.escape(cargo),
            "$options":"i"
        }
    }

    try:
        cursor = colecao_trabalhadores.find(filtro)

        trabalhadores = [
            trabalhador_para_dict(documento)
            for documento in cursor
        ]

    except (PyMongoError):
        current_app.logger.exception("Erro ao encontrar o trabalhador")
        return jsonify({"erro":"Não foi possível encontrar o trabalhador"}), 422

    return jsonify(trabalhadores), 200

@trabalhadores_bp.route("/obra/<obra_id>/", methods = ["GET"])
def filtrar_usuario_por_obra (obra_id):
    try:
        id_obra = ObjectId(obra_id)
    except (InvalidId,TypeError):
        return jsonify({"erro":"ID da obra inválido"}), 400

    try:
        obra = colecao_obras.find_one({"_id":id_obra})

        if obra is None:
            return jsonify({"erro":"Nenhuma obra encontrada"}), 404

        emails_trabalhadores = obra.get("trabalhadores", [])

        if not emails_trabalhadores:
            return jsonify({"mensagem": "Nenhum usuário encontrado"}),200

        cursor = colecao_trabalhadores.find({
            "email":{"$in":emails_trabalhadores}
        })

        trabalhadores = [
            trabalhador_para_dict(documento)
            for documento in cursor
        ]

    except (PyMongoError):
        current_app.logger.exception(
            "Erro ao buscar trabalhadores na obra"
        )
        return jsonify({"erro":"Não foi possível encontrar os trabalhadores da obra"}), 500

    return jsonify(trabalhadores), 200
