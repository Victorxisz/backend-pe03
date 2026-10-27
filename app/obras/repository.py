"""Operações de persistência de obras."""

import db
from pymongo import ReturnDocument


def salvar_obra(documento):
    return db.banco_dados["tbl_obras"].insert_one(documento).inserted_id


def buscar_obra_por_id(obra_id):
    return db.banco_dados["tbl_obras"].find_one({"_id": obra_id})


def consultar_obras(filtro):
    return list(db.banco_dados["tbl_obras"].find(filtro).sort("_id", 1))


def consultar_marcos(obra_id):
    return list(db.banco_dados["tbl_marcos"].find({"obra_id": obra_id}).sort("_id", 1))


def atualizar_descricao(obra_id, campos):
    # Uma única operação atômica; não substitui nem recria o documento.
    return db.banco_dados["tbl_obras"].find_one_and_update(
        {"_id": obra_id}, {"$set": campos}, return_document=ReturnDocument.AFTER
    )
