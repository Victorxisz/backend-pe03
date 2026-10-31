"""Regressão das rotas já existentes na branch MatheusHermida (fora CT-01..17)."""

from datetime import datetime

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot


def test_cadastro_trabalhador(
    client, headers, database, trabalhador, obra_existente
):
    # Preparação
    obra_id = str(obra_existente["_id"])
    path = f"/trabalhadores/obra/{obra_id}/"

    # Execução
    response = client.post(path, json=trabalhador, headers=headers)

    # Verificação
    assert response.status_code == 201
    body = response.get_json()
    assert body["mensagem"] == "Trabalhador criado com sucesso e vinculado à obra"
    assert body["obra_id"] == obra_id
    saved = database.tbl_trabalhadores.find_one({"_id": ObjectId(body["id"])})
    assert saved is not None
    for field, value in trabalhador.items():
        assert saved[field] == value
    assert saved["obras"] == [obra_id]
    assert saved["ativo"] is True
    assert saved["data_cadastro"] == datetime(2030, 10, 20, 12)
    assert database.tbl_trabalhadores.count_documents({}) == 1
    assert database.tbl_obras.find_one({"_id": obra_existente["_id"]}) == obra_existente
    consulta = client.get(path, headers=headers)
    assert consulta.status_code == 200
    assert [item["id"] for item in consulta.get_json()] == [body["id"]]


@pytest.mark.parametrize("campo", ["nome", "email", "telefone", "cargo"])
def test_cadastro_trabalhador_campo_ausente(
    client, headers, database, trabalhador, campo, obra_existente
):
    # Preparação
    del trabalhador[campo]
    before = snapshot(database)
    path = f"/trabalhadores/obra/{obra_existente['_id']}/"

    # Execução
    response = client.post(path, json=trabalhador, headers=headers)

    # Verificação
    assert response.status_code == 422
    assert response.get_json() == {
        "erro": f"O campo '{campo}' deve ser um texto preenchido"
    }
    assert snapshot(database) == before


@pytest.mark.parametrize("payload", [[], "texto", {"nome": " "}, {"email": "invalido"},
    {"telefone": "123"}, {"telefone": "+55 11 99999-9999"}, {"cargo": 123}])
def test_cadastro_dados_invalidos(
    client, headers, database, trabalhador, obra_existente, payload
):
    dados = {**trabalhador, **payload} if isinstance(payload, dict) else payload
    before = snapshot(database)

    response = client.post(
        f"/trabalhadores/obra/{obra_existente['_id']}/", json=dados, headers=headers
    )

    assert response.status_code == 422
    assert "erro" in response.get_json()
    assert snapshot(database) == before


@pytest.mark.parametrize("corpo", [None, '{"nome":', "null"])
def test_cadastro_corpo_ausente_ou_malformado(
    client, headers, database, obra_existente, corpo
):
    before = snapshot(database)
    response = client.post(
        f"/trabalhadores/obra/{obra_existente['_id']}/", data=corpo,
        content_type="application/json", headers=headers,
    )
    assert response.status_code == 422
    assert snapshot(database) == before


def test_cadastro_id_obra_invalido(client, headers, database, trabalhador):
    before = snapshot(database)
    response = client.post("/trabalhadores/obra/invalido/", json=trabalhador, headers=headers)
    assert response.status_code == 400
    assert snapshot(database) == before


def test_cadastro_obra_inexistente_nao_cria_orfao(
    client, headers, database, trabalhador
):
    before = snapshot(database)
    response = client.post(
        f"/trabalhadores/obra/{ObjectId()}/", json=trabalhador, headers=headers
    )
    # Regressão: o status deve ficar fora de jsonify, na tupla de retorno.
    assert snapshot(database) == before
    assert response.status_code == 404
    assert response.get_json() == {"erro": "Obra não encontrada"}


@pytest.mark.parametrize("telefone,esperado", [
    (" (11) 3333-4444 ", "1133334444"), (" (11) 99999-9999 ", "11999999999"),
])
def test_cadastro_normaliza_campos_e_ignora_campos_controlados_pela_api(
    client, headers, database, obra_existente, telefone, esperado, account
):
    response = client.post(
        f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers,
        json={"nome": " Ana ", "email": " ana@example.com ", "telefone": telefone,
              "cargo": " ENGENHEIRO ", "ativo": False, "obras": [999],
              "data_cadastro": "2000-01-01", "senha": "ignorada"},
    )

    assert response.status_code == 201
    saved = database.tbl_trabalhadores.find_one({"_id": ObjectId(response.get_json()["id"])})
    assert saved == {
        "_id": saved["_id"], "nome": "Ana", "email": "ana@example.com",
        "telefone": esperado, "cargo": "engenheiro", "ativo": True,
        "obras": [str(obra_existente["_id"])], "data_cadastro": datetime(2030, 10, 20, 12),
        "construtora_id": str(account["_id"]),
    }
    assert database.tbl_obras.find_one({"_id": obra_existente["_id"]}) == obra_existente


@pytest.mark.parametrize("collection,operation", [
    ("colecao_obras", "find_one"),
    ("colecao_trabalhadores", "insert_one"),
])
def test_cadastro_trata_falha_em_cada_etapa(
    client, headers, database, trabalhador, obra_existente,
    modulo_trabalhadores, monkeypatch, collection, operation
):
    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    before = snapshot(database)
    with monkeypatch.context() as context:
        context.setattr(getattr(modulo_trabalhadores, collection), operation, falhar)
        response = client.post(
            f"/trabalhadores/obra/{obra_existente['_id']}/", json=trabalhador, headers=headers
        )

    assert response.status_code == 503
    assert "erro" in response.get_json()
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == before
