"""Sessões da conta pré-configurada; rotas antigas permanecem compatíveis."""
from flask import Blueprint, jsonify
from app.auth.permissions import sessao_obrigatoria

from construtora import login_construtora, logout_construtora
from app.auth.service import consultar_sessao

sessoes_bp = Blueprint("sessoes", __name__, url_prefix="/sessoes")


@sessoes_bp.post("")
def criar_sessao():
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
