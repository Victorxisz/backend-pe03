"""Falhas e atomicidade da edição descritiva de obras."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from support import snapshot

ID = "507f1f77bcf86cd799439011"
PATH = "/api/v1/obras/" + ID


@pytest.fixture
def obra_salva(database, obra):
    documento = deepcopy(obra)
    documento.update(_id=ObjectId(ID), estado="em andamento")
    database.tbl_obras.insert_one(documento)
    return documento


@pytest.mark.parametrize(
    "dados,campos",
    [
        pytest.param({}, ["corpo"], id="objeto-vazio"),
        pytest.param([], ["corpo"], id="lista"),
        pytest.param("texto", ["corpo"], id="texto"),
        pytest.param({"nome": ""}, ["nome"], id="nome-vazio"),
        pytest.param({"cliente": []}, ["cliente"], id="cliente-lista"),
        pytest.param({"descricao": None}, ["descricao"], id="descricao-nula"),
        pytest.param({"localizacao": "  "}, ["localizacao"], id="endereco-vazio"),
        pytest.param({"nome": 42}, ["nome"], id="nome-numerico"),
        pytest.param(
            {"entrega.data": "2031-01-01"}, ["entrega.data"], id="prazo-campo-aninhado"
        ),
        pytest.param({"$set": {"estado": "concluída"}}, ["$set"], id="operador-mongo"),
        pytest.param(
            {"nome": "Mudança parcial proibida", "cliente": []},
            ["cliente"],
            id="valido-com-invalido",
        ),
        pytest.param(
            {"estado": "concluída", "motivo": "Mesmo com motivo não é esta rota"},
            ["estado", "motivo"],
            id="conclusao-com-motivo",
        ),
    ],
)
def test_ct16_ct17_rejeicao_sem_gravacao(
    client, headers, database, obra_salva, dados, campos
):
    # Preparação
    before = snapshot(database)

    # Execução
    with patch.object(type(database.tbl_obras), "find_one_and_update") as update:
        response = client.patch(PATH, json=dados, headers=headers)

    # Verificação
    assert response.status_code == 422
    assert response.get_json()["mensagem"]
    assert response.get_json()["campos"] == campos
    update.assert_not_called()
    assert snapshot(database) == before


@pytest.mark.parametrize(
    "identifier,status", [("invalido", 400), ("507f1f77bcf86cd799439099", 404)]
)
def test_ct16_id_invalido_ou_ausente(
    client, headers, database, obra_salva, identifier, status
):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.patch(
        "/api/v1/obras/" + identifier, json={"nome": "Novo nome"}, headers=headers
    )

    # Verificação
    assert response.status_code == status
    assert response.get_json()["campos"] == ["id"]
    assert snapshot(database) == before


@pytest.mark.parametrize(
    "erro",
    [
        pytest.param(
            OperationFailure("rejeição fictícia", code=121), id="gravacao-rejeitada"
        ),
        pytest.param(
            ServerSelectionTimeoutError("servidor fictício indisponível"),
            id="sem-servidor",
        ),
    ],
)
def test_ct16_falha_de_gravacao(client, headers, database, obra_salva, erro):
    # Preparação
    before = snapshot(database)
    changes = {"nome": "Novo nome"}

    # Execução
    with patch.object(
        type(database.tbl_obras), "find_one_and_update", side_effect=erro
    ) as update:
        response = client.patch(PATH, json=changes, headers=headers)

    # Verificação
    update.assert_called_once_with(
        {"_id": ObjectId(ID)}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    assert response.status_code == 500
    assert response.get_json() == {
        "mensagem": "Não foi possível salvar a correção da obra"
    }
    assert snapshot(database) == before


def test_ct16_edicao_nao_altera_outra_obra(client, headers, database, obra_salva):
    # Preparação
    outra = {**obra_salva, "_id": ObjectId(), "nome": "Outra obra"}
    database.tbl_obras.insert_one(outra)

    # Execução
    response = client.patch(PATH, json={"nome": "Nome corrigido"}, headers=headers)

    # Verificação
    assert response.status_code == 200
    assert database.tbl_obras.find_one({"_id": outra["_id"]}) == outra
    assert database.tbl_obras.count_documents({}) == 2
