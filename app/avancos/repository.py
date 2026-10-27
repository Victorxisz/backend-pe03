"""Persistência de avanços."""

import db


def marco_existe(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id}, {"_id": 1}) is not None


def inserir_avanco(documento):
    return db.banco_dados["tbl_avancos"].insert_one(documento).inserted_id


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def listar_avancos(marco_id):
    return list(db.banco_dados["tbl_avancos"].find({"marco_id": marco_id}).sort("data", 1).sort("_id", 1))
