"""Acesso à persistência de marcos e obras."""

import db


def obra_existe(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id}, {"_id": 1}) is not None


def inserir_marco(marco):
    resultado = db.colecao_marcos.insert_one(marco)
    return resultado.inserted_id
