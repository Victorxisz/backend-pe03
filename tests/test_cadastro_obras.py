"""Validação antes da escrita, proteção da consulta e erros do cadastro."""

from unittest.mock import patch

import pytest
from freezegun import freeze_time
from pymongo.errors import PyMongoError

BASE = "/api/v1/obras"
ID = "507f1f77bcf86cd799439011"
pytestmark = pytest.mark.routes(("POST", BASE), ("GET", BASE + "/" + ID))


@pytest.mark.parametrize("campo", ["nome", "tipo", "cliente", "localizacao", "descricao", "inicio", "entrega"])
def test_campo_obrigatorio_nao_chega_ao_banco(client, headers, database, obra, campo):
    del obra[campo]
    with patch.object(type(database.tbl_obras), "insert_one") as inserir:
        response = client.post(BASE, json=obra, headers=headers)

    assert response.status_code == 422
    assert campo in response.get_json()["campos"]
    inserir.assert_not_called()


@pytest.mark.parametrize("dados", [None, [], "obra", 123])
def test_corpo_invalido_nao_chega_ao_banco(client, headers, database, dados):
    with patch.object(type(database.tbl_obras), "insert_one") as inserir:
        response = client.post(BASE, json=dados, headers=headers)

    assert response.status_code == 422
    assert response.get_json()["campos"] == ["corpo"]
    inserir.assert_not_called()


@pytest.mark.parametrize("campo", ["_id", "autor", "data_registro", "estado"])
def test_campos_do_servidor_nao_chegam_ao_banco(client, headers, database, obra, campo):
    obra[campo] = "valor enviado pelo cliente"
    with patch.object(type(database.tbl_obras), "insert_one") as inserir:
        response = client.post(BASE, json=obra, headers=headers)

    assert response.status_code == 422
    assert campo in response.get_json()["campos"]
    inserir.assert_not_called()


@pytest.mark.parametrize("metodo,path", [("POST", BASE), ("GET", BASE + "/" + ID)])
def test_cadastro_consulta_exigem_token(client, database, obra, metodo, path):
    response = client.open(path, method=metodo, json=obra)

    assert response.status_code == 401
    assert database.tbl_obras.count_documents({}) == 0


@pytest.mark.parametrize("identifier,status", [("invalido", 400), (ID, 404)])
def test_consulta_id_invalido_ou_ausente(client, headers, identifier, status):
    response = client.get(BASE + "/" + identifier, headers=headers)

    assert response.status_code == status
    assert response.get_json()["campos"] == ["id"]


def test_falha_consulta_nao_expoe_erro_do_driver(client, headers, database):
    with patch.object(
        type(database.tbl_obras), "find_one", side_effect=PyMongoError("detalhe privado")
    ):
        response = client.get(BASE + "/" + ID, headers=headers)

    assert response.status_code == 500
    assert response.get_json()["mensagem"]
    assert "detalhe privado" not in response.get_data(as_text=True)


def test_data_registro_igual_apos_leitura(client, headers, obra):
    with freeze_time("2030-10-20 12:00:00.123456"):
        criada = client.post(BASE, json=obra, headers=headers)
        assert criada.status_code == 201
        consultada = client.get(criada.headers["Location"], headers=headers)

    assert consultada.status_code == 200
    assert consultada.get_json() == criada.get_json()
