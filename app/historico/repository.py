"""Leituras dos eventos já gravados por obras, marcos e avanços."""

import db


class RepositorioHistorico:
    def __init__(self, colecao=None, banco=None):
        self.colecao = colecao if colecao is not None else db.colecao_historico
        self.banco = banco if banco is not None else db.banco_dados

    def inserir_evento(self, evento, *, session=None):
        return self.colecao.insert_one(evento, session=session).inserted_id

    def listar_eventos_dos_alvos(self, ids, *, session=None):
        return list(self.colecao.find({"alvo.id": {"$in": list(ids)}}, session=session))

    def remover_eventos_dos_alvos(self, ids, *, session=None):
        """A trilha de um objeto excluído não sobrevive ao objeto (RN-09)."""
        alvos = list(ids)
        if not alvos:
            return
        self.colecao.delete_many({"alvo.id": {"$in": alvos}}, session=session)

    def buscar_obra(self, obra_id):
        return self.banco["tbl_obras"].find_one({"_id": obra_id})

    def buscar_marco(self, marco_id):
        return self.banco["tbl_marcos"].find_one({"_id": marco_id})

    def buscar_avanco(self, avanco_id):
        return self.banco["tbl_avancos"].find_one({"_id": avanco_id})

    def listar_marcos(self, obra_id):
        return list(self.banco["tbl_marcos"].find({"obra_id": obra_id}, {"_id": 1}))

    def listar_eventos_marcos(self, ids):
        return list(self.colecao.find({"alvo.tipo": "marco", "alvo.id": {"$in": ids}}))

    def buscar_evento_marco(self, evento_id):
        return self.colecao.find_one({"_id": evento_id, "alvo.tipo": "marco"})

    def listar_avancos_publicados(self, ids_marcos):
        return list(self.banco["tbl_avancos"].find({
            "marco_id": {"$in": ids_marcos}, "estado": "publicado",
        }))


_repositorio = RepositorioHistorico()
inserir_evento = _repositorio.inserir_evento
