from datetime import datetime, timezone

import re
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError

from db import colecao_trabalhadores
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
    "/obra/<int:codigo_obra>/",
    methods=["POST"]
)
def cadastrar_trabalhador(codigo_obra):
    """Cria um trabalhador vinculado à obra informada na URL."""
    if codigo_obra <= 0:
        return jsonify({
            "erro": "O código da obra deve ser um inteiro positivo"
        }), 422

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
        "obras": [codigo_obra],
        "ativo": True,
        "data_cadastro": datetime.now(timezone.utc)
    })

    try:
        resultado = colecao_trabalhadores.insert_one(
            novo_trabalhador
        )
    except PyMongoError:
        current_app.logger.exception(
            "Erro ao cadastrar trabalhador"
        )
        return jsonify({
            "erro": "Não foi possível salvar o trabalhador"
        }), 500

    return jsonify({
        "mensagem": "Trabalhador criado com sucesso",
        "id": str(resultado.inserted_id)
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

