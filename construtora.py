import re
from datetime import datetime, timezone

from flask import request, jsonify, Blueprint, current_app
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from pymongo.errors import PyMongoError, DuplicateKeyError
from bson import ObjectId
from bson.errors import InvalidId

from validacoes import validar_dados_construtora, normalizar_dados_construtora
from db import colecao_construtora

construtora_bp = Blueprint(
    "construtora",
    __name__,
    url_prefix="/construtora"
)

bcrypt = Bcrypt()

@construtora_bp.route("/", methods=["POST"])
def cadastrar_construtora ():
    dados_recebidos = request.get_json(silent=True)

    erro_validacao = validar_dados_construtora(dados_recebidos)

    if erro_validacao:
        mensagem, status_mensagem = erro_validacao
        return jsonify(mensagem), status_mensagem

    nova_construtora = normalizar_dados_construtora(dados_recebidos)

    senha_hash = bcrypt.generate_password_hash(dados_recebidos["senha"]).decode("utf-8")

    nova_construtora.update({
        "senha_hash":senha_hash,
        "ativo":True,
        "data_cadastro":datetime.now(timezone.utc)
    })

    try:
        resultado = colecao_construtora.insert_one(
            nova_construtora
        )

    except DuplicateKeyError:
        return jsonify({
            "erro":"Já existe uma conta com este email"
        }), 409

    except PyMongoError:
        current_app.logger.exception("Erro ao cadastrar a construtora")
        return jsonify({"erro":"Houve um erro ao cadastrar a construtora"}), 500

    id_construtora = str(resultado.inserted_id)

    token = create_access_token(
        identity=id_construtora,
        additional_claims={"tipo":"construtora"}
    )

    return jsonify({
        "mensagem":"Construtora criada com sucesso",
        "construtora": {
            "id": id_construtora,
            "nome": nova_construtora["nome"],
            "email": nova_construtora["email"],
            "telefone": nova_construtora.get("telefone")
        },
        "access_token":token
    }), 201

@construtora_bp.route("/<string:construtora_id>", methods = ["DELETE"])
@jwt_required()
def deletar_construtora (construtora_id):
    try:
        id_construtora = ObjectId(construtora_id)
    except (InvalidId, TypeError):
        return jsonify({
            "erro":"Não foi possível indentificar a construtora"
        }), 400

    # Garante que a construtora esta deletando uma construtora
    if get_jwt().get("tipo") != "construtora":
        return jsonify({
            "erro":"Você não tem permissão para realizar esta ação"
        }), 403

    # Impede que a construtora delete a conta de outra. Apenas a dela
    if get_jwt_identity() != str(id_construtora):
        return jsonify({
            "erro": "Você só pode excluir sua própria conta."
        }), 403

    try:
        resultado = colecao_construtora.delete_one(
            {"_id": id_construtora}
        )
    except (PyMongoError):
        current_app.logger.exception("Erro ao excluir a construtora")
        return jsonify({
            "erro":"Não foi possível excluir a construtora, tente novamente"
        }), 500

    if resultado.deleted_count == 0:
        return jsonify({
            "erro": "Conta da construtora não encontrada."
        }), 404

    return jsonify({"mensagem":"Construtora exclída com sucesso"}), 200