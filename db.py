import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient


# Carrega os dados inseridos no .env
caminho_env = Path(__file__).resolve().parent / ".env"
load_dotenv(caminho_env)

mongo_uri = os.getenv("MONGO_URI")

# Caso não ache a uri do mongo
if not mongo_uri:
    raise RuntimeError("Configure MONGO_URI no arquivo .env")

# Cliente compartilhado pelas rotas dentro deste processo.
cliente_mongo = MongoClient(mongo_uri)

# O nome do banco deve estar informado na URI.
banco_dados = cliente_mongo.get_default_database()

colecao_trabalhadores = banco_dados["tbl_trabalhadores"]