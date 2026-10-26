"""Acesso à persistência do histórico."""

import db


def inserir_evento(evento):
    return db.colecao_historico.insert_one(evento).inserted_id


def remover_evento(evento_id):
    db.colecao_historico.delete_one({"_id": evento_id})
