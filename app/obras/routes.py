"""Contrato HTTP do cadastro, consulta e edição de obras."""

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity
from app.auth.permissions import sessao_obrigatoria
from pymongo.errors import PyMongoError

from app.exclusoes import ErroExclusao
from .exclusoes import excluir_obra
from .service import ErroObra, ServicoObras

servico = ServicoObras()
buscar_obra = servico.buscar_obra
criar_obra = servico.criar_obra
editar_descricao = servico.editar_descricao
listar_obras = servico.listar_obras

obras_bp = Blueprint("obras", __name__, url_prefix="/obras")
@obras_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@obras_bp.post("")
def cadastrar_obra():
    try:
        obra = criar_obra(request.get_json(silent=True), get_jwt_identity())
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante cadastro da obra")
        return jsonify(mensagem="Não foi possível salvar a obra"), 500

    resposta = jsonify(obra)
    resposta.status_code = 201
    resposta.headers["Location"] = url_for("obras.consultar_obra", obra_id=obra["id"])
    return resposta


@obras_bp.get("/<string:obra_id>")
def consultar_obra(obra_id):
    try:
        obra = buscar_obra(obra_id)
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante consulta da obra")
        return jsonify(mensagem="Não foi possível consultar a obra"), 500
    return jsonify(obra), 200


@obras_bp.get("")
def consultar_obras():
    try:
        obras = listar_obras(request.args)
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante listagem de obras")
        return jsonify(mensagem="Não foi possível consultar as obras"), 500

    filtros_aplicados = {}

    for campo in request.args:
        valor = request.args[campo].strip()

        if valor:
            filtros_aplicados[campo] = valor

    if obras:
        situacao = "com_resultados"
    elif filtros_aplicados:
        situacao = "sem_resultados"
    else:
        situacao = "lista_vazia"

    return jsonify(
            obras=obras,
            situacao=situacao,
            filtros_aplicados=filtros_aplicados,
        ), 200


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


@obras_bp.delete("/<string:obra_id>")
def excluir_obra_e_dependentes(obra_id):
    """UC-17: só responde 204 com a cascata inteira concluída."""
    try:
        excluir_obra(obra_id, request.get_json(silent=True), get_jwt_identity())
    except ErroExclusao as erro:
        return jsonify(erro.corpo()), erro.status
    except PyMongoError:
        current_app.logger.exception("Falha no banco durante exclusão da obra")
        return jsonify(mensagem="Não foi possível concluir a exclusão da obra",
                       codigo="FALHA_NO_BANCO"), 503
    except Exception:
        # A transação não foi confirmada; a resposta não pode parecer sucesso.
        current_app.logger.exception("Falha inesperada durante exclusão da obra")
        return jsonify(mensagem="Não foi possível concluir a exclusão da obra",
                       codigo="EXCLUSAO_NAO_CONCLUIDA"), 500
    return "", 204


@obras_bp.patch("/<string:obra_id>/estado")
def alterar_estado(obra_id):
    try:
        obra = servico.alterar_estado(obra_id, request.get_json(silent=True), get_jwt_identity())
    except ErroObra as erro:
        return jsonify(mensagem=str(erro), campos=erro.campos), erro.status
    except PyMongoError:
        current_app.logger.error("Falha no banco durante alteração de estado da obra")
        return jsonify(mensagem="Não foi possível alterar o estado da obra"), 500
    return jsonify(obra), 200
