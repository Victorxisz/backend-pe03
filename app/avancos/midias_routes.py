"""Metadados e conteúdo das mídias, protegidos pela sessão da construtora."""

from io import BytesIO

from flask import Blueprint, current_app, jsonify, send_file, url_for
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from .midias import ErroMidia
from .acesso_midias import (
    abrir_conteudo, buscar_midia, formato_para_resposta, listar_midias, nome_para_resposta,
)


midias_bp = Blueprint("midias", __name__)


@midias_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@midias_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@midias_bp.errorhandler(ErroMidia)
def responder_erro(erro):
    return jsonify(codigo=erro.codigo, mensagem=str(erro), campos=erro.campos), erro.status


@midias_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante consulta de mídia")
    return jsonify(codigo="FALHA_NO_BANCO", mensagem="Não foi possível consultar a mídia"), 500


def _com_conteudo(midia):
    return {**midia, "conteudo": url_for("midias.obter_conteudo", midia_id=midia["id"])}


@midias_bp.get("/avancos/<string:avanco_id>/midias")
def consultar_midias_do_avanco(avanco_id):
    return jsonify(midias=[_com_conteudo(midia) for midia in listar_midias(avanco_id)]), 200


@midias_bp.get("/midias/<string:midia_id>")
def consultar_midia(midia_id):
    return jsonify(_com_conteudo(buscar_midia(midia_id))), 200


@midias_bp.get("/midias/<string:midia_id>/conteudo")
def obter_conteudo(midia_id):
    documento, conteudo = abrir_conteudo(midia_id)
    mime, embutido = formato_para_resposta(documento)
    return send_file(BytesIO(conteudo), mimetype=mime, as_attachment=not embutido,
                     download_name=nome_para_resposta(documento))
