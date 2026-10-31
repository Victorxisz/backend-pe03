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
banco_dados = cliente_mongo["banco_de_dados"]

colecao_trabalhadores = banco_dados["tbl_trabalhadores"]
colecao_construtora = banco_dados["tbl_construtora"]
colecao_marcos = banco_dados["tbl_marcos"]
colecao_historico = banco_dados["tbl_historico"]
colecao_obras = banco_dados["tbl_obras"]
colecao_ocorrencias = banco_dados["tbl_ocorrencias"]
colecao_sessoes_revogadas = banco_dados["tbl_sessoes_revogadas"]

colecao_construtora.create_index("email", unique=True) # Impede que uma construtora tenha mais de uma conta em um único email
