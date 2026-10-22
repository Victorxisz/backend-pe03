"""Regressão das rotas já existentes na branch MatheusHermida (fora CT-01..17)."""

from datetime import datetime

import pytest
from bson import ObjectId

from support import snapshot


@pytest.fixture
def trabalhador():
    return {
        "nome": "João Fictício",
        "email": "joao@example.com",
        "telefone": "16991736767",
        "cargo": "pedreiro",
    }


def test_cadastro_trabalhador(client, database, trabalhador):
    # Preparação
    path = "/trabalhadores/obra/123/"

    # Execução
    response = client.post(path, json=trabalhador)

    # Verificação
    assert response.status_code == 201
    body = response.get_json()
    assert body["mensagem"] == "Trabalhador criado com sucesso"
    saved = database.tbl_trabalhadores.find_one({"_id": ObjectId(body["id"])})
    assert saved is not None
    for field, value in trabalhador.items():
        assert saved[field] == value
    assert saved["obras"] == [123]
    assert saved["ativo"] is True
    assert saved["data_cadastro"] == datetime(2030, 10, 20, 12)


@pytest.mark.parametrize("campo", ["nome", "email", "telefone", "cargo"])
def test_cadastro_trabalhador_campo_ausente(client, database, trabalhador, campo):
    # Preparação
    del trabalhador[campo]
    before = snapshot(database)

    # Execução
    response = client.post("/trabalhadores/obra/123/", json=trabalhador)

    # Verificação
    assert response.status_code == 422
    assert response.get_json()
    assert snapshot(database) == before
