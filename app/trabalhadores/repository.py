"""Persistência dos trabalhadores e consulta de obras para seus vínculos."""

import db
from bson import ObjectId


class RepositorioTrabalhadores:
    def __init__(self, trabalhadores=None, obras=None, ocorrencias=None, cliente=None):
        self.trabalhadores = trabalhadores if trabalhadores is not None else db.colecao_trabalhadores
        self.obras = obras if obras is not None else db.colecao_obras
        self.ocorrencias = ocorrencias if ocorrencias is not None else db.banco_dados["tbl_ocorrencias"]
        self.cliente = cliente if cliente is not None else db.cliente_mongo

    def buscar_obra(self, identificador):
        return self.obras.find_one({"_id": identificador})

    def obras_existentes(self, identificadores):
        return list(self.obras.find({"_id": {"$in": identificadores}}))

    def inserir(self, documento):
        return self.trabalhadores.insert_one(documento).inserted_id

    def buscar(self, identificador):
        return self.trabalhadores.find_one({"_id": identificador})

    def atualizar(self, identificador, campos):
        def gravar(sessao=None):
            return self.trabalhadores.update_one(
                {"_id": identificador}, {"$set": campos}, session=sessao).matched_count

        if "obras" not in campos:
            return gravar()
        # Responsabilidade é opcional, mas exige vínculo com a mesma obra.
        mantidas = [valor for obra in campos["obras"] for valor in (obra, ObjectId(obra))]
        return self._manter_responsaveis(identificador, gravar, {"obra_id": {"$nin": mantidas}})

    def excluir(self, identificador):
        def gravar(sessao=None):
            return self.trabalhadores.delete_one({"_id": identificador}, session=sessao).deleted_count

        return self._manter_responsaveis(identificador, gravar)

    def _manter_responsaveis(self, identificador, gravar, contexto=None):
        filtro = {"responsavel_id": {"$in": [identificador, str(identificador)]}, **(contexto or {})}
        if self.ocorrencias.find_one(filtro, {"_id": 1}) is None:
            return gravar()

        def transacao(sessao):
            resultado = gravar(sessao)
            if resultado:
                # Não apaga ocorrências, aceitações nem transições anteriores.
                self.ocorrencias.update_many(
                    filtro, {"$set": {"responsavel_id": None}, "$inc": {"versao": 1}}, session=sessao)
            return resultado

        with self.cliente.start_session() as sessao:
            return sessao.with_transaction(transacao)

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
