"""UC-04 / CT-14, CT-16 e CT-17: edição descritiva de obras."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from support import snapshot
from support_obras import BASE, DETAIL, ID, assert_error, seed

PATH = DETAIL
routes = pytest.mark.routes


@routes(("PATCH", DETAIL))
def test_ct14_alerta_nao_editavel(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    before = snapshot(database)

    # Execução
    response = client.patch(DETAIL, json={"alertas": ["atrasada"]}, headers=headers)

    # Verificação
    assert_error(response, 422, "alertas")
    assert snapshot(database) == before


@routes(("PATCH", DETAIL))
@pytest.mark.parametrize(
    "changes",
    [
        {"nome": "Nome corrigido"},
        {"localizacao": "Endereço fictício 20"},
        {"descricao": "Descrição corrigida"},
        {"cliente": "Outro cliente fictício"},
        {"nome": "Nome novo", "cliente": "Cliente novo"},
    ],
)
def test_ct16_edicao_parcial(client, headers, database, obra, changes):
    # Preparação
    seed(database, obra)
    before = database.tbl_obras.find_one()

    # Execução
    response = client.patch(DETAIL, json=changes, headers=headers)

    # Verificação
    assert response.status_code == 200
    saved = database.tbl_obras.find_one()
    assert saved == {**before, **changes}, "Só os campos enviados devem mudar"
    assert isinstance(saved["cliente"], str)
    assert database.tbl_obras.count_documents({}) == 1
    for field, value in changes.items():
        assert response.get_json()[field] == value


@routes(("PATCH", DETAIL))
@pytest.mark.parametrize(
    "changes,field",
    [
        ({"entrega": {"modalidade": "data_exata", "data": "2031-01-01"}}, "entrega"),
        (
            {
                "entrega": {
                    "modalidade": "intervalo_estimado",
                    "inicio": "2031-01-01",
                    "fim": "2031-02-01",
                }
            },
            "entrega",
        ),
        ({"estado": "concluída"}, "estado"),
        ({"data_conclusao": "2030-10-20"}, "data_conclusao"),
        ({"nome": "Não pode mudar parcialmente", "estado": "concluída"}, "estado"),
    ],
)
def test_ct17_bloqueia_prazo_conclusao(client, headers, database, obra, changes, field):
    # Preparação
    seed(database, obra)
    before = snapshot(database)

    # Execução
    response = client.patch(DETAIL, json=changes, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before, "Rejeição deve preservar obra e histórico"


@routes(("PATCH", DETAIL), ("GET", DETAIL))
def test_ct16_releitura_http(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    changes = {"nome": "Nome corrigido"}

    # Execução
    updated = client.patch(DETAIL, json=changes, headers=headers)
    fetched = client.get(DETAIL, headers=headers)

    # Verificação
    assert updated.status_code == 200
    assert fetched.status_code == 200
    for field, value in {**obra, **changes}.items():
        assert fetched.get_json()[field] == value


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
        BASE + "/" + identifier, json={"nome": "Novo nome"}, headers=headers
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
