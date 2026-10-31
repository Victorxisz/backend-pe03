"""Rotas para registrar e consultar aceitações sem solução."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .service import ErroOcorrencia, ServicoOcorrencias

ocorrencias_bp = Blueprint("ocorrencias", __name__)
servico = ServicoOcorrencias()


def _erro(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@ocorrencias_bp.post("/ocorrencias/<string:ocorrenciaId>/aceitacoes")
@sessao_obrigatoria
def registrar_aceitacao(ocorrenciaId):
    try:
        item, repetida = servico.aceitar(
            ocorrenciaId, request.get_json(silent=True), get_jwt_identity(),
            request.headers.get("Idempotency-Key"),
        )
    except ErroOcorrencia as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.exception("Falha ao registrar aceitação da ocorrência")
        return jsonify(mensagem="Não foi possível registrar a aceitação"), 500
    return jsonify(item), 200 if repetida else 201


@ocorrencias_bp.get("/ocorrencias/<string:ocorrenciaId>/aceitacoes")
@sessao_obrigatoria
def consultar_aceitacoes(ocorrenciaId):
    try:
        return jsonify(servico.listar_aceitacoes(ocorrenciaId)), 200
    except ErroOcorrencia as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.exception("Falha ao consultar aceitações da ocorrência")
        return jsonify(mensagem="Não foi possível consultar as aceitações"), 500
