from datetime import datetime, timezone
import re

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from db import colecao_obras, colecao_trabalhadores
from validacoes import (
    normalizar_dados_trabalhador,
    validar_dados_trabalhador,
)


trabalhadores_bp = Blueprint(
    "trabalhadores",
    __name__,
    url_prefix="/trabalhadores",
)


@trabalhadores_bp.before_request
@sessao_obrigatoria
def exigir_autenticacao():
    pass


def trabalhador_para_dict(documento):
    return {
        "id": str(documento["_id"]),
        "nome": documento.get("nome", ""),
        "email": documento.get("email"),
        "telefone": documento.get("telefone"),
        "cargo": documento.get("cargo"),
        "obras": documento.get("obras", []),
        "ativo": documento.get("ativo"),
        "data_cadastro": documento.get(
            "data_cadastro",
            documento.get("criado_em"),
        ),
    }


@trabalhadores_bp.errorhandler(PyMongoError)
def tratar_erro_banco(erro):
    current_app.logger.exception(
        "Erro ao acessar dados de trabalhadores"
    )
    return jsonify({
        "erro": "Não foi possível concluir a operação. Tente novamente"
    }), 503


@trabalhadores_bp.post("/obra/<string:obra_id>/")
def cadastrar_trabalhador_em_obra(obra_id):
    try:
        id_obra = ObjectId(obra_id)
    except (InvalidId, TypeError):
        return jsonify({"erro": "ID da obra inválido"}), 400

    dados = request.get_json(silent=True)
    erro = validar_dados_trabalhador(dados)

    if erro:
        mensagem, status = erro
        return jsonify(mensagem), status

    obra = colecao_obras.find_one(
        {"_id": id_obra},
        {"_id": 1},
    )
    if obra is None:
        return jsonify({"erro": "Obra não encontrada"}), 404

    trabalhador = normalizar_dados_trabalhador(dados)
    trabalhador.update({
        "obras": [str(id_obra)],
        "ativo": True,
        "data_cadastro": datetime.now(timezone.utc),
    })

    resultado = colecao_trabalhadores.insert_one(trabalhador)

    return jsonify({
        "mensagem": "Trabalhador criado com sucesso e vinculado à obra",
        "id": str(resultado.inserted_id),
        "obra_id": str(id_obra),
    }), 201


@trabalhadores_bp.patch("/<string:trabalhador_id>/")
def atualizar_trabalhador(trabalhador_id):
    try:
        id_trabalhador = ObjectId(trabalhador_id)
    except (InvalidId, TypeError):
        return jsonify({"erro": "ID do trabalhador inválido"}), 400

    dados = request.get_json(silent=True)
    erro = validar_dados_trabalhador(
        dados,
        atualizacao=True,
    )

    if erro:
        mensagem, status = erro
        return jsonify(mensagem), status

    campos = normalizar_dados_trabalhador(
        dados,
        incluir_obras=True,
    )

    if "obras" in campos:
        # O validador já verificou o formato desses IDs.
        ids_obras = [ObjectId(valor) for valor in campos["obras"]]

        encontradas = {
            str(obra["_id"])
            for obra in colecao_obras.find(
                {"_id": {"$in": ids_obras}},
                {"_id": 1},
            )
        }

        ausentes = sorted(set(campos["obras"]) - encontradas)

        if ausentes:
            return jsonify({
                "erro": "Uma ou mais obras não foram encontradas",
                "obras": ausentes,
            }), 422

    resultado = colecao_trabalhadores.update_one(
        {"_id": id_trabalhador},
        {"$set": campos},
    )

    if resultado.matched_count == 0:
        return jsonify({"erro": "Trabalhador não encontrado"}), 404

    return jsonify({
        "mensagem": "Trabalhador atualizado com sucesso",
        "id": str(id_trabalhador),
    }), 200


@trabalhadores_bp.delete("/<string:trabalhador_id>/")
def deletar_trabalhador(trabalhador_id):
    try:
        id_trabalhador = ObjectId(trabalhador_id)
    except (InvalidId, TypeError):
        return jsonify({"erro": "ID do trabalhador inválido"}), 400

    resultado = colecao_trabalhadores.delete_one(
        {"_id": id_trabalhador},
    )

    if resultado.deleted_count == 0:
        return jsonify({"erro": "Trabalhador não encontrado"}), 404

    return jsonify({
        "mensagem": "Trabalhador excluído com sucesso",
    }), 200


@trabalhadores_bp.get("/nome/<string:nome_usuario>/")
def filtrar_usuario_por_nome(nome_usuario):
    nome = nome_usuario.strip()

    if not nome:
        return jsonify({
            "erro": "Digite um nome para pesquisar",
        }), 422

    documentos = colecao_trabalhadores.find({
        "nome": {
            "$regex": re.escape(nome),
            "$options": "i",
        },
    })

    return jsonify([
        trabalhador_para_dict(documento)
        for documento in documentos
    ]), 200


@trabalhadores_bp.get("/cargo/<string:cargo>/")
def filtrar_usuario_por_cargo(cargo):
    cargo = cargo.strip()

    if not cargo:
        return jsonify({
            "erro": "Digite um cargo para pesquisar",
        }), 422

    documentos = colecao_trabalhadores.find({
        "cargo": {
            "$regex": re.escape(cargo),
            "$options": "i",
        },
    })

    return jsonify([
        trabalhador_para_dict(documento)
        for documento in documentos
    ]), 200


@trabalhadores_bp.get("/obra/<string:obra_id>/")
def filtrar_usuario_por_obra(obra_id):
    try:
        id_obra = ObjectId(obra_id)
    except (InvalidId, TypeError):
        return jsonify({"erro": "ID da obra inválido"}), 400

    obra = colecao_obras.find_one(
        {"_id": id_obra},
        {"_id": 1},
    )
    if obra is None:
        return jsonify({"erro": "Obra não encontrada"}), 404

    # Consulta o vínculo pelo ID da obra, independentemente do email.
    documentos = colecao_trabalhadores.find({
        "obras": str(id_obra),
    })

    return jsonify([
        trabalhador_para_dict(documento)
        for documento in documentos
    ]), 200