"""Persistência das contas e revogação de sessões."""

import db


class RepositorioConstrutoras:
    def __init__(self, contas=None, sessoes=None):
        self.contas = contas if contas is not None else db.colecao_construtora
        self.sessoes = sessoes if sessoes is not None else db.colecao_sessoes_revogadas

    def inserir(self, documento):
        return self.contas.insert_one(documento).inserted_id

    def por_email(self, email):
        return self.contas.find_one({"email": email})

    def buscar(self, identificador):
        return self.contas.find_one({"_id": identificador})

    def atualizar(self, identificador, campos):
        return self.contas.update_one({"_id": identificador}, {"$set": campos}).matched_count

    def excluir(self, identificador):
        return self.contas.delete_one({"_id": identificador}).deleted_count

    def encerrar_sessao(self, sessao_id, construtora_id, instante):
        self.sessoes.update_one({"_id": sessao_id}, {"$setOnInsert": {
            "construtora_id": construtora_id, "encerrada_em": instante,
        }}, upsert=True)
