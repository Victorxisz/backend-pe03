"""Conexão compartilhada e fachada dos nomes de coleção já usados pela aplicação."""

import os
from pathlib import Path
from dotenv import load_dotenv
from app.database import BancoMongo

load_dotenv(Path(__file__).resolve().parent / ".env")
conexao = BancoMongo(os.getenv("MONGO_URI"))
cliente_mongo = conexao.cliente
banco_dados = conexao.banco

colecao_trabalhadores = conexao.colecao("tbl_trabalhadores")
colecao_construtora = conexao.colecao("tbl_construtora")
colecao_marcos = conexao.colecao("tbl_marcos")
colecao_historico = conexao.colecao("tbl_historico")
colecao_obras = conexao.colecao("tbl_obras")
colecao_ocorrencias = conexao.colecao("tbl_ocorrencias")
colecao_sessoes_revogadas = conexao.colecao("tbl_sessoes_revogadas")
conexao.preparar_indices()
