"""Contrato HTTP dos trabalhadores; regras e persistência ficam em app.trabalhadores."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from app.trabalhadores.service import ErroTrabalhador, ServicoTrabalhadores, trabalhador_para_dict
# Mantidos para consumidores que já importam as coleções deste módulo.
from db import colecao_obras, colecao_trabalhadores

trabalhadores_bp = Blueprint("trabalhadores", __name__, url_prefix="/trabalhadores")
servico = ServicoTrabalhadores()


@trabalhadores_bp.before_request
@sessao_obrigatoria
def exigir_autenticacao():
    pass


@trabalhadores_bp.errorhandler(ErroTrabalhador)
def tratar_erro_dominio(erro):
    return jsonify(erro.corpo), erro.status


@trabalhadores_bp.errorhandler(PyMongoError)
def tratar_erro_banco(erro):
    current_app.logger.error("Erro ao acessar dados de trabalhadores")
    return jsonify(erro="Não foi possível concluir a operação. Tente novamente"), 503


@trabalhadores_bp.post("/obra/<string:obra_id>/")
def cadastrar_trabalhador_em_obra(obra_id):
    return jsonify(servico.cadastrar(obra_id, request.get_json(silent=True), get_jwt_identity())), 201


@trabalhadores_bp.patch("/<string:trabalhador_id>/")
def atualizar_trabalhador(trabalhador_id):
    return jsonify(servico.atualizar(trabalhador_id, request.get_json(silent=True), get_jwt_identity()))


@trabalhadores_bp.delete("/<string:trabalhador_id>/")
def deletar_trabalhador(trabalhador_id):
    return jsonify(servico.excluir(trabalhador_id, get_jwt_identity()))


@trabalhadores_bp.get("/nome/<string:nome_usuario>/")
def filtrar_usuario_por_nome(nome_usuario):
    return jsonify(servico.filtrar_texto("nome", nome_usuario, get_jwt_identity()))


@trabalhadores_bp.get("/cargo/<string:cargo>/")
def filtrar_usuario_por_cargo(cargo):
    return jsonify(servico.filtrar_texto("cargo", cargo, get_jwt_identity()))


@trabalhadores_bp.get("/obra/<string:obra_id>/")
def filtrar_usuario_por_obra(obra_id):
    return jsonify(servico.por_obra(obra_id, get_jwt_identity()))
