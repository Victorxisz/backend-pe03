"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

import db
import logging

logger = logging.getLogger(__name__)


def avanco_existe(avanco_id):
    return (
        db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1})
        is not None
    )


def consultar_midias(avanco_id):
    return list(
        db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1)
    )


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


class MarcoRemovido(Exception):
    pass


def buscar_marco(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id})


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def listar_avancos(marco_id):
    return list(
        db.banco_dados["tbl_avancos"].find({"marco_id": marco_id}).sort("_id", 1)
    )


def salvar_com_midias(documento, midias, operacao_id):
    """Salva documentos e verifica vínculo em transação MongoDB."""

    def gravar(sessao):
        # A escrita no marco detecta exclusão concorrente antes do commit.
        atualizado = db.colecao_marcos.update_one(
            {"_id": documento["marco_id"]},
            {"$inc": {"_versao_avancos": 1}},
            session=sessao,
        )
        if atualizado.matched_count != 1:
            raise MarcoRemovido()
        db.banco_dados["tbl_avancos"].insert_one(documento, session=sessao)
        db.banco_dados["tbl_midias"].insert_many(midias, session=sessao)
        operacao = db.banco_dados["tbl_uploads_pendentes"].update_one(
            {"_id": operacao_id, "estado": "pendente"},
            {"$set": {"estado": "concluida"}},
            session=sessao,
        )
        if operacao.matched_count != 1:
            raise RuntimeError("Operação de upload indisponível")

    confirmado = False
    try:
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(gravar)
            confirmado = True
    except Exception:
        if not confirmado:
            raise
        # A transação já confirmou: um erro no encerramento da sessão não deve
        # acionar a compensação e apagar mídias efetivamente referenciadas.
        logger.warning("Transação confirmada; falha ao encerrar sessão do MongoDB")


def criar_operacao(documento):
    db.banco_dados["tbl_uploads_pendentes"].insert_one(documento)


def buscar_operacao(operacao_id):
    return db.banco_dados["tbl_uploads_pendentes"].find_one({"_id": operacao_id})


def registrar_referencia(operacao_id, referencia):
    resultado = db.banco_dados["tbl_uploads_pendentes"].update_one(
        {"_id": operacao_id, "estado": "pendente"},
        {"$push": {"referencias": referencia}},
    )
    if resultado.matched_count != 1:
        raise RuntimeError("Operação de upload indisponível")


def remover_operacao_pendente(operacao_id):
    db.banco_dados["tbl_uploads_pendentes"].delete_one(
        {"_id": operacao_id, "estado": "pendente"}
    )
