"""Cadastro, consulta e edição descritiva das obras."""

from copy import deepcopy
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .validacoes import validar_criacao_obra

EDITAVEIS = {"nome", "descricao", "localizacao", "cliente"}
CADASTRAVEIS = EDITAVEIS | {"tipo", "inicio", "entrega"}


class ErroObra(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def obra_para_dict(documento):
    obra = {campo: valor for campo, valor in documento.items() if campo != "_id"}
    obra["id"] = str(documento["_id"])
    registro = obra.get("data_registro")
    if isinstance(registro, datetime):
        # O PyMongo pode devolver UTC sem tzinfo; a API sempre informa o fuso.
        if registro.tzinfo is None:
            registro = registro.replace(tzinfo=timezone.utc)
        obra["data_registro"] = registro.isoformat()
    return obra


def criar_obra(dados, autor):
    erro = validar_criacao_obra(dados)
    if erro:
        raise ErroObra(erro["mensagem"], 422, erro["campos"])

    proibidos = sorted(set(dados) - CADASTRAVEIS)
    if proibidos:
        raise ErroObra("Envie somente os campos do cadastro da obra", 422, proibidos)

    documento = deepcopy(dados)
    registro = datetime.now(timezone.utc)
    # BSON armazena milissegundos; POST e consultas devem devolver o mesmo instante.
    registro = registro.replace(microsecond=(registro.microsecond // 1000) * 1000)
    documento.update(
        _id=ObjectId(),
        autor=autor,
        data_registro=registro,
        estado="planejada",
        critica=False,
    )
    repository.salvar_obra(documento)
    return obra_para_dict(documento)


def buscar_obra(identifier):
    try:
        obra_id = ObjectId(identifier)
    except (InvalidId, TypeError):
        raise ErroObra("ID da obra inválido", 400, ["id"])

    documento = repository.buscar_obra_por_id(obra_id)
    if documento is None:
        raise ErroObra("Obra não encontrada", 404, ["id"])
    return obra_para_dict(documento)


def editar_descricao(identifier, dados):
    try:
        obra_id = ObjectId(identifier)
    except (InvalidId, TypeError):
        raise ErroObra("ID da obra inválido", 400, ["id"])

    if not isinstance(dados, dict) or not dados:
        raise ErroObra("Envie um objeto JSON com campos para corrigir", 422, ["corpo"])

    proibidos = sorted(set(dados) - EDITAVEIS)
    if proibidos:
        raise ErroObra(
            "Esta rota aceita apenas nome, descrição, endereço e cliente. "
            "Prazo e conclusão exigem o fluxo de mudança com motivo e histórico.",
            422,
            proibidos,
        )

    invalidos = [
        campo
        for campo, valor in dados.items()
        if not isinstance(valor, str) or not valor.strip()
    ]
    if invalidos:
        raise ErroObra("Os campos enviados devem ser textos não vazios", 422, invalidos)

    documento = repository.atualizar_descricao(obra_id, dados)
    if documento is None:
        raise ErroObra("Obra não encontrada", 404, ["id"])
    return documento
