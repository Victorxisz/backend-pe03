"""Criação e consulta autenticadas de avanços."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from .midias import ErroMidia, ResultadoPersistenciaIndeterminado
from .service import consultar_avanco, consultar_avancos, criar_avanco
from .validacoes import ErroAvanco

avancos_bp = Blueprint("avancos", __name__)


@avancos_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@avancos_bp.errorhandler(ErroAvanco)
@avancos_bp.errorhandler(ErroMidia)
def erro_validacao(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@avancos_bp.errorhandler(ErroArmazenamento)
def erro_armazenamento(erro):
    if isinstance(erro, ErroLimpeza):
        current_app.logger.error(
            "Falha na limpeza de mídias; referências pendentes: %s", erro.pendentes
        )
    return jsonify(mensagem=str(erro), campos=["midias"]), erro.status


@avancos_bp.errorhandler(ResultadoPersistenciaIndeterminado)
def erro_indeterminado(erro):
    return jsonify(mensagem=str(erro), campos=["banco"]), 503


@avancos_bp.errorhandler(PyMongoError)
def erro_banco(erro):
    current_app.logger.error("Falha no banco durante operação de avanço")
    return jsonify(mensagem="Não foi possível concluir a operação de avanço"), 500


@avancos_bp.post("/marcos/<string:marco_id>/avancos")
def cadastrar_avanco(marco_id):
    if request.mimetype != "multipart/form-data":
        raise ErroAvanco("Envie multipart/form-data", 415, ["corpo"])
    # A aplicação Flask 3.0 não permite limitar o corpo por rota no parser.
    # Exigimos tamanho declarado antes de acessar request.form/request.files.
    limite = current_app.config.get("UC09_MAX_REQUEST_BYTES", 110 * 1024 * 1024)
    if request.content_length is None:
        raise ErroAvanco("Informe o tamanho da requisição", 411, ["corpo"])
    if request.content_length > limite:
        raise ErroAvanco("O lote excede o tamanho permitido", 413, ["midias"])
    campos = request.form.to_dict(flat=True)
    if any(len(request.form.getlist(chave)) != 1 for chave in request.form):
        raise ErroAvanco("Não repita campos", 422, ["corpo"])
    if set(request.files) - {"midias"}:
        raise ErroAvanco("Use o campo midias para os arquivos", 422, ["midias"])
    if len(request.files.getlist("midias")) > 5:
        raise ErroAvanco("Envie no máximo cinco arquivos", 413, ["midias"])
    resultado = criar_avanco(
        marco_id,
        campos,
        request.files.getlist("midias"),
        get_jwt_identity(),
        request.headers.get("Idempotency-Key"),
    )
    resposta = jsonify(resultado)
    resposta.status_code = 201
    resposta.headers["Location"] = f"/avancos/{resultado['id']}"
    return resposta


@avancos_bp.get("/marcos/<string:marco_id>/avancos")
def listar_avancos(marco_id):
    return jsonify(avancos=consultar_avancos(marco_id)), 200


@avancos_bp.get("/avancos/<string:avanco_id>")
def obter_avanco(avanco_id):
    return jsonify(consultar_avanco(avanco_id)), 200
