"""Regras de negócio do cadastro de marcos."""

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .validacoes import validar_marco


class ErroMarco(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def criar_marco(obra_id, dados_do_marco):
    obra_id = identificar_obra(obra_id)
    validar_dados_do_marco(dados_do_marco)
    garantir_obra_existente(obra_id)
    marco = preparar_marco_para_cadastro(obra_id, dados_do_marco)
    id_marco = repository.inserir_marco(marco)
    return montar_resposta_do_marco(marco, id_marco)


def identificar_obra(obra_id):
    try:
        return ObjectId(obra_id)
    except (InvalidId, TypeError):
        raise ErroMarco("ID da obra inválido", 400, ["obra_id"])


def validar_dados_do_marco(dados_do_marco):
    erro = validar_marco(dados_do_marco)
    if erro:
        mensagem, campos = erro
        raise ErroMarco(mensagem, 422, campos)


def garantir_obra_existente(obra_id):
    if not repository.obra_existe(obra_id):
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])


def preparar_marco_para_cadastro(obra_id, dados_do_marco):
    return {
        "obra_id": obra_id,
        "nome": dados_do_marco["nome"].strip(),
        "descricao": dados_do_marco["descricao"].strip(),
        "inicio_previsto": dados_do_marco["inicio_previsto"],
        "fim_previsto": dados_do_marco["fim_previsto"],
        "estado": "a iniciar",
    }


def montar_resposta_do_marco(marco, id_marco):
    return {
        "id": str(id_marco),
        "obra_id": str(marco["obra_id"]),
        "nome": marco["nome"],
        "descricao": marco["descricao"],
        "inicio_previsto": marco["inicio_previsto"],
        "fim_previsto": marco["fim_previsto"],
        "estado": marco["estado"],
    }
