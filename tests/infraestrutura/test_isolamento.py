"""Verifica que os testes acessam e limpam apenas suas próprias coleções."""

import sys
import uuid

import pytest

from mongo_support import BancoDaExecucao, NOME_DO_BANCO
from support import snapshot


def test_conexao_redirecionada_para_colecoes_da_execucao(app, database):
    # Preparação
    db_module = sys.modules["db"]

    # Execução
    configured = db_module.banco_dados

    # Verificação
    assert configured is database
    assert configured.name == NOME_DO_BANCO
    assert db_module.colecao_trabalhadores.name == database.prefixo + "tbl_trabalhadores"


def test_namespace_inicia_vazio(database):
    # Preparação
    expected = {}

    # Execução
    actual = snapshot(database)

    # Verificação
    assert actual == expected


def test_limpeza_preserva_colecoes_de_outras_execucoes(storage, database):
    outra_execucao = BancoDaExecucao(storage[NOME_DO_BANCO], "tests_" + uuid.uuid4().hex + "_")
    try:
        outra_execucao.tbl_obras.insert_one({"nome": "Preservar"})
        database.tbl_obras.insert_one({"nome": "Remover"})
        database.limpar_colecoes()
        assert database.list_collection_names() == []
        assert outra_execucao.tbl_obras.find_one()["nome"] == "Preservar"
    finally:
        outra_execucao.limpar_colecoes()


@pytest.mark.parametrize("prefixo", ["", "tbl_", "tests_", "tests_.*_"])
def test_prefixo_invalido_nao_permite_limpeza(storage, prefixo):
    with pytest.raises(ValueError):
        BancoDaExecucao(storage[NOME_DO_BANCO], prefixo)
