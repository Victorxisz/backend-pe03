"""Persistência dos exemplos e sua participação nas cascatas existentes."""

import db


class RepositorioSimulados:
    def __init__(self, banco=None):
        self.banco = banco if banco is not None else db.banco_dados

    def buscar(self, colecao, identificador):
        return self.banco[colecao].find_one({"_id": identificador})

    def listar(self, obra_id, tipo, alvo_id):
        return list(self.banco["tbl_feedback_simulado"].find({
            "obra_id": obra_id, "alvo.tipo": tipo, "alvo.id": alvo_id,
            "origem": "simulado",
        }).sort("_id", 1))

    def remover(self, filtro, *, session=None):
        return self.banco["tbl_feedback_simulado"].delete_many(filtro, session=session)

    def contar(self, filtro):
        return self.banco["tbl_feedback_simulado"].count_documents(filtro)
