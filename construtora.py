"""Rotas da conta da construtora; os casos de uso ficam em app.construtoras."""

from flask import Blueprint, current_app, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    create_access_token, create_refresh_token, get_jwt, get_jwt_identity, jwt_required,
)
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.construtoras.service import ErroConstrutora, ServicoConstrutoras, ServicoSessoes
from db import colecao_construtora, colecao_sessoes_revogadas

construtora_bp = Blueprint("construtora", __name__, url_prefix="/construtora")
bcrypt = Bcrypt()
sessoes = ServicoSessoes(create_access_token, create_refresh_token)
servico = ServicoConstrutoras(bcrypt, sessoes)


def gerar_tokens_construtora(id_construtora):
    return sessoes.iniciar(id_construtora)


@construtora_bp.errorhandler(ErroConstrutora)
def responder_erro(erro):
    return jsonify(erro=str(erro)), erro.status


@construtora_bp.errorhandler(DuplicateKeyError)
def responder_duplicidade(erro):
    return jsonify(erro="Já existe uma conta com este email"), 409


@construtora_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Erro ao acessar a conta da construtora")
    return jsonify(erro="Não foi possível concluir a operação. Tente novamente"), 500


@construtora_bp.post("/")
def cadastrar_construtora():
    return jsonify(servico.cadastrar(request.get_json(silent=True))), 201


@construtora_bp.delete("/<string:construtora_id>")
@jwt_required()
def deletar_construtora(construtora_id):
    return jsonify(servico.excluir(construtora_id, get_jwt_identity(), get_jwt().get("tipo")))


@construtora_bp.patch("/<string:construtora_id>")
@jwt_required()
def atualizar_construtora(construtora_id):
    return jsonify(servico.atualizar(construtora_id, request.get_json(silent=True),
                                    get_jwt_identity(), get_jwt().get("tipo")))


@construtora_bp.post("/login/")
def login_construtora():
    return jsonify(servico.entrar(request.get_json(silent=True)))


@construtora_bp.post("/refresh/")
@jwt_required(refresh=True)
def renovar_token_construtora():
    return jsonify(servico.renovar(get_jwt_identity(), get_jwt()))


@construtora_bp.post("/logout/")
@jwt_required(verify_type=False)
def logout_construtora():
    return jsonify(servico.sair(get_jwt_identity(), get_jwt()))
