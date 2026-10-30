"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

from bson import ObjectId
from pymongo import ReturnDocument

import db

from .revisoes import ConflitoRascunho, filtro_revisao, registrar_alteracao

ESTADO_EXCLUSAO = "exclusao_pendente"


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id, "estado": {"$ne": ESTADO_EXCLUSAO}},
        {"_id": 1},
    ) is not None


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id},
    )


def salvar_edicao(
    documento, alteracoes, midias_anteriores, ids_manter, novas_midias,
):
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

def iniciar_exclusao(documento, arquivos, token, agora, ate):
    validar_referencias_das_midias(
        documento["_id"], consultar_midias(documento["_id"])
    )
    # O mesmo CAS usado pela publicação impede a disputa publicar/excluir.
    return db.banco_dados["tbl_avancos"].find_one_and_update(
        {"_id": documento["_id"], "estado": "rascunho", "publicacao": {"$exists": False},
         **filtro_revisao(documento)},
        {"$set": {"estado": ESTADO_EXCLUSAO, "exclusao": {
            "arquivos": arquivos, "pendentes": arquivos, "token": token,
            "iniciada_em": agora, "ate": ate, "tentativas": 1,
        }}, "$inc": {"revisao": 1}},
        return_document=ReturnDocument.AFTER,
    )


def retomar_exclusao(avanco_id, token, agora, ate):
    return db.banco_dados["tbl_avancos"].find_one_and_update(
        {"_id": avanco_id, "estado": ESTADO_EXCLUSAO, "publicacao": {"$exists": False},
         "$or": [{"exclusao.token": None}, {"exclusao.ate": {"$lte": agora}}]},
        {"$set": {"exclusao.token": token, "exclusao.ate": ate},
         "$inc": {"exclusao.tentativas": 1}},
        return_document=ReturnDocument.AFTER,
    )


def _operacao(avanco_id, token):
    return {"_id": avanco_id, "estado": ESTADO_EXCLUSAO, "exclusao.token": token}


def renovar_exclusao(avanco_id, token, ate):
    return db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token), {"$set": {"exclusao.ate": ate}}
    ).matched_count == 1


def concluir_arquivo(avanco_id, token, chave):
    return db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token), {"$pull": {"exclusao.pendentes": {"chave": chave}}}
    ).matched_count == 1


def liberar_exclusao(avanco_id, token):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$set": {"exclusao.token": None, "exclusao.ate": None}},
    )


def registrar_falha_limpeza(avanco_id, token, agora):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$set": {"exclusao.ultima_falha_em": agora,
                  "exclusao.ultimo_erro": "Não foi possível remover um arquivo no provedor"}},
    )



def consultar_midias_para_limpeza(avanco_id):
    """Inclui arquivos removidos por edições cuja limpeza ainda não terminou."""
    atuais = consultar_midias(avanco_id)
    anteriores = [
        tarefa["midia"]
        for tarefa in db.banco_dados["tbl_limpezas_midias"].find(
            {"avanco_id": avanco_id}
        )
    ]
    return atuais + anteriores


def acrescentar_pendencias(avanco_id, token, arquivos):
    return db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$push": {"exclusao.arquivos": {"$each": arquivos},
                   "exclusao.pendentes": {"$each": arquivos}}},
    ).matched_count == 1


def finalizar_exclusao(avanco_id, token):
    filtro = {**_operacao(avanco_id, token), "exclusao.pendentes": {"$size": 0}}
    if db.banco_dados["tbl_avancos"].find_one(filtro, {"_id": 1}) is None:
        return False
    validar_referencias_das_midias(avanco_id, consultar_midias(avanco_id))
    # O diário permanece até concluir todas as etapas e permite retentativa
    # se alguma escrita falhar, inclusive depois de remover os metadados.
    db.banco_dados["tbl_midias"].delete_many({"avanco_id": avanco_id})
    db.banco_dados["tbl_limpezas_midias"].delete_many({"avanco_id": avanco_id})
    return db.banco_dados["tbl_avancos"].delete_one(filtro).deleted_count == 1


def _outros_documentos(avanco_id):
    """Tarefas de limpeza não são consumidores dos arquivos."""
    banco = db.banco_dados
    for nome in banco.list_collection_names():
        if nome == "tbl_limpezas_midias":
            continue
        for documento in banco[nome].find():
            if nome == "tbl_avancos":
                if documento["_id"] == avanco_id or documento.get("estado") == ESTADO_EXCLUSAO:
                    continue
            if nome == "tbl_midias":
                dono = documento.get("avanco_id")
                if dono == avanco_id:
                    continue
                pai = buscar_avanco(dono) if dono is not None else None
                if pai is not None and pai.get("estado") == ESTADO_EXCLUSAO:
                    continue
            yield documento


def _contem_id(valor, ids, textos):
    if isinstance(valor, dict):
        return any(_contem_id(item, ids, textos) for item in valor.values())
    if isinstance(valor, list):
        return any(_contem_id(item, ids, textos) for item in valor)
    if isinstance(valor, str):
        return valor in textos
    return isinstance(valor, ObjectId) and valor in ids


def validar_referencias_das_midias(avanco_id, midias):
    """Não remove metadados cujo ID ainda é usado fora do rascunho."""
    ids = {midia["_id"] for midia in midias}
    if not ids:
        return
    textos = {str(valor) for valor in ids}
    if any(_contem_id(doc, ids, textos) for doc in _outros_documentos(avanco_id)):
        raise ConflitoRascunho(
            "Uma mídia está referenciada por outro registro"
        )


def arquivo_tem_outras_referencias(avanco_id, arquivo):
    """Preserva arquivos usados por outras mídias ou snapshots históricos."""
    from .midias import chave_arquivo, ErroMidia

    identidade = chave_arquivo(arquivo["referencia"])
    ids = set(arquivo["midia_ids"])
    textos = {str(valor) for valor in ids}

    def contem(valor):
        if isinstance(valor, dict):
            try:
                if chave_arquivo(valor) == identidade:
                    return True
            except ErroMidia:
                pass
            return any(contem(item) for item in valor.values())
        if isinstance(valor, list):
            return any(contem(item) for item in valor)
        return _contem_id(valor, ids, textos)

    return any(contem(doc) for doc in _outros_documentos(avanco_id))
