"""Verifica a proteção da suíte contra a configuração da demonstração."""

import sys

from support import snapshot


def test_conexao_redirecionada_para_namespace_de_teste(app, database):
    # Preparação
    db_module = sys.modules["db"]

    # Execução
    configured = db_module.banco_dados

    # Verificação
    assert configured is database
    assert configured.name.startswith("tests_")
    assert db_module.colecao_trabalhadores.database is database


def test_namespace_inicia_vazio(database):
    # Preparação
    expected = {}

    # Execução
    actual = snapshot(database)

    # Verificação
    assert actual == expected
