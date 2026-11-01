"""Validação do contexto e representação pública dos feedbacks fictícios."""

from bson import ObjectId
from bson.errors import InvalidId

from app.serializacao import serializar
from .repository import RepositorioSimulados


class ErroSimulado(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status, self.campos = status, list(campos)


def identificar(valor, campo):
    try:
        if not isinstance(valor, (str, ObjectId)):
            raise TypeError
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroSimulado("Identificador inválido", 400, [campo]) from None


class ServicoSimulados:
    def __init__(self, repositorio=None):
        self.repositorio = repositorio if repositorio is not None else RepositorioSimulados()

    def contexto(self, obra_id, autor, marco_id=None, atualizacao_id=None):
        obra_id = identificar(obra_id, "obra_id")
        obra = self.repositorio.buscar("tbl_obras", obra_id)
        if obra is None or (obra.get("autor") and str(obra["autor"]) != str(autor)):
            raise ErroSimulado("Obra não encontrada", 404, ["obra_id"])
        if marco_id is not None and atualizacao_id is not None:
            raise ErroSimulado("Escolha marco ou atualização", 422, ["marco_id", "atualizacao_id"])
        if atualizacao_id is not None:
            alvo_id = identificar(atualizacao_id, "atualizacao_id")
            avanco = self.repositorio.buscar("tbl_avancos", alvo_id)
            if avanco is None or avanco.get("estado") != "publicado" or not avanco.get("publicacao"):
                raise ErroSimulado("Atualização não encontrada", 404, ["atualizacao_id"])
            marco = self.repositorio.buscar("tbl_marcos", avanco.get("marco_id"))
            if marco is None or marco.get("obra_id") != obra_id:
                raise ErroSimulado("Atualização não encontrada nesta obra", 404, ["atualizacao_id"])
            return obra_id, "atualizacao", alvo_id
        if marco_id is not None:
            alvo_id = identificar(marco_id, "marco_id")
            marco = self.repositorio.buscar("tbl_marcos", alvo_id)
            if marco is None or marco.get("obra_id") != obra_id:
                raise ErroSimulado("Marco não encontrado nesta obra", 404, ["marco_id"])
            return obra_id, "marco", alvo_id
        return obra_id, "obra", obra_id

    def consultar(self, obra_id, autor, **filtros):
        obra_id, tipo, alvo_id = self.contexto(obra_id, autor, **filtros)
        # Lista fechada: metadados internos da carga nunca chegam ao cliente.
        return serializar([
            {"id": item["_id"], "obra_id": obra_id, "alvo": item["alvo"],
             "tipo": item["tipo"], "texto": item["texto"], "cliente": item["cliente"],
             "origem": "simulado", "simulado": True}
            for item in self.repositorio.listar(obra_id, tipo, alvo_id)
        ])
