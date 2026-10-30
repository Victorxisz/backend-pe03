"""Persistência e consulta de avanços e de suas mídias."""

import db


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1}) is not None


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def marco_existe(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id}, {"_id": 1}) is not None


def inserir_avanco(documento):
    return db.banco_dados["tbl_avancos"].insert_one(documento).inserted_id


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def listar_avancos(marco_id):
    return list(db.banco_dados["tbl_avancos"].find({"marco_id": marco_id}).sort("data", 1).sort("_id", 1))
