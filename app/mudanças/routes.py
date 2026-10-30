"""POST /obras/{obra_id}/mudancas: aplica uma decisão autenticada."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from app.auth.permissions import sessao_obrigatoria
from app.marcos.service import ErroMarco
from app.obras.service import ErroObra
from .service import ErroMudanca, ServicoMudancas

mudancas_bp = Blueprint("mudancas", __name__)
servico = ServicoMudancas()


@mudancas_bp.post("/obras/<string:obra_id>/mudancas")
@sessao_obrigatoria
def aplicar_mudanca(obra_id):
    try:
        resultado = servico.aplicar(obra_id, request.get_json(silent=True), get_jwt_identity())
    except (ErroMudanca, ErroMarco, ErroObra) as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos,
                       **getattr(erro, "detalhes", {})), erro.status
    except Exception:
        current_app.logger.exception("Falha ao persistir mudança")
        return jsonify(mensagem="Não foi possível aplicar a mudança"), 500
    return jsonify(resultado), 200
