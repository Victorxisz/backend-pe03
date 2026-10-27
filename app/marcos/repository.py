"""Acesso à persistência de marcos e obras."""

import db


def obra_existe(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id}, {"_id": 1}) is not None


def inserir_marco(marco):
    resultado = db.colecao_marcos.insert_one(marco)
    return resultado.inserted_id

def buscar_marco_por_id (marco_id):
    return db.colecao_marcos.find_one({"_id":marco_id})

def buscar_obra_por_id (obra_id):
    return db.colecao_obras.find_one({"_id":obra_id})

def substituir_dependencias(obra, novos_vinculos):
    filtro = {"_id": obra["_id"]}

    if "dependencias_marcos" in obra:
        filtro["dependencias_marcos"] = obra["dependencias_marcos"]
    else:
        filtro["dependencias_marcos"] = {"$exists": False}

    resultado = db.colecao_obras.update_one(
        filtro,
        {"$set": {"dependencias_marcos": novos_vinculos}},
    )

    return resultado.modified_count == 1

def buscar_marcos_da_obra(obra_id):
    return list(
        db.colecao_marcos.find(
            {"obra_id": obra_id},
            {"nome": 1, "estado": 1},
        ).sort([("nome", 1), ("_id", 1)])
    )