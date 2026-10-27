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
def obra_existente(database, obra):
    documento = {**obra, "_id": ObjectId("507f1f77bcf86cd799439011")}
    database.tbl_obras.insert_one(documento)
    return documento


@pytest.fixture
def pessoa(database, trabalhador, obra_existente):
    documento = {
        **trabalhador,
        "_id": ObjectId(),
        "obras": [str(obra_existente["_id"])],
        "ativo": True,
    }
    database.tbl_trabalhadores.insert_one(documento)
    return documento


@pytest.fixture
def modulo_trabalhadores(app):
    # O app precisa ser carregado antes do import para isolar o banco.
    import trabalhadores

    return trabalhadores
