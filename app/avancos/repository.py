"""Consulta dos avanços e dos metadados de suas mídias no MongoDB."""

import db


# Uma mídia pertence a um único registro de negócio. O campo do vínculo diz qual
# coleção a guarda: ocorrência não é avanço, e o acesso não confunde as duas.
COLECAO_DO_VINCULO = {
    "avanco_id": "tbl_avancos",
    "ocorrencia_id": "tbl_ocorrencias",
}


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id}, {"_id": 1}) is not None


def vinculo_existe(campo, identificador):
    colecao = COLECAO_DO_VINCULO.get(campo)
    if colecao is None:
        return False
    return db.banco_dados[colecao].find_one({"_id": identificador}, {"_id": 1}) is not None


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})


def midias_existentes(identificadores):
    """Quais mídias citadas pelo histórico de versões continuam no acervo."""
    if not identificadores:
        return set()
    return {
        documento["_id"]
        for documento in db.banco_dados["tbl_midias"].find(
            {"_id": {"$in": list(identificadores)}}, {"_id": 1}
        )
    }
