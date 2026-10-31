"""Leitura dos vínculos e gravação atômica da ocorrência com suas mídias."""

import db


class VinculoAlterado(Exception):
    """Obra, marco ou responsável deixou de existir antes da gravação."""


def buscar_obra(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id})


def buscar_marco(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id})


def buscar_trabalhador(trabalhador_id):
    return db.colecao_trabalhadores.find_one({"_id": trabalhador_id})


def buscar_ocorrencia(ocorrencia_id):
    return db.colecao_ocorrencias.find_one({"_id": ocorrencia_id})


def consultar_por_obra(obra_id):
    return list(db.colecao_ocorrencias.find({"obra_id": obra_id}).sort("_id", 1))


def consultar_midias(ocorrencia_id):
    return list(
        db.banco_dados["tbl_midias"].find({"ocorrencia_id": ocorrencia_id}).sort("_id", 1)
    )


def salvar(documento, midias):
    """Grava ocorrência e mídias juntas; sem os dois lados não há registro."""

    def gravar(sessao):
        # Revalidação na transação: um vínculo excluído depois da verificação não
        # pode virar ocorrência que aponta para obra, marco ou responsável ausente.
        if db.colecao_obras.find_one(
            {"_id": documento["obra_id"]}, {"_id": 1}, session=sessao
        ) is None:
            raise VinculoAlterado()
        if documento.get("marco_id") is not None and db.colecao_marcos.find_one(
            {"_id": documento["marco_id"], "obra_id": documento["obra_id"]},
            {"_id": 1},
            session=sessao,
        ) is None:
            raise VinculoAlterado()
        if documento.get("responsavel_id") is not None and db.colecao_trabalhadores.find_one(
            {"_id": documento["responsavel_id"], "obras": str(documento["obra_id"])},
            {"_id": 1},
            session=sessao,
        ) is None:
            raise VinculoAlterado()
        if midias:
            db.banco_dados["tbl_midias"].insert_many(
                [dict(midia) for midia in midias], session=sessao
            )
        db.colecao_ocorrencias.insert_one(dict(documento), session=sessao)

    with db.cliente_mongo.start_session() as sessao:
        sessao.with_transaction(gravar)
