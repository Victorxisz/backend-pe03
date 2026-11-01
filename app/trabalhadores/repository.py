"""Persistência dos trabalhadores e consulta de obras para seus vínculos."""

import db


class RepositorioTrabalhadores:
    def __init__(self, trabalhadores=None, obras=None):
        self.trabalhadores = trabalhadores if trabalhadores is not None else db.colecao_trabalhadores
        self.obras = obras if obras is not None else db.colecao_obras

    def buscar_obra(self, identificador):
        return self.obras.find_one({"_id": identificador})

    def obras_existentes(self, identificadores):
        return list(self.obras.find({"_id": {"$in": identificadores}}))

    def inserir(self, documento):
        return self.trabalhadores.insert_one(documento).inserted_id

    def buscar(self, identificador):
        return self.trabalhadores.find_one({"_id": identificador})

    def atualizar(self, identificador, campos):
        return self.trabalhadores.update_one({"_id": identificador}, {"$set": campos}).matched_count

    def excluir(self, identificador):
        return self.trabalhadores.delete_one({"_id": identificador}).deleted_count

    def consultar(self, filtro):
        return list(self.trabalhadores.find(filtro))

    def _vinculo(self, obra_id):
        # Vínculos antigos podem ter sido gravados como ObjectId.
        return {"$in": [str(obra_id), obra_id]}

    def vinculados_a_obra(self, obra_id, *, session=None):
        return list(self.trabalhadores.find(
            {"obras": self._vinculo(obra_id)}, session=session).sort("_id", 1))

    def desvincular_obra(self, obra_id, *, session=None):
        """Retira só o vínculo: preserva o cadastro e as outras obras (CT-100)."""
        return self.trabalhadores.update_many(
            {"obras": self._vinculo(obra_id)},
            {"$pull": {"obras": self._vinculo(obra_id)}},
            session=session,
        ).modified_count
