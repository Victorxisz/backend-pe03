"""Acesso à persistência de marcos, obras e histórico associado."""

import db
from app.historico import repository as historico_repository
from bson import ObjectId
from bson.errors import InvalidId


class EstadoMarcoAlterado(Exception):
    """Indica que outra requisição alterou o marco durante a operação."""

class DependenciaInconsistente(Exception):
    """Indica uma referência de dependência inválida ou inexistente."""


def obra_existe(obra_id):
    return buscar_obra_por_id(obra_id) is not None


def inserir_marco(documento):
    resultado = db.colecao_marcos.insert_one(documento)
    return resultado.inserted_id


def buscar_marco(marco_id):
    return buscar_marco_por_id(marco_id)


def buscar_marco_por_id(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id})


def buscar_obra_por_id(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id})


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


def dependencias_pendentes(marco):
    ids = marco.get("dependencias", [])
    if not isinstance(ids, list):
        ids = []
    else:
        ids = list(ids)
    obra = buscar_obra_por_id(marco["obra_id"])
    if obra:
        ids.extend(
            vinculo["depende_de_id"]
            for vinculo in obra.get("dependencias_marcos", [])
            if vinculo.get("marco_id") == marco["_id"]
        )

    pendentes = []
    ids_verificados = set()

    for dependencia_id in ids:
        try:
            oid = (
                dependencia_id
                if isinstance(dependencia_id, ObjectId)
                else ObjectId(str(dependencia_id))
            )
        except (InvalidId, TypeError, ValueError) as erro:
            raise DependenciaInconsistente(
                "Dependência com identificador inválido"
            ) from erro

        if oid in ids_verificados:
            continue
        ids_verificados.add(oid)

        dependencia = buscar_marco_por_id(oid)

        if dependencia is None:
            raise DependenciaInconsistente(
                "Marco de dependência não encontrado"
            )

        if dependencia.get("obra_id") != marco["obra_id"]:
            raise DependenciaInconsistente(
                "A dependência pertence a outra obra"
            )

        if dependencia.get("estado") != "concluído":
            pendentes.append({
                "id": str(oid),
                "nome": dependencia.get("nome", "Marco"),
                "estado": dependencia.get("estado", "a iniciar"),
            })

    return pendentes


def salvar_estado_com_historico(marco_id, estado_anterior, estado_novo, evento):
    def executar (session):
        resultado = db.colecao_marcos.update_one(
            {"_id":marco_id, "estado": estado_anterior},
            {"$set": {"estado":estado_novo}},
            session=session,
        )

        if resultado.matched_count != 1:
            raise EstadoMarcoAlterado(
                "O estado do marco foi alterado concorrentemente"
            )

        historico_repository.inserir_evento(
            dict(evento),
            session=session,
        )

    with db.cliente_mongo.start_session() as session:
        session.with_transaction(executar)