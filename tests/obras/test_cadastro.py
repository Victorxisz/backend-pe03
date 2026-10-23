"""CT-05 a CT-10: cadastro e validações de obras."""

from unittest.mock import patch
import pytest
from pymongo.errors import PyMongoError
from support import snapshot
from support_obras import BASE, DETAIL, ID, assert_error, assert_created, seed

routes = pytest.mark.routes


@routes(("POST", BASE), ("GET", DETAIL))
@pytest.mark.parametrize(
    "interval",
    [False, True],
    ids=["CT-05-casa-data-exata", "CT-06-apartamentos-intervalo"],
)
def test_ct05_ct06_criacao(client, headers, database, obra, interval):
    # Preparação
    if interval:
        obra.update(
            tipo="apartamentos",
            entrega={
                "modalidade": "intervalo_estimado",
                "inicio": "2030-11-01",
                "fim": "2030-12-20",
            },
        )

    # Execução
    response = client.post(BASE, json=obra, headers=headers)
    identifier = (response.get_json() or {}).get("id", "id-ausente")
    fetched = client.get(BASE + "/" + identifier, headers=headers)

    # Verificação
    assert_created(response, database, obra)
    assert database.tbl_obras.count_documents({}) == 1
    saved = database.tbl_obras.find_one()
    assert set(saved["entrega"]) == set(obra["entrega"])
    assert fetched.status_code == 200
    for field in obra:
        assert fetched.get_json()[field] == obra[field]


@routes(("POST", BASE))
def test_ct05_auditoria_nao_controlada_pelo_cliente(client, headers, database, obra):
    # Preparação
    submitted = {
        **obra,
        "autor": "intruso_ficticio",
        "data_registro": "2000-01-01T00:00:00Z",
    }
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=submitted, headers=headers)

    # Verificação
    if response.status_code == 422:
        assert_error(response, 422)
        assert {"autor", "data_registro"} & set(response.get_json().get("campos", []))
        assert snapshot(database) == before
    else:
        # A API pode rejeitar os campos reservados ou gerar seus próprios valores.
        assert_created(response, database, obra)
        assert database.tbl_obras.count_documents({}) == 1


@routes(("POST", BASE))
@pytest.mark.parametrize(
    "entrega,field",
    [
        (
            {
                "modalidade": "data_exata",
                "data": "2030-12-20",
                "inicio": "2030-11-01",
                "fim": "2030-12-20",
            },
            "entrega",
        ),
        ({"data": "2030-12-20"}, "entrega.modalidade"),
        ({"inicio": "2030-11-01", "fim": "2030-12-20"}, "entrega.modalidade"),
        (None, "entrega"),
    ],
    ids=[
        "modalidades-juntas",
        "data-sem-modalidade",
        "intervalo-sem-modalidade",
        "sem-entrega",
    ],
)
def test_ct07_modalidade_invalida(client, headers, database, obra, entrega, field):
    # Preparação
    seed(database, obra)
    if entrega is None:
        del obra["entrega"]
    else:
        obra["entrega"] = entrega
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before


@routes(("POST", BASE))
@pytest.mark.parametrize(
    "changes,field",
    [
        ({"nome": ""}, "nome"),
        ({"nome": "   "}, "nome"),
        (
            {"entrega": {"modalidade": "data_exata", "data": "2030-02-30"}},
            "entrega.data",
        ),
        ({"entrega": {"modalidade": "data_exata", "data": "inválida"}}, "entrega.data"),
        (
            {
                "entrega": {
                    "modalidade": "intervalo_estimado",
                    "inicio": "2030-02-30",
                    "fim": "2030-12-20",
                }
            },
            "entrega.inicio",
        ),
        (
            {
                "entrega": {
                    "modalidade": "intervalo_estimado",
                    "inicio": "2030-11-01",
                    "fim": "2030-13-20",
                }
            },
            "entrega.fim",
        ),
        (
            {
                "entrega": {
                    "modalidade": "intervalo_estimado",
                    "inicio": "2030-12-20",
                    "fim": "2030-11-01",
                }
            },
            "entrega.fim",
        ),
    ],
)
def test_ct08_campos_invalidos(client, headers, database, obra, changes, field):
    # Preparação
    seed(database, obra)
    before = snapshot(database)
    obra.update(changes)

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before


@routes(("POST", BASE))
def test_ct10_falha_banco(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    before = snapshot(database)

    # Execução
    with patch.object(
        type(database.tbl_obras),
        "insert_one",
        side_effect=PyMongoError("falha fictícia"),
    ) as insert:
        response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_error(response, 500)
    insert.assert_called_once()
    assert not response.headers.get("Location")
    assert "id" not in response.get_json()
    assert snapshot(database) == before

