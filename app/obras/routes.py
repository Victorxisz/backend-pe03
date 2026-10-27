"""Contrato HTTP da edição descritiva."""

from flask import Blueprint, current_app, jsonify, request
from app.auth.permissions import sessao_obrigatoria
from pymongo.errors import PyMongoError

from .service import ErroObra, editar_descricao

obras_bp = Blueprint("obras", __name__, url_prefix="/obras")
@obras_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@obras_bp.patch("/<string:obra_id>")
def corrigir_descricao(obra_id):
    try:
        documento = editar_descricao(obra_id, request.get_json(silent=True))
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        # Não expõe mensagens do driver, URI ou credenciais.
        current_app.logger.error("Falha no banco durante edição descritiva da obra")
        return jsonify(mensagem="Não foi possível salvar a correção da obra"), 500

    return (
        jsonify(
            id=str(documento["_id"]),
            **{
                campo: documento.get(campo)
                for campo in ("nome", "descricao", "localizacao", "cliente")
            },
        ),
        200,
    )
