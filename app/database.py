"""Configuração da conexão MongoDB; não contém regras de negócio."""

from pymongo import MongoClient


class BancoMongo:
    def __init__(self, uri, *, cliente=None, nome="banco_de_dados"):
        if not uri and cliente is None:
            raise RuntimeError("Configure MONGO_URI no arquivo .env")
        self.cliente = cliente if cliente is not None else MongoClient(uri)
        self.banco = self.cliente[nome]

    def colecao(self, nome):
        return self.banco[nome]

    def preparar_indices(self):
        self.colecao("tbl_construtora").create_index("email", unique=True)
