"""Cadastro recebido da main; aguarda integração ao contrato versionado.

A main importava este blueprint, mas não o registrava. Mantido separado para
preservar o trabalho recebido sem substituir o PATCH do UC-04 nem publicar
uma nova rota de escrita nesta resolução de conflitos.
"""

from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError

from app.obras.obras import criar_obra, validar_obra

obras_bp = Blueprint("obras", __name__, url_prefix="/obras")


@obras_bp.post("")
def cadastrar_obra():
    dados_da_obra = request.get_json(silent=True)
    erro = validar_obra(dados_da_obra)
    if erro:
        return jsonify({"erro": erro})
    try:
        obra = criar_obra(dados_da_obra)
    except PyMongoError:
        current_app.logger.exception("Erro ao cadastrar obra")
        return jsonify({"erro": "Não foi possível salvar a obra"}), 500
    resposta = jsonify(obra)
    resposta.status_code = 201
    resposta.headers["Location"] = f"/obras/{obra['id']}"
    return resposta
