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


def test_atualizacao_email_preserva_vinculo(client, headers, database, pessoa, obra_existente):
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"email": " novo@example.com "},
    )
    assert response.status_code == 200
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]}) == {
        **pessoa, "email": "novo@example.com"
    }
    consulta = client.get(f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers)
    assert consulta.status_code == 200
    assert [(item["id"], item["email"]) for item in consulta.get_json()] == [
        (str(pessoa["_id"]), "novo@example.com")
    ]


@pytest.mark.parametrize("remover", [False, True])
def test_atualizacao_substitui_obras_sem_enviar_cargo(
    client, headers, database, pessoa, obra_existente, remover
):
    nova_obra = {**obra_existente, "_id": ObjectId("ABCDEF123456ABCDEF123456")}
    database.tbl_obras.insert_one(nova_obra)
    esperado = [] if remover else [str(nova_obra["_id"])]
    obras = [] if remover else [str(nova_obra["_id"]).upper(), str(nova_obra["_id"])]
    obras_antes = list(database.tbl_obras.find())
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", json={"obras": obras}, headers=headers
    )
    assert response.status_code == 200
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]}) == {
        **pessoa, "obras": esperado
    }
    assert list(database.tbl_obras.find()) == obras_antes
    antiga = client.get(f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers)
    nova = client.get(f"/trabalhadores/obra/{nova_obra['_id']}/", headers=headers)
    assert antiga.status_code == nova.status_code == 200
    assert antiga.get_json() == []
    assert [item["id"] for item in nova.get_json()] == (
        [] if remover else [str(pessoa["_id"])]
    )


@pytest.mark.parametrize("payload", [
    {}, [], "texto", {"nome": ""}, {"nome": None}, {"cargo": 123},
    {"email": "invalido"}, {"telefone": "123"}, {"telefone": "+5511999999999"},
    {"ativo": False}, {"obras": "1"}, {"obras": [0]}, {"obras": [-1]},
    {"obras": [True]}, {"obras": ["1"]}, {"obras": [1.5]},
    {"obras": [1, 2]}, {"obras": [None]}, {"obras": [""]},
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


def test_exclusao_remove_apenas_trabalhador_informado(client, headers, database, pessoa, obra_existente):
    outro = {**pessoa, "_id": ObjectId(), "obras": []}
    database.tbl_trabalhadores.insert_one(outro)

    response = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)

    assert response.status_code == 200
    assert list(database.tbl_trabalhadores.find()) == [outro]
    consulta = client.get(f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers)
    assert consulta.status_code == 200
    assert consulta.get_json() == []


def test_vinculo_com_obra_inexistente_rejeita_toda_edicao(
    client, headers, database, pessoa, obra_existente
):
    ausente = str(ObjectId())
    antes = snapshot(database)
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"nome": "Não deve mudar", "obras": [str(obra_existente['_id']), ausente]},
    )
    assert response.status_code == 422
    assert response.get_json()["obras"] == [ausente]
    assert snapshot(database) == antes


@pytest.mark.parametrize("durante_iteracao", [False, True])
def test_falha_ao_validar_obras_nao_atualiza_trabalhador(
    client, headers, database, pessoa, obra_existente,
    modulo_trabalhadores, monkeypatch, durante_iteracao
):
    antes = snapshot(database)

    def cursor_com_erro():
        yield {"_id": obra_existente["_id"]}
        raise PyMongoError("detalhe interno simulado")

    def falhar(*args, **kwargs):
        if durante_iteracao:
            return cursor_com_erro()
        raise PyMongoError("detalhe interno simulado")

    with monkeypatch.context() as context:
        context.setattr(modulo_trabalhadores.colecao_obras, "find", falhar)
        response = client.patch(
            f"/trabalhadores/{pessoa['_id']}/", headers=headers,
            json={"obras": [str(obra_existente['_id'])]},
        )
    assert response.status_code == 503
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == antes


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
    assert response.status_code == 503
    assert "erro" in response.get_json()
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == before


@pytest.mark.parametrize("method,path", [
    ("POST", "/trabalhadores/obra/{obra}/"),
    ("GET", "/trabalhadores/{id}/"),
    ("PATCH", "/trabalhadores/{id}/"), ("DELETE", "/trabalhadores/{id}/"),
    ("GET", "/trabalhadores/nome/João/"), ("GET", "/trabalhadores/cargo/pedreiro/"),
    ("GET", "/trabalhadores/obra/{obra}/"),
])
@pytest.mark.parametrize("situacao,status", [
    ("ausente", 401), ("expirado", 401), ("revogado", 401), ("refresh", 422),
    ("conta-excluida", 401), ("conta-inativa", 401), ("perfil-invalido", 403),
])
def test_todas_rotas_exigem_access_token_valido(
    client, database, pessoa, obra_existente, account, emitir_headers, method, path, situacao, status
):
    auth = {}
    if situacao != "ausente":
        if situacao == "conta-excluida":
            database.tbl_construtora.delete_one({"_id": account["_id"]})
        elif situacao == "conta-inativa":
            database.tbl_construtora.update_one(
                {"_id": account["_id"]}, {"$set": {"ativo": False}}
            )
        if situacao == "revogado":
            database.tbl_sessoes_revogadas.insert_one({"_id": "sessao-revogada"})
        claims = {"sessao_id": "sessao-revogada"}
        if situacao == "perfil-invalido":
            claims["tipo"] = "trabalhador"
        auth = emitir_headers(
            "refresh" if situacao == "refresh" else "access",
            claims=claims, expirado=situacao == "expirado",
        )
    before = snapshot(database)

    response = client.open(
        path.format(id=pessoa["_id"], obra=obra_existente["_id"]),
        method=method, json={"nome": "Teste"}, headers=auth,
    )

    assert response.status_code == status
    assert snapshot(database) == before
    assert pessoa["email"] not in response.get_data(as_text=True)
