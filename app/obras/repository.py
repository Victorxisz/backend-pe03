"""Operações de persistência de obras."""

import db
from pymongo import ReturnDocument


class RepositorioObras:
    def __init__(self, banco=None):
        self.banco = banco if banco is not None else db.banco_dados

    def salvar_obra(self, documento):
        return self.banco["tbl_obras"].insert_one(documento).inserted_id

    def buscar_obra_por_id(self, obra_id):
        return self.banco["tbl_obras"].find_one({"_id": obra_id})

    def consultar_obras(self, filtro):
        return list(self.banco["tbl_obras"].find(filtro).sort("_id", 1))

    def consultar_marcos(self, obra_id):
        return list(self.banco["tbl_marcos"].find({"obra_id": obra_id}).sort("_id", 1))

    def atualizar_descricao(self, obra_id, campos):
        # Uma única operação atômica; não substitui nem recria o documento.
        return self.banco["tbl_obras"].find_one_and_update(
            {"_id": obra_id}, {"$set": campos}, return_document=ReturnDocument.AFTER
        )

    def salvar_estado_com_historico(self, documento, evento):
        filtro = {"_id": documento["_id"], "estado": documento["estado"]}
        filtro["revisao_estado"] = documento.get("revisao_estado", {"$exists": False})
        return self.banco["tbl_obras"].find_one_and_update(
            filtro,
            {"$set": evento["valor_novo"], "$push": {"historico_estados": evento},
             "$inc": {"revisao_estado": 1}, "$unset": {"critica": ""}},
            return_document=ReturnDocument.AFTER,
        )


_repositorio = RepositorioObras()

# Fachada para imports e pontos de integração já existentes.
salvar_obra = _repositorio.salvar_obra
buscar_obra_por_id = _repositorio.buscar_obra_por_id
consultar_obras = _repositorio.consultar_obras
consultar_marcos = _repositorio.consultar_marcos
atualizar_descricao = _repositorio.atualizar_descricao
salvar_estado_com_historico = _repositorio.salvar_estado_com_historico
