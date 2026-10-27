"""Contrato HTTP de consulta e acesso às mídias de um avanço."""

from io import BytesIO

from flask import Blueprint, current_app, jsonify, redirect, send_file, url_for
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria

from .midias import (
    ErroMidia,
    abrir_conteudo,
    buscar_midia,
    formato_para_resposta,
    listar_midias,
    nome_para_resposta,
)


midias_bp = Blueprint("midias", __name__)


@midias_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    # Vale também para o acesso direto ao arquivo, fora da interface React.
    pass


def _erro(erro):
    return (
        jsonify(codigo=erro.codigo, mensagem=str(erro), campos=erro.campos),
        erro.status,
    )


def _com_conteudo(midia):
    # O arquivo é alcançado por rota própria do Flask, nunca por endereço do
    # provedor: sem a sessão da construtora o link não serve para nada.
    return {**midia, "conteudo": url_for("midias.obter_conteudo", midia_id=midia["id"])}


@midias_bp.get("/avancos/<string:avanco_id>/midias")
def consultar_midias_do_avanco(avanco_id):
    try:
        midias = listar_midias(avanco_id)
    except ErroMidia as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante consulta de mídias do avanço")
        return jsonify(
            codigo="FALHA_NO_BANCO",
            mensagem="Não foi possível consultar as mídias do avanço",
        ), 500

    return jsonify(midias=[_com_conteudo(midia) for midia in midias]), 200


@midias_bp.get("/midias/<string:midia_id>")
def consultar_midia(midia_id):
    try:
        midia = buscar_midia(midia_id)
    except ErroMidia as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante consulta de mídia")
        return jsonify(
            codigo="FALHA_NO_BANCO", mensagem="Não foi possível consultar a mídia"
        ), 500

    return jsonify(_com_conteudo(midia)), 200


@midias_bp.get("/midias/<string:midia_id>/conteudo")
def obter_conteudo(midia_id):
    try:
        documento, acesso = abrir_conteudo(midia_id)
    except ErroMidia as erro:
        return _erro(erro)
    except PyMongoError:
        current_app.logger.error("Falha no banco durante acesso ao arquivo da mídia")
        return jsonify(
            codigo="FALHA_NO_BANCO", mensagem="Não foi possível abrir a mídia"
        ), 500

    if acesso.url_temporaria:
        # Endereço de validade curta, já conferida pelo serviço.
        resposta = redirect(acesso.url_temporaria, code=302)
    else:
        formato, embutido = formato_para_resposta(documento)
        resposta = send_file(
            BytesIO(acesso.conteudo),
            mimetype=formato,
            as_attachment=not embutido,
            download_name=nome_para_resposta(documento),
        )

    # Cópia protegida não fica em cache compartilhado nem é adivinhada pelo tipo.
    resposta.headers["Cache-Control"] = "private, no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta
