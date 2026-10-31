"""Persistência do histórico, com coleção recebida por dependência."""

import db


class RepositorioHistorico:
    def __init__(self, colecao=None):
        self.colecao = colecao if colecao is not None else db.colecao_historico

    def inserir_evento(self, evento, *, session=None):
        return self.colecao.insert_one(evento, session=session).inserted_id


_repositorio = RepositorioHistorico()
inserir_evento = _repositorio.inserir_evento
