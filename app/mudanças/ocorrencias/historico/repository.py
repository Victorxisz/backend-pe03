"""Leitura e transição atômica do avanço, sem uma segunda gravação de histórico."""

import db
from pymongo import ReturnDocument
from app.avancos.revisoes import ConflitoRascunho, filtro_revisao


class VinculoAlterado(Exception):
    """Um registro revisado foi excluído ou alterado antes da publicação."""


def buscar_avanco(identificador):
    return db.banco_dados["tbl_avancos"].find_one({"_id": identificador})


def buscar_marco(identificador):
    return db.colecao_marcos.find_one({"_id": identificador})


def buscar_obra(identificador):
    return db.colecao_obras.find_one({"_id": identificador})


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def publicar(documento, publicacao, marco, midias):
    try:
        revisao_esperada = filtro_revisao(documento)
    except ConflitoRascunho:
        raise VinculoAlterado() from None
    
    def gravar(sessao):
        publicado = db.banco_dados["tbl_avancos"].find_one_and_update(
            {
                "_id": documento["_id"],
                "estado": "rascunho",
                "publicacao": {"$exists": False},
                **revisao_esperada,
                **{
                    campo: documento[campo]
                    for campo in ("data", "descricao", "marco_id")
                   },
                },
            {
                "$set": {
                    "estado": "publicado",
                    "publicacao": publicacao
                    },
                    "$inc":{"revisao":1},
            },
            return_document=ReturnDocument.AFTER,
            session=sessao,
        )

        if publicado is None:
            return None

        midias_atuais = list(
            db.banco_dados["tbl_midias"].find(
                {"avanco_id": documento["_id"]},
                session = sessao,
            )
            .sort("_id", 1)
        )

        if midias_atuais != midias:
            raise VinculoAlterado()
        
        vinculos = [
                (db.colecao_obras, {"_id": marco["obra_id"]}),
                (db.colecao_marcos, marco)
            ]
        vinculos.extend(
            (db.banco_dados["tbl_midias"], midia)
              for midia in midias
            )
        
        for colecao, revisado in vinculos:
            # A escrita real faz exclusões concorrentes conflitarem até o commit.
            filtro = {
                k: v
                for k, v in revisado.items()
                if k != "_versao_publicacao"
            }

            resultado = colecao.update_one(
                filtro,
                {"$inc": {"_versao_publicacao": 1}},
                session=sessao,
            )

            if resultado.matched_count != 1:
                raise VinculoAlterado()
            
        return publicado

    with db.cliente_mongo.start_session() as sessao:
        return sessao.with_transaction(gravar)


def consultar_publicados(obra_id):
    marcos = [
        item["_id"] for item in db.colecao_marcos.find(
            {"obra_id": obra_id},
            {"_id": 1},
        )
    ]
    return list(db.banco_dados["tbl_avancos"].find(
            {"marco_id": {"$in": marcos},
            "estado": "publicado",
            "publicacao": {"$type": "object"}
        },
    ).sort(
        [
            ("publicacao.data", 1),
            ("publicacao.instante", 1),
            ("_id", 1),
        ]))
