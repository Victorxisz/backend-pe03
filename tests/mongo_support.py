"""Conexão da aplicação e coleções temporárias no mesmo banco MongoDB."""

import os
import re
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient


NOME_DO_BANCO = "banco_de_dados"


def obter_mongo_uri():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        uri = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("MONGO_URI")
    if not uri:
        raise RuntimeError("Configure MONGO_URI no ambiente ou no arquivo .env")
    return uri


def conectar_mongo():
    uri = obter_mongo_uri()
    try:
        cliente = MongoClient(uri, serverSelectionTimeoutMS=5000)
    except Exception:
        raise RuntimeError("MONGO_URI inválida; verifique a configuração da aplicação") from None
    try:
        cliente.admin.command("ping")
    except Exception:
        cliente.close()
        raise RuntimeError("MongoDB indisponível; verifique acesso e MONGO_URI") from None
    return cliente


class BancoDaExecucao:
    def __init__(self, banco, prefixo):
        if not re.fullmatch(r"tests_[0-9a-f]{32}_", prefixo):
            raise ValueError("Prefixo de coleções temporárias inválido")
        self._banco = banco
        self.prefixo = prefixo
        self.name = banco.name
        self.client = banco.client

    def __getitem__(self, nome):
        return self._banco[self.prefixo + nome]

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        return self[nome]

    def list_collection_names(self):
        return [
            nome.removeprefix(self.prefixo)
            for nome in self._banco.list_collection_names()
            if nome.startswith(self.prefixo)
        ]

    def limpar_colecoes(self):
        for nome in self.list_collection_names():
            self._banco.drop_collection(self.prefixo + nome)


def recuperar_banco_da_execucao(cliente):
    return BancoDaExecucao(cliente[NOME_DO_BANCO], os.environ["TEST_COLLECTION_PREFIX"])
