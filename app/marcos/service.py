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


def criar_marco(obra_id, dados):
    try:
        object_id_obra = ObjectId(obra_id)
    except (InvalidId, TypeError):
        raise ErroMarco("ID da obra inválido", 400, ["obra_id"])

    erro = validar_marco(dados)
    if erro:
        mensagem, campos = erro
        raise ErroMarco(mensagem, 422, campos)

    if not repository.obra_existe(object_id_obra):
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

    documento = {
        "obra_id": object_id_obra,
        "nome": dados["nome"].strip(),
        "descricao": dados["descricao"].strip(),
        "inicio_previsto": dados["inicio_previsto"],
        "fim_previsto": dados["fim_previsto"],
        "estado": "a iniciar",
    }
    identifier = repository.inserir_marco(documento)
    return {"id": str(identifier), **{k: v for k, v in documento.items() if k != "obra_id"},
            "obra_id": str(object_id_obra)}
