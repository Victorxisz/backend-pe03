"""Regras de negócio de marcos."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .validacoes import validar_alteracao_estado, validar_marco


class ErroMarco(Exception):
    def __init__(self, mensagem, status, campos=(), detalhes=None):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.detalhes = detalhes or {}


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


def alterar_estado_marco(marco_id, dados, autor):
    try:
        object_id = ObjectId(marco_id)
    except (InvalidId, TypeError):
        raise ErroMarco("ID do marco inválido", 400, ["marco_id"])

    erro = validar_alteracao_estado(dados)
    if erro:
        mensagem, campos = erro
        raise ErroMarco(mensagem, 422, campos)

    marco = repository.buscar_marco(object_id)
    if not marco:
        raise ErroMarco("Marco não encontrado", 404, ["marco_id"])

    novo_estado = dados["estado"]
    pendentes = repository.dependencias_pendentes(marco) if novo_estado == "concluído" else []
    if pendentes and dados.get("confirmar_dependencias") is not True:
        raise ErroMarco("Há dependências pendentes", 409, [], {
            "codigo": "DEPENDENCIAS_PENDENTES", "dependencias": pendentes
        })

    anterior = marco.get("estado", "a iniciar")
    evento = {
        "tipo": "estado_marco",
        "alvo": {"tipo": "marco", "id": object_id},
        "estado_anterior": anterior,
        "estado_novo": novo_estado,
        "motivo": dados["motivo"].strip(),
        "autor": autor,
        "instante": datetime.now(timezone.utc),
        "confirmou_dependencias_pendentes": bool(pendentes and dados.get("confirmar_dependencias") is True),
        "dependencias_pendentes": pendentes,
    }
    try:
        repository.salvar_estado_com_historico(object_id, anterior, novo_estado, evento)
    except Exception:
        raise
    return {"id": str(object_id), "estado": novo_estado}
