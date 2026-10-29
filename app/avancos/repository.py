"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

import db


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1}) is not None


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def buscar_obra(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id}, {"_id": 1})


def consultar_publicados(obra_id):
    marcos = [item["_id"] for item in db.colecao_marcos.find({"obra_id": obra_id}, {"_id": 1})]
    return list(db.banco_dados["tbl_avancos"].find(
        {"marco_id": {"$in": marcos}, "estado": "publicado", "publicacao": {"$type": "object"}}
    ).sort([("publicacao.instante", -1), ("_id", 1)]))
