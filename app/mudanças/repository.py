"""Gravação indivisível do planejamento e de sua trilha, com versão otimista."""

import db
from pymongo import ReturnDocument

from app.historico import repository as historico_repository


class MudancaConcorrente(Exception):
    """O documento lido já foi alterado por outra decisão."""


class RepositorioMudancas:
    def __init__(self, banco=None, cliente=None, historico=None):
        self.banco = banco if banco is not None else db.banco_dados
        self.cliente = cliente if cliente is not None else db.cliente_mongo
        self.historico = historico if historico is not None else (
            historico_repository if banco is None else
            historico_repository.RepositorioHistorico(self.banco["tbl_historico"])
        )

    def aplicar(self, tipo, documento, campos, evento):
        filtro = {"_id": documento["_id"],
                  "versao": documento.get("versao", {"$exists": False})}
        atualizacao = {"$set": campos, "$inc": {"versao": 1}}
        colecao = self.banco["tbl_obras" if tipo == "obra" else "tbl_marcos"]
        if tipo == "obra":
            # Um documento MongoDB é atômico mesmo sem replica set. A entrega
            # inteira é substituída para retirar campos da modalidade anterior.
            atualizacao["$push"] = {"historico_mudancas": evento}
            atualizacao["$unset"] = {"critica": ""}
            salvo = colecao.find_one_and_update(
                filtro, atualizacao, return_document=ReturnDocument.AFTER
            )
            if salvo is None:
                raise MudancaConcorrente()
            return salvo

        def executar(sessao):
            salvo = colecao.find_one_and_update(
                filtro, atualizacao, return_document=ReturnDocument.AFTER, session=sessao
            )
            if salvo is None:
                raise MudancaConcorrente()
            self.historico.inserir_evento(dict(evento), session=sessao)
            return salvo

        # Sem fallback para duas gravações: falhar mantém o objeto e a trilha intactos.
        with self.cliente.start_session() as sessao:
            return sessao.with_transaction(executar)
