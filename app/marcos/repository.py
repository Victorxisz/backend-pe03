"""Acesso à persistência de marcos e obras."""

import db
from app.historico import repository as historico_repository


class EstadoMarcoAlterado(Exception):
    """Indica que outra requisição alterou o marco durante a operação."""


def obra_existe(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id}, {"_id": 1}) is not None


def inserir_marco(documento):
    resultado = db.colecao_marcos.insert_one(documento)
    return resultado.inserted_id


def buscar_marco(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id})


def dependencias_pendentes(marco):
    ids = marco.get("dependencias", [])
    if not isinstance(ids, list):
        return []
    pendentes = []
    for dependencia_id in ids:
        try:
            from bson import ObjectId
            oid = dependencia_id if isinstance(dependencia_id, ObjectId) else ObjectId(str(dependencia_id))
        except (TypeError, ValueError):
            continue
        dependencia = db.colecao_marcos.find_one(
            {"_id": oid}, {"nome": 1, "estado": 1}
        )
        if dependencia and dependencia.get("estado") != "concluído":
            pendentes.append({"id": str(oid), "nome": dependencia.get("nome", "Marco"),
                              "estado": dependencia.get("estado", "a iniciar")})
    return pendentes


def salvar_estado_com_historico(marco_id, estado_anterior, estado_novo, evento):
    # O histórico é gravado primeiro. Se a atualização do marco falhar, removê-lo
    # mantém a operação integral mesmo em MongoDB sem suporte a transações.
    evento_id = historico_repository.inserir_evento(evento)
    try:
        resultado = db.colecao_marcos.update_one(
            {"_id": marco_id, "estado": estado_anterior},
            {"$set": {"estado": estado_novo}},
        )
        if resultado.matched_count != 1:
            raise EstadoMarcoAlterado("O estado do marco foi alterado concorrentemente")
    except Exception:
        historico_repository.remover_evento(evento_id)
        raise
