"""Acesso à persistência de marcos, obras e histórico associado."""

import db
from app.historico import repository as historico_repository
from bson import ObjectId
from bson.errors import InvalidId


class EstadoMarcoAlterado(Exception):
    """Indica que outra requisição alterou o marco durante a operação."""

class DependenciaInconsistente(Exception):
    """Indica uma referência de dependência inválida ou inexistente."""


class RepositorioMarcos:
    def __init__(self, banco=None, cliente=None, historico=None):
        self.banco = banco if banco is not None else db.banco_dados
        self.cliente = cliente if cliente is not None else db.cliente_mongo
        self.historico = historico if historico is not None else (
            historico_repository if banco is None else
            historico_repository.RepositorioHistorico(self.banco["tbl_historico"])
        )

    def obra_existe(self, obra_id):
        return self.buscar_obra_por_id(obra_id) is not None

    def inserir_marco(self, documento):
        resultado = self.banco["tbl_marcos"].insert_one(documento)
        return resultado.inserted_id

    def buscar_marco(self, marco_id):
        return self.buscar_marco_por_id(marco_id)

    def buscar_marco_por_id(self, marco_id):
        return self.banco["tbl_marcos"].find_one({"_id": marco_id})

    def buscar_obra_por_id(self, obra_id):
        return self.banco["tbl_obras"].find_one({"_id": obra_id})

    def substituir_dependencias(self, obra, novos_vinculos):
        filtro = {"_id": obra["_id"]}
        if "dependencias_marcos" in obra:
            filtro["dependencias_marcos"] = obra["dependencias_marcos"]
        else:
            filtro["dependencias_marcos"] = {"$exists": False}

        resultado = self.banco["tbl_obras"].update_one(
            filtro,
            {"$set": {"dependencias_marcos": novos_vinculos}},
        )
        return resultado.modified_count == 1

    def dependencias_pendentes(self, marco):
        ids = marco.get("dependencias", [])
        if not isinstance(ids, list):
            ids = []
        else:
            ids = list(ids)
        obra = self.buscar_obra_por_id(marco["obra_id"])
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

            dependencia = self.buscar_marco_por_id(oid)

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

    def salvar_estado_com_historico(self, marco_id, estado_anterior, estado_novo, evento, *, versao=0):
        def executar (session):
            resultado = self.banco["tbl_marcos"].update_one(
                {"_id": marco_id, "estado": estado_anterior,
                 "versao": versao if versao else {"$in": [None, 0]}},
                {"$set": {"estado": estado_novo}, "$inc": {"versao": 1}},
                session=session,
            )

            if resultado.matched_count != 1:
                raise EstadoMarcoAlterado(
                    "O estado do marco foi alterado concorrentemente"
                )

            self.historico.inserir_evento(
                dict(evento),
                session=session,
            )

        with self.cliente.start_session() as session:
            session.with_transaction(executar)


_repositorio = RepositorioMarcos()

# Fachada para imports e pontos de integração já existentes.
def obra_existe(obra_id):
    # A fachada mantém o ponto de consulta substituível dos consumidores antigos.
    return buscar_obra_por_id(obra_id) is not None


inserir_marco = _repositorio.inserir_marco
buscar_marco = _repositorio.buscar_marco
buscar_marco_por_id = _repositorio.buscar_marco_por_id
buscar_obra_por_id = _repositorio.buscar_obra_por_id
substituir_dependencias = _repositorio.substituir_dependencias
dependencias_pendentes = _repositorio.dependencias_pendentes
salvar_estado_com_historico = _repositorio.salvar_estado_com_historico
