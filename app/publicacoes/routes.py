"""Contrato HTTP do UC-10, com a mesma autenticação dos demais módulos."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .service import ErroPublicacao, consultar_previa, consultar_publicacoes, publicar_avanco

publicacoes_bp = Blueprint("publicacoes", __name__)


@publicacoes_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@publicacoes_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@publicacoes_bp.errorhandler(ErroPublicacao)
def responder_erro(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@publicacoes_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante publicação ou consulta da prévia")
    return jsonify(mensagem="Não foi possível concluir a solicitação", campos=[]), 503


@publicacoes_bp.post("/avancos/<string:avanco_id>/publicacoes")
def publicar(avanco_id):
    # Autor, instante e conteúdo são obtidos no servidor, nunca aceitos do cliente.
    if request.get_data() and request.get_json(silent=True) != {}:
        raise ErroPublicacao("Envie um objeto vazio ou nenhum corpo para confirmar publicação", 422, ["corpo"])
    publicacao, criada = publicar_avanco(avanco_id, get_jwt_identity())
    return jsonify(publicacao), 201 if criada else 200, {
        "Location": url_for("publicacoes.listar", avanco_id=avanco_id)
    }


@publicacoes_bp.get("/avancos/<string:avanco_id>/publicacoes")
def listar(avanco_id):
    return jsonify(publicacoes=consultar_publicacoes(avanco_id))


@publicacoes_bp.get("/obras/<string:obra_id>/previa")
def previa(obra_id):
    return jsonify(atualizacoes=consultar_previa(obra_id))
