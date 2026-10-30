"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

import db
from pymongo import ReturnDocument

from .revisoes import filtro_revisao

ESTADO_EXCLUSAO = "exclusao_pendente"
from bson import ObjectId

from .revisoes import ConflitoRascunho, registrar_alteracao
from .rascunhos_repository import RepositorioRascunhos


def salvar_edicao(documento, alteracoes, midias_anteriores, ids_manter, novas_midias):
    return RepositorioRascunhos().salvar_edicao(
        documento, alteracoes, midias_anteriores, ids_manter, novas_midias,
    )


def referencia_em_uso(referencia, ids_midias=()):
    return RepositorioRascunhos().referencia_em_uso(referencia, ids_midias)


def concluir_limpeza(midia_id):
    return RepositorioRascunhos().concluir_limpeza(midia_id)


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id, "estado": {"$ne": ESTADO_EXCLUSAO}}, {"_id": 1}
    ) is not None


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def iniciar_exclusao(documento, arquivos, token, agora, ate):
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


def acrescentar_pendencias(avanco_id, token, arquivos):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$push": {"exclusao.arquivos": {"$each": arquivos},
                   "exclusao.pendentes": {"$each": arquivos}}},
    )


def finalizar_exclusao(avanco_id, token):
    filtro = {**_operacao(avanco_id, token), "exclusao.pendentes": {"$size": 0}}
    if db.banco_dados["tbl_avancos"].find_one(filtro, {"_id": 1}) is None:
        return False
    # Se uma etapa do banco falhar, o diário permanece para repetir a operação.
    db.banco_dados["tbl_midias"].delete_many({"avanco_id": avanco_id})
    return db.banco_dados["tbl_avancos"].delete_one(filtro).deleted_count == 1


def arquivo_tem_outras_referencias(avanco_id, arquivo):
    """Conservador: preserva referências atuais, históricas e de registros órfãos.

    Rascunhos já marcados para exclusão não são leitores ativos. Isso permite
    excluir simultaneamente dois rascunhos que compartilham o mesmo objeto.
    """
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
        from bson import ObjectId
        return isinstance(valor, ObjectId) and valor in ids

    banco = db.banco_dados
    for nome in banco.list_collection_names():
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
            if contem(documento):
                return True
    return False
