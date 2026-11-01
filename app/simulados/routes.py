"""Contrato HTTP de UC-21: leitura dos exemplos simulados de uma obra.

Apenas `GET`. Os demais métodos existem para recusar de forma explícita e em
JSON qualquer tentativa de enviar avaliação, dúvida ou mensagem como comprador
(CT-105): RN-10 não cria perfil, login ou formulário desses participantes.
"""

from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .service import ErroSimulado, consultar_feedback_simulado

CAMINHO = "/obras/<string:obra_id>/feedback-simulado"
METODOS_RECUSADOS = ("POST", "PUT", "PATCH", "DELETE")
PERMITIDOS = "GET, HEAD, OPTIONS"
RECUSA = ("O MVP não recebe avaliações, dúvidas ou mensagens de comprador e "
          "engenheiro. Os exemplos são pré-carregados pelo procedimento de "
          "demonstração e esta rota é somente de leitura.")

simulados_bp = Blueprint("simulados", __name__)


@simulados_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@simulados_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@simulados_bp.errorhandler(ErroSimulado)
def responder_erro(erro):
    return jsonify(erro.corpo()), erro.status


@simulados_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante consulta dos exemplos simulados")
    return jsonify(mensagem="Não foi possível concluir a solicitação", campos=[]), 503


@simulados_bp.get(CAMINHO)
def feedback_simulado(obra_id):
    return jsonify(consultar_feedback_simulado(obra_id, request.args)), 200


@simulados_bp.route(CAMINHO, methods=list(METODOS_RECUSADOS))
def recusar_interacao(obra_id):
    """Recusa inequívoca: não há interação real de comprador ou engenheiro."""
    return jsonify(mensagem=RECUSA, campos=[], codigo="INTERACAO_NAO_DISPONIVEL",
                   simulado=True), 405, {"Allow": PERMITIDOS}
