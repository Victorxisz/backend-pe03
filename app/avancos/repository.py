"""Persistência de avanços, revisões e limpeza de mídias."""

import db
from bson import ObjectId
from pymongo import ReturnDocument

from .revisoes import filtro_revisao

ESTADO_EXCLUSAO = "exclusao_pendente"


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id, "estado": {"$ne": ESTADO_EXCLUSAO}}, {"_id": 1}
    ) is not None


def marco_existe(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id}, {"_id": 1}) is not None


def inserir_avanco(documento):
    return db.banco_dados["tbl_avancos"].insert_one(documento).inserted_id


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def listar_avancos(marco_id):
    return list(db.banco_dados["tbl_avancos"].find({"marco_id": marco_id}).sort([("data", 1), ("_id", 1)]))


def salvar_edicao(documento, alteracoes, midias_anteriores, ids_manter, novas_midias):
    ids_anteriores = {item["_id"] for item in midias_anteriores}
    ids_manter = set(ids_manter)
    if (not ids_manter or not ids_manter.issubset(ids_anteriores)
            or any(item.get("avanco_id") != documento["_id"] for item in midias_anteriores)):
        raise ValueError("Seleção de mídias inconsistente")
    removidas = [item for item in midias_anteriores if item["_id"] not in ids_manter]
    if set(alteracoes) - {"data", "descricao"}:
        raise ValueError("Campo protegido")

    def gravar(sessao):
        atual = db.banco_dados["tbl_avancos"].find_one_and_update(
            {"_id": documento["_id"], "estado": "rascunho", "publicacao": {"$exists": False},
             **filtro_revisao(documento)},
            {"$set": alteracoes, "$inc": {"revisao": 1}},
            return_document=ReturnDocument.AFTER, session=sessao,
        )
        if atual is None:
            from .revisoes import ConflitoRascunho
            raise ConflitoRascunho()
        for midia in midias_anteriores:
            filtro = {k: v for k, v in midia.items()}
            resultado = db.banco_dados["tbl_midias"].delete_one(filtro, session=sessao)
            if resultado.deleted_count != 1:
                from .revisoes import ConflitoRascunho
                raise ConflitoRascunho()
        mantidas = [item for item in midias_anteriores if item["_id"] in ids_manter]
        if mantidas:
            db.banco_dados["tbl_midias"].insert_many(mantidas, session=sessao)
        if novas_midias:
            db.banco_dados["tbl_midias"].insert_many(novas_midias, session=sessao)
        for item in removidas:
            db.banco_dados["tbl_limpezas_midias"].replace_one(
                {"_id": item["_id"]}, {"_id": item["_id"], "midia": item}, upsert=True, session=sessao,
            )
        return atual

    with db.cliente_mongo.start_session() as sessao:
        salvo = sessao.with_transaction(gravar)
    return salvo, removidas


def referencia_em_uso(referencia, ids_midias=()):
    from .midias import chave_arquivo, ErroMidia
    try:
        chave = chave_arquivo(referencia)
    except ErroMidia:
        return True
    excluidos = set(ids_midias)

    def contem(valor):
        if isinstance(valor, dict):
            try:
                if chave_arquivo(valor) == chave:
                    return True
            except ErroMidia:
                pass
            return any(contem(item) for item in valor.values())
        if isinstance(valor, list):
            return any(contem(item) for item in valor)
        return False

    for nome in db.banco_dados.list_collection_names():
        if nome == "tbl_limpezas_midias":
            continue
        for documento in db.banco_dados[nome].find():
            if nome == "tbl_midias" and documento.get("_id") in excluidos:
                continue
            if contem(documento):
                return True
    return False


def concluir_limpeza(midia_id):
    db.banco_dados["tbl_limpezas_midias"].delete_one({"_id": midia_id})


def iniciar_exclusao(documento, arquivos, token, agora, ate):
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
         "$inc": {"exclusao.tentativas": 1}}, return_document=ReturnDocument.AFTER,
    )


def _operacao(avanco_id, token):
    return {"_id": avanco_id, "estado": ESTADO_EXCLUSAO, "exclusao.token": token}


def renovar_exclusao(avanco_id, token, ate):
    return db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$set": {"exclusao.ate": ate}}).matched_count == 1


def concluir_arquivo(avanco_id, token, chave):
    return db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$pull": {"exclusao.pendentes": {"chave": chave}}}).matched_count == 1


def liberar_exclusao(avanco_id, token):
    db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$set": {"exclusao.token": None, "exclusao.ate": None}})


def registrar_falha_limpeza(avanco_id, token, agora):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$set": {"exclusao.ultima_falha_em": agora, "exclusao.ultimo_erro": "Não foi possível remover um arquivo no provedor"}},
    )


def acrescentar_pendencias(avanco_id, token, arquivos):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$push": {"exclusao.arquivos": {"$each": arquivos}, "exclusao.pendentes": {"$each": arquivos}},
         "$inc": {"revisao": 1}},
    )


def finalizar_exclusao(avanco_id, token):
    filtro = {**_operacao(avanco_id, token), "exclusao.pendentes": {"$size": 0}}
    if db.banco_dados["tbl_avancos"].find_one(filtro, {"_id": 1}) is None:
        return False
    db.banco_dados["tbl_midias"].delete_many({"avanco_id": avanco_id})
    return db.banco_dados["tbl_avancos"].delete_one(filtro).deleted_count == 1


def arquivo_tem_outras_referencias(avanco_id, arquivo):
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
        if isinstance(valor, str):
            return valor in textos
        return isinstance(valor, ObjectId) and valor in ids

    for nome in db.banco_dados.list_collection_names():
        for documento in db.banco_dados[nome].find():
            if nome == "tbl_avancos" and (documento["_id"] == avanco_id or documento.get("estado") == ESTADO_EXCLUSAO):
                continue
            if nome == "tbl_midias":
                dono = documento.get("avanco_id")
                if dono == avanco_id:
                    continue
                pai = buscar_avanco(dono) if dono is not None else None
                if pai is not None and pai.get("estado") == ESTADO_EXCLUSAO:
                    continue
            if contem(documento):
                return True
    return False
