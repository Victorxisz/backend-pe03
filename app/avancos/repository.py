"""Acesso à persistência de avanços e de suas mídias."""

import db


def avanco_existe(avanco_id):
    return (
        db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1})
        is not None
    )


def consultar_midias(avanco_id):
    # O vínculo é o próprio filtro: mídia de outro avanço não é devolvida.
    return list(
        db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1)
    )


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})
