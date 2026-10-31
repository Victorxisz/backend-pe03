"""Sessões da conta pré-configurada; rotas antigas permanecem compatíveis."""
from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError
from app.auth.permissions import sessao_obrigatoria

from construtora import login_construtora, logout_construtora, responder_erro, responder_falha_banco
from app.construtoras.service import ErroConstrutora
from app.auth.service import consultar_sessao

sessoes_bp = Blueprint("sessoes", __name__, url_prefix="/sessoes")
sessoes_bp.register_error_handler(ErroConstrutora, responder_erro)
sessoes_bp.register_error_handler(PyMongoError, responder_falha_banco)


@sessoes_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@sessoes_bp.post("")
def criar_sessao():
    if not current_app.config.get("CONSTRUTORA_ID"):
        return jsonify(erro="Conta da construtora não configurada"), 503
    return login_construtora()


@sessoes_bp.get("/atual")
@sessao_obrigatoria
def sessao_atual():
    conta = consultar_sessao()
    if conta is None:
        return jsonify(erro="Entre em uma conta ativa"), 401
    return jsonify(construtora=conta), 200


@sessoes_bp.delete("/atual")
def encerrar_sessao():
    return logout_construtora()
