"""Operações de persistência de obras."""

import db
from pymongo import ReturnDocument


def salvar_obra(documento):
    return db.banco_dados["tbl_obras"].insert_one(documento).inserted_id


def buscar_obra_por_id(obra_id):
    return db.banco_dados["tbl_obras"].find_one({"_id": obra_id})


def atualizar_descricao(obra_id, campos):
    # Uma única operação atômica; não substitui nem recria o documento.
    return db.banco_dados["tbl_obras"].find_one_and_update(
        {"_id": obra_id}, {"$set": campos}, return_document=ReturnDocument.AFTER
    )
