"""Rotas autenticadas de cadastro, consulta e manutenção de avanços."""

import json

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from .midias import ErroMidia, ResultadoPersistenciaIndeterminado
from .service import ErroAvanco, criar_avanco, consultar_avanco, consultar_avancos, excluir_avanco, editar_rascunho
from app.exclusoes import ErroExclusao
from app.serializacao import serializar
from .versoes import consultar_versoes
from .correcoes import corrigir_publicacao
from . import repository as avancos_repository

avancos_bp = Blueprint("avancos", __name__)


@avancos_bp.errorhandler(ErroExclusao)
def responder_exclusao(erro):
    resposta = jsonify(erro.corpo())
    if erro.status == 503:
        resposta.headers["Retry-After"] = "30"
    return resposta, erro.status


@avancos_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@avancos_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@avancos_bp.errorhandler(ErroAvanco)
@avancos_bp.errorhandler(ErroMidia)
def responder_erro(erro):
    corpo = {"mensagem": str(erro), "campos": getattr(erro, "campos", ["midias"])}
    codigo = getattr(erro, "codigo", None)
    if codigo:
        corpo["codigo"] = codigo
    pendentes = getattr(erro, "pendentes", None)
    if pendentes is not None:
        corpo["pendentes"] = pendentes
    resposta = jsonify(corpo)
    if getattr(erro, "status", 500) == 503 or codigo == "CONFLITO_EXCLUSAO":
        resposta.headers["Retry-After"] = "30"
    return resposta, getattr(erro, "status", 500)


@avancos_bp.errorhandler(ErroArmazenamento)
@avancos_bp.errorhandler(ErroLimpeza)
def responder_erro_armazenamento(erro):
    if isinstance(erro, ErroLimpeza):
        current_app.logger.error("Falha na limpeza de mídias; referências pendentes para reconciliação")
    return jsonify(mensagem=str(erro), codigo=getattr(erro, "codigo", "FALHA_ARMAZENAMENTO"), campos=["midias"]), getattr(erro, "status", 503)


@avancos_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.exception("Falha no banco durante operação de avanço")
    return jsonify(mensagem="Não foi possível concluir a solicitação", codigo="FALHA_NO_BANCO", campos=[]), 503


@avancos_bp.errorhandler(ResultadoPersistenciaIndeterminado)
def responder_resultado_indeterminado(erro):
    return jsonify(mensagem=str(erro), campos=["banco"]), 503


def ler_multipart():
    if request.mimetype != "multipart/form-data":
        raise ErroAvanco("Envie multipart/form-data", 415, ["corpo"])
    if request.content_length is None:
        raise ErroAvanco("Informe o tamanho da requisição", 411, ["corpo"])
    if request.content_length > current_app.config.get("UC09_MAX_REQUEST_BYTES", 110 * 1024 * 1024):
        raise ErroAvanco("O lote excede o tamanho permitido", 413, ["midias"])
    if any(len(request.form.getlist(chave)) != 1 for chave in request.form):
        raise ErroAvanco("Não repita campos", 422, ["corpo"])
    if set(request.files) - {"midias"}:
        raise ErroAvanco("Use o campo midias para os arquivos", 422, ["midias"])
    arquivos = request.files.getlist("midias")
    if len(arquivos) > 5:
        raise ErroAvanco("Envie no máximo cinco arquivos", 413, ["midias"])
    return request.form.to_dict(), arquivos


@avancos_bp.post("/marcos/<string:marco_id>/avancos")
def cadastrar_avanco(marco_id):
    dados, arquivos = ler_multipart()
    avanco = criar_avanco(marco_id, dados, arquivos, get_jwt_identity(), chave=request.headers.get("Idempotency-Key"))
    resposta = jsonify(avanco)
    resposta.status_code = 201
    resposta.headers["Location"] = url_for("avancos.consultar_avanco_route", avanco_id=avanco["id"])
    return resposta


@avancos_bp.get("/marcos/<string:marco_id>/avancos")
def listar_avancos(marco_id):
    return jsonify(consultar_avancos(marco_id)), 200


@avancos_bp.get("/avancos/<string:avanco_id>")
def consultar_avanco_route(avanco_id):
    return jsonify(consultar_avanco(avanco_id)), 200


@avancos_bp.get("/avancos/<string:avanco_id>/versoes")
def listar_versoes(avanco_id):
    return jsonify(consultar_versoes(avanco_id)), 200


@avancos_bp.patch("/avancos/<string:avanco_id>")
def editar_avanco_route(avanco_id):
    if request.is_json:
        dados, arquivos = request.get_json(silent=True), []
    else:
        dados, arquivos = ler_multipart()
        if "midias_manter" in dados:
            try:
                dados["midias_manter"] = json.loads(dados["midias_manter"])
            except (TypeError, ValueError):
                raise ErroAvanco("midias_manter deve ser uma lista JSON de IDs", 422, ["midias_manter"]) from None
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        documento = avancos_repository.buscar_avanco(ObjectId(avanco_id))
    except (InvalidId, TypeError):
        documento = None
    if documento is not None and documento.get("estado") == "publicado":
        if not documento.get("publicacao"):
            raise ErroAvanco("Publicação inconsistente", 409, ["publicacao"])
        return jsonify(corrigir_publicacao(avanco_id, dados, get_jwt_identity(), arquivos)), 200
    return jsonify(editar_rascunho(avanco_id, dados, arquivos)), 200


@avancos_bp.delete("/avancos/<string:avanco_id>")
def excluir(avanco_id):
    excluir_avanco(avanco_id, contexto_exclusao(), get_jwt_identity())
    return "", 204


def contexto_exclusao():
    from app.exclusao_registros import ler_contexto
    return ler_contexto()


@avancos_bp.get("/avancos/<string:avanco_id>/exclusao")
def previa_exclusao(avanco_id):
    return jsonify(serializar(excluir_avanco(avanco_id, contexto_exclusao(), get_jwt_identity(), previa=True)))
