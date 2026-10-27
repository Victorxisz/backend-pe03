"""Edição, exclusão e autenticação ainda não cobertas por test_cadastro.py."""

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot


def test_atualizacao_parcial_normaliza_e_preserva_outro_trabalhador(
    client, headers, database, pessoa
):
    outro = {**pessoa, "_id": ObjectId(), "email": "outra@example.com"}
    database.tbl_trabalhadores.insert_one(outro)
    obra_antes = list(database.tbl_obras.find())

    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"nome": " Ana Silva ", "cargo": " ENGENHEIRO ", "telefone": "(11) 98888-7777"},
    )

    assert response.status_code == 200
    assert response.get_json()["id"] == str(pessoa["_id"])
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]}) == {
        **pessoa, "nome": "Ana Silva", "cargo": "engenheiro", "telefone": "11988887777"
    }
    assert database.tbl_trabalhadores.find_one({"_id": outro["_id"]}) == outro
    assert list(database.tbl_obras.find()) == obra_antes


def test_atualizacao_email(client, headers, database, pessoa):
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"email": " novo@example.com "},
    )
    assert response.status_code == 200
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]}) == {
        **pessoa, "email": "novo@example.com"
    }


@pytest.mark.parametrize("obras,esperado", [([], []), ([1, 2, 1], [1, 2])])
def test_atualizacao_substitui_obras_conforme_contrato_atual(
    client, headers, database, pessoa, obras, esperado
):
    # O validador atual aceita códigos inteiros no PATCH; o POST usa ObjectId.
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", json={"obras": obras}, headers=headers
    )
    assert response.status_code == 200
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]}) == {
        **pessoa, "obras": esperado
    }


@pytest.mark.parametrize("payload", [
    {}, [], "texto", {"nome": ""}, {"nome": None}, {"cargo": 123},
    {"email": "invalido"}, {"telefone": "123"}, {"telefone": "+5511999999999"},
    {"ativo": False}, {"obras": "1"}, {"obras": [0]}, {"obras": [-1]},
    {"obras": [True]}, {"obras": ["1"]}, {"obras": [1.5]},
])
def test_atualizacao_invalida_nao_grava(client, headers, database, pessoa, payload):
    before = snapshot(database)
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", json=payload, headers=headers
    )
    assert response.status_code == 422
    assert "erro" in response.get_json()
    assert snapshot(database) == before


@pytest.mark.parametrize("corpo", [None, '{"nome":', "null"])
def test_atualizacao_corpo_ausente_ou_malformado(
    client, headers, database, pessoa, corpo
):
    before = snapshot(database)
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", data=corpo,
        content_type="application/json", headers=headers,
    )
    assert response.status_code == 422
    assert snapshot(database) == before


def test_atualizacao_sem_mudanca_retorna_sucesso(client, headers, database, pessoa):
    before = snapshot(database)
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", json={"nome": pessoa["nome"]}, headers=headers
    )
    assert response.status_code == 200
    assert snapshot(database) == before


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("identificador,status", [
    ("invalido", 400), ("507f191e810c19729de860ea", 404),
])
def test_id_invalido_ou_trabalhador_inexistente(
    client, headers, database, pessoa, method, identificador, status
):
    before = snapshot(database)
    response = client.open(
        f"/trabalhadores/{identificador}/", method=method,
        json={"nome": "Novo Nome"}, headers=headers,
    )
    assert response.status_code == status
    assert snapshot(database) == before


def test_exclusao_remove_apenas_trabalhador_informado(client, headers, database, pessoa):
    outro = {**pessoa, "_id": ObjectId(), "email": "outra@example.com"}
    database.tbl_trabalhadores.insert_one(outro)

    response = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)

    assert response.status_code == 200
    assert list(database.tbl_trabalhadores.find()) == [outro]


@pytest.mark.parametrize("method,operation", [("PATCH", "update_one"), ("DELETE", "delete_one")])
def test_falha_na_gravacao_preserva_banco(
    client, headers, database, pessoa, modulo_trabalhadores, monkeypatch, method, operation
):
    before = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    with monkeypatch.context() as context:
        context.setattr(modulo_trabalhadores.colecao_trabalhadores, operation, falhar)
        response = client.open(
            f"/trabalhadores/{pessoa['_id']}/", method=method,
            json={"nome": "Novo Nome"}, headers=headers,
        )
    assert response.status_code == 500
    assert "erro" in response.get_json()
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == before


@pytest.mark.parametrize("method,path", [
    ("POST", "/trabalhadores/obra/{obra}/"),
    ("PATCH", "/trabalhadores/{id}/"), ("DELETE", "/trabalhadores/{id}/"),
    ("GET", "/trabalhadores/nome/João/"), ("GET", "/trabalhadores/cargo/pedreiro/"),
    ("GET", "/trabalhadores/obra/{obra}/"),
])
@pytest.mark.parametrize("situacao,status", [
    ("ausente", 401), ("expirado", 401), ("revogado", 401), ("refresh", 422),
])
def test_todas_rotas_exigem_access_token_valido(
    client, database, pessoa, obra_existente, emitir_headers, method, path, situacao, status
):
    auth = {}
    if situacao != "ausente":
        if situacao == "revogado":
            database.tbl_sessoes_revogadas.insert_one({"_id": "sessao-revogada"})
        auth = emitir_headers(
            "refresh" if situacao == "refresh" else "access",
            claims={"sessao_id": "sessao-revogada"}, expirado=situacao == "expirado",
        )
    before = snapshot(database)

    response = client.open(
        path.format(id=pessoa["_id"], obra=obra_existente["_id"]),
        method=method, json={"nome": "Teste"}, headers=auth,
    )

    assert response.status_code == status
    assert snapshot(database) == before
    assert pessoa["email"] not in response.get_data(as_text=True)
