"""Regras da edição descritiva; prazo e conclusão pertencem ao fluxo de mudanças."""

from bson import ObjectId
from bson.errors import InvalidId

from . import repository

EDITAVEIS = {"nome", "descricao", "localizacao", "cliente"}


class ErroObra(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


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
