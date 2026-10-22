"""Operações de persistência de obras."""

import db
from pymongo import ReturnDocument


def atualizar_descricao(obra_id, campos):
    # Uma única operação atômica; não substitui nem recria o documento.
    return db.banco_dados["tbl_obras"].find_one_and_update(
        {"_id": obra_id}, {"$set": campos}, return_document=ReturnDocument.AFTER
    )
