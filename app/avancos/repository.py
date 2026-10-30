"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

import db
from bson import ObjectId

from .revisoes import ConflitoRascunho, registrar_alteracao


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1}) is not None


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})

def buscar_avanco (avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id},
    )

def salvar_edicao (documento, alteracoes, midias_anteriores, ids_manter, novas_midias,):
    if set(alteracoes) - {"data", "descricao"}:
        raise ValueError("Campos não permitidos na persistência da edição")

    avanco_id = documento["_id"]
    ids_manter = set(ids_manter)

    ids_anteriores = {
        midia["_id"]
        for midia in midias_anteriores
    }

    if not ids_manter.issubset(ids_anteriores):
        raise ValueError("Uma mídia selecionada não pertence ao conjunto anterior")

    if any(
        midia.get("avanco_id") != avanco_id
        for midia in midias_anteriores
    ):
        raise ValueError("Existe uma mídia vinculada a outro avanço")

    novas = [
        {
            **metadados,
            "_id": ObjectId(),
            "avanco_id":avanco_id
        }
        for metadados in novas_midias
    ]

    if not ids_manter and not novas:
        raise ValueError("O avanço precisa manter pelo menos uma mídia")

    removidas = [
        midia
        for midia in midias_anteriores
        if midia["_id"] not in ids_manter
    ]

    def gravar(sessao):
        avancos = db.banco_dados["tbl_avancos"]
        midias = db.banco_dados["tbl_midias"]

        registrar_alteracao(documento, sessao)

        atuais = list(
            midias.find(
                {"avanco_id": avanco_id},
                session=sessao,
            ).sort("_id", 1)
        )

        anteriores_ordenadas = sorted(
            midias_anteriores,
            key=lambda midia: midia["_id"],
        )

        if atuais != anteriores_ordenadas:
            raise ConflitoRascunho(
                "As mídias foram alteradas; consulte o avanço novamente"
            )

        if alteracoes:
            avancos.update_one(
                {"_id": avanco_id},
                {"$set": alteracoes},
                session=sessao,
            )

        for midia in atuais:
            if midia["_id"] in ids_manter:
                resultado = midias.update_one(
                    midia,
                    {"$inc": {"_versao_edicao": 1}},
                    session=sessao,
                )

                if resultado.matched_count != 1:
                    raise ConflitoRascunho(
                        "Uma mídia foi alterada durante a edição"
                    )

        for midia in removidas:
            if midia_tem_publicacao(
                midia["_id"],
                sessao=sessao,
            ):
                raise ConflitoRascunho(
                    "Uma mídia selecionada para remoção "
                    "está referenciada por uma publicação"
                )        

        if removidas:
            for midia in removidas:
                db.banco_dados["tbl_limpezas_midias"].update_one(
                    {"_id": midia["_id"]},
                    {
                        "$setOnInsert": {
                            "avanco_id": avanco_id,
                            "midia": midia,
                        }
                    },
                    upsert=True,
                    session=sessao,
                )
            
            resultado = midias.delete_many(
                {
                    "avanco_id":avanco_id,
                    "_id": {
                        "$in": [
                            midia["_id"]
                            for midia in removidas
                        ]
                    },
                },
                session=sessao
            )

            if resultado.deleted_count != len(removidas):
                raise ConflitoRascunho(
                    "Uma mídia foi alterada com a edição"
                )

        if novas:
            midias.insert_many(novas, session=sessao)

        salvo = avancos.find_one(
            {"_id": avanco_id},
            session=sessao
        )

        return salvo, removidas

    with db.cliente_mongo.start_session() as sessao:
        return sessao.with_transaction(gravar)

def midia_tem_publicacao(midia_id, *, sessao=None):
    documento = db.banco_dados["tbl_avancos"].find_one(
        {
            "publicacao.midias.id": {
                "$in": [
                    str(midia_id),
                    midia_id,
                ]
            }
        },
        {"_id": 1},
        session=sessao,
    )

    return documento is not None

def referencia_em_uso(referencia, *, ids_midias=()):
    campos_identidade = (
        "provedor",
        "public_id",
        "resource_type",
        "delivery_type",
    )

    # Sem uma identidade válida, não autoriza a exclusão.
    if not isinstance(referencia, dict):
        return True

    if any(
        not isinstance(referencia.get(campo), str)
        or not referencia[campo].strip()
        for campo in campos_identidade
    ):
        return True

    filtro = {
        f"referencia_externa.{campo}": referencia[campo]
        for campo in campos_identidade
    }

    encontrada = db.banco_dados["tbl_midias"].find_one(
        filtro,
        {"_id": 1},
    )

    if encontrada is not None:
        return True

    return any(
        midia_tem_publicacao(midia_id)
        for midia_id in ids_midias
    )   

def concluir_limpeza(midia_id):
    db.banco_dados["tbl_limpezas_midias"].delete_one(
        {"_id": midia_id}
    )