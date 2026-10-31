"""Persistência atômica de aceitações vinculadas à ocorrência."""

import db
from pymongo import ReturnDocument


class OcorrenciaNaoEncontrada(Exception):
    pass


class EstadoOcorrenciaIncompativel(Exception):
    pass


class RepositorioOcorrencias:
    def __init__(self, banco=None):
        self.banco = banco if banco is not None else db.banco_dados

    def buscar(self, ocorrencia_id):
        return self.banco["tbl_ocorrencias"].find_one({"_id": ocorrencia_id})

    def aceitar(self, ocorrencia_id, aceitacao, chave_reenvio=None):
        # Estado no filtro torna a validação e o append uma única operação atômica.
        filtro = {"_id": ocorrencia_id, "estado": "sem solução"}
        if chave_reenvio:
            filtro["aceitacoes.chave_reenvio"] = {"$ne": chave_reenvio}
            aceitacao["chave_reenvio"] = chave_reenvio
        salvo = self.banco["tbl_ocorrencias"].find_one_and_update(
            filtro,
            {"$push": {"aceitacoes": aceitacao}},
            return_document=ReturnDocument.AFTER,
        )
        if salvo is not None:
            return salvo, False
        if chave_reenvio:
            existente = self.buscar(ocorrencia_id)
            if existente is not None:
                anterior = next((a for a in existente.get("aceitacoes", [])
                                 if a.get("chave_reenvio") == chave_reenvio), None)
                if anterior is not None:
                    return {"aceitacoes": [anterior]}, True
        if self.buscar(ocorrencia_id) is None:
            raise OcorrenciaNaoEncontrada()
        raise EstadoOcorrenciaIncompativel()


_repositorio = RepositorioOcorrencias()
