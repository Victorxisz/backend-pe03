"""Dados compartilhados pelos testes de trabalhadores."""

import pytest
from bson import ObjectId


@pytest.fixture
def trabalhador():
    return {
        "nome": "João Fictício",
        "email": "joao@example.com",
        "telefone": "16991736767",
        "cargo": "pedreiro",
    }


@pytest.fixture
def obra_existente(database, obra, account):
    documento = {**obra, "_id": ObjectId("507f1f77bcf86cd799439011"), "autor": str(account["_id"])}
    database.tbl_obras.insert_one(documento)
    return documento


@pytest.fixture
def pessoa(database, trabalhador, obra_existente, account):
    documento = {
        **trabalhador,
        "_id": ObjectId(),
        "obras": [str(obra_existente["_id"])],
        "ativo": True,
        "construtora_id": str(account["_id"]),
    }
    database.tbl_trabalhadores.insert_one(documento)
    return documento


@pytest.fixture
def modulo_trabalhadores(app):
    # O app precisa ser carregado antes do import para isolar o banco.
    import trabalhadores

    return trabalhadores
