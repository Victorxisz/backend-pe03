"""Controle de revisão compartilhado entre edição e publicação"""

import db

class ConflitoRascunho(Exception):
    """O rascunho mudou, foi pudblicado ou deixou de existir."""

def filtro_revisao (documento):
    if 'revisao' not in documento:
        return {"revisao": {"$exists":False}}

    revisao = documento["revisao"]

    if type(revisao) is not int or revisao < 0:
        raise ConflitoRascunho("Revisão do rascunho inválida")

    return {"revisao":revisao}

def registrar_alteracao (documento, sessao):
    filtro = {
        "_id": documento["_id"],
        "estado":"rascunho",
        "publicacao":{"$exists":False},
        **filtro_revisao(documento)
    }

    resultado = db.banco_dados["tbl_avancos"].update_one(
        filtro,
        {"$inc": {"revisao":1}},
        session=sessao,
    )

    if resultado.matched_count != 1:
        raise ConflitoRascunho(
            "O rascunho foi alterado; consulte novamente antes de editar"
        )