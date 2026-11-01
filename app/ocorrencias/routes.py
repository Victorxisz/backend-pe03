"""Rotas de cadastro, consulta e aceitação de ocorrências."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.auth.permissions import sessao_obrigatoria
from app.avancos.midias import ErroMidia, ResultadoPersistenciaIndeterminado
from app.integracoes.armazenamento import ErroArmazenamento
from .service import ErroOcorrencia, ServicoOcorrencias
from app.exclusoes import ErroExclusao
from app.serializacao import serializar

ocorrencias_bp = Blueprint("ocorrencias", __name__)
servico = ServicoOcorrencias()


@ocorrencias_bp.errorhandler(ErroExclusao)
def responder_exclusao(erro):
    resposta = jsonify(erro.corpo())
    if erro.status == 503:
        resposta.headers["Retry-After"] = "30"
    return resposta, erro.status


@ocorrencias_bp.delete("/ocorrencias/<string:ocorrencia_id>")
@sessao_obrigatoria
def excluir_ocorrencia(ocorrencia_id):
    from app.exclusao_registros import ler_contexto
    servico.excluir(ocorrencia_id, ler_contexto(), get_jwt_identity())
    return "", 204


@ocorrencias_bp.get("/ocorrencias/<string:ocorrencia_id>/exclusao")
@sessao_obrigatoria
def previa_exclusao(ocorrencia_id):
    from app.exclusao_registros import ler_contexto
    return jsonify(serializar(servico.excluir(ocorrencia_id, ler_contexto(), get_jwt_identity(), previa=True)))


def _erro(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@ocorrencias_bp.errorhandler(ErroOcorrencia)
def responder_erro(erro):
    return _erro(erro)


@ocorrencias_bp.errorhandler(ErroMidia)
def responder_midia(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos, codigo=erro.codigo), erro.status


@ocorrencias_bp.errorhandler(ErroArmazenamento)
@ocorrencias_bp.errorhandler(ResultadoPersistenciaIndeterminado)
def responder_armazenamento(erro):
    return jsonify(mensagem="Não foi possível confirmar o cadastro; consulte a lista antes de reenviar"), 503


@ocorrencias_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@ocorrencias_bp.post("/obras/<string:obra_id>/ocorrencias")
@sessao_obrigatoria
def cadastrar_ocorrencia(obra_id):
    arquivos = []
    if request.mimetype == "multipart/form-data":
        if (set(request.files) - {"midias"}
                or any(len(request.form.getlist(campo)) != 1 for campo in request.form)):
            raise ErroOcorrencia("Campos de formulário inválidos ou repetidos", 422, ["corpo"])
        dados = request.form.to_dict()
        arquivos = [arquivo for arquivo in request.files.getlist("midias") if arquivo.filename]
    elif request.is_json:
        dados = request.get_json(silent=True)
    else:
        raise ErroOcorrencia("Use JSON ou multipart/form-data", 415, ["corpo"])
    item = servico.cadastrar(obra_id, dados, get_jwt_identity(), arquivos)
    return jsonify(item), 201, {"Location": f"/ocorrencias/{item['id']}"}


@ocorrencias_bp.get("/obras/<string:obra_id>/ocorrencias")
@sessao_obrigatoria
def listar_ocorrencias(obra_id):
    return jsonify(servico.listar(obra_id, get_jwt_identity()))


@ocorrencias_bp.get("/ocorrencias/<string:ocorrencia_id>")
@sessao_obrigatoria
def consultar_ocorrencia(ocorrencia_id):
    return jsonify(servico.consultar(ocorrencia_id, get_jwt_identity()))


@ocorrencias_bp.patch("/ocorrencias/<string:ocorrencia_id>")
@sessao_obrigatoria
def atualizar_ocorrencia(ocorrencia_id):
    if not request.is_json:
        raise ErroOcorrencia("Use application/json para atualizar a ocorrência", 415, ["corpo"])
    return jsonify(servico.atualizar(ocorrencia_id, request.get_json(silent=True), get_jwt_identity()))


@ocorrencias_bp.post("/ocorrencias/<string:ocorrenciaId>/aceitacoes")
@sessao_obrigatoria
def registrar_aceitacao(ocorrenciaId):
    if not request.is_json:
        raise ErroOcorrencia("Use application/json para registrar a aceitação", 415, ["corpo"])
    item, repetida = servico.aceitar(
        ocorrenciaId, request.get_json(silent=True), get_jwt_identity(),
        request.headers.get("Idempotency-Key"),
    )
    return jsonify(item), 200 if repetida else 201, {"Location": request.path}


@ocorrencias_bp.get("/ocorrencias/<string:ocorrenciaId>/aceitacoes")
@sessao_obrigatoria
def consultar_aceitacoes(ocorrenciaId):
    return jsonify(servico.listar_aceitacoes(ocorrenciaId, get_jwt_identity())), 200
