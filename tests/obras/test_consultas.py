"""CT-11 a CT-15: consulta, filtros e atraso derivado."""

from datetime import datetime, timezone
import pytest
from bson import ObjectId
from support import snapshot
from support_obras import BASE, DETAIL, ID, assert_error, seed

routes = pytest.mark.routes


@pytest.fixture
def two_works(database, obra):
    a = seed(database, obra, nome="Residencial Aurora", cliente="Cliente Aurora")
    b = seed(
        database,
        obra,
        _id=ObjectId(),
        nome="Casa Ipê",
        cliente="Cliente Ipê",
        data_registro=datetime(2030, 11, 15, 9, tzinfo=timezone.utc),
        entrega={
            "modalidade": "intervalo_estimado",
            "inicio": "2031-01-01",
            "fim": "2031-02-01",
        },
    )
    return a, b


@routes(("GET", BASE), ("GET", DETAIL))
def test_ct11_lista_e_detalhes(client, headers, database, two_works):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.get(BASE, headers=headers)
    details = [
        client.get(BASE + "/" + str(doc["_id"]), headers=headers) for doc in two_works
    ]

    # Verificação
    assert response.status_code == 200
    assert {d["id"] for d in response.get_json()["obras"]} == {
        str(d["_id"]) for d in two_works
    }
    for doc, response in zip(two_works, details):
        assert response.status_code == 200
        for field in ("nome", "cliente", "entrega", "descricao", "localizacao"):
            assert response.get_json()[field] == doc[field]
    assert snapshot(database) == before


@routes(("GET", DETAIL + "/marcos"))
def test_ct11_marcos_nao_vazam(client, headers, database, two_works):
    # Preparação
    a, b = two_works
    marco = {"_id": ObjectId(), "obra_id": a["_id"], "nome": "Marco exclusivo A"}
    database.tbl_marcos.insert_one(marco)
    before = snapshot(database)

    # Execução
    ra = client.get(BASE + "/" + str(a["_id"]) + "/marcos", headers=headers)
    rb = client.get(BASE + "/" + str(b["_id"]) + "/marcos", headers=headers)

    # Verificação
    assert ra.status_code == rb.status_code == 200
    assert [m["id"] for m in ra.get_json()["marcos"]] == [str(marco["_id"])]
    assert rb.get_json()["marcos"] == []
    assert snapshot(database) == before


@routes(("GET", BASE))
@pytest.mark.parametrize(
    "query,indices",
    [
        ({"nome": "Aurora"}, [0]),
        ({"cliente": "Cliente Ipê"}, [1]),
        ({"registroDe": "2030-10-10", "registroAte": "2030-10-10"}, [0]),
        ({"entregaDe": "2030-12-20", "entregaAte": "2030-12-20"}, [0]),
        ({"entregaDe": "2031-02-01", "entregaAte": "2031-02-01"}, [1]),
    ],
    ids=["nome", "cliente", "registro-inclusivo", "entrega-exata", "fim-intervalo"],
)
def test_ct12_filtros(client, headers, database, two_works, query, indices):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.get(BASE, query_string=query, headers=headers)

    # Verificação
    assert response.status_code == 200
    assert {d["id"] for d in response.get_json()["obras"]} == {
        str(two_works[i]["_id"]) for i in indices
    }
    assert snapshot(database) == before


@routes(("GET", BASE))
@pytest.mark.parametrize(
    "cliente,indices", [("Cliente Aurora", [0]), ("Cliente Ipê", [])]
)
def test_ct13_intersecao(client, headers, database, two_works, cliente, indices):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.get(
        BASE, query_string={"nome": "Aurora", "cliente": cliente}, headers=headers
    )

    # Verificação
    assert response.status_code == 200
    assert [d["id"] for d in response.get_json()["obras"]] == [
        str(two_works[i]["_id"]) for i in indices
    ]
    assert snapshot(database) == before


@routes(("GET", DETAIL))
@pytest.mark.parametrize("mode", ["data_exata", "intervalo_estimado"])
@pytest.mark.parametrize(
    "end,late", [("2030-10-21", False), ("2030-10-20", False), ("2030-10-19", True)]
)
def test_ct14_atraso_derivado(client, headers, database, obra, mode, end, late):
    # Preparação
    entrega = (
        {"modalidade": mode, "data": end}
        if mode == "data_exata"
        else {"modalidade": mode, "inicio": "2030-10-01", "fim": end}
    )
    seed(database, obra, entrega=entrega)
    before = snapshot(database)

    # Execução
    response = client.get(DETAIL, headers=headers)

    # Verificação
    assert response.status_code == 200
    assert ("atrasada" in response.get_json()["alertas"]) is late
    assert response.get_json()["estado"] == "em andamento"
    assert snapshot(database) == before


@routes(("GET", DETAIL))
def test_ct15_id_inexistente(client, headers, database, obra):
    # Preparação
    seed(database, obra, _id=ObjectId())
    before = snapshot(database)

    # Execução
    response = client.get(DETAIL, headers=headers)

    # Verificação
    assert_error(response, 404)
    assert obra["nome"] not in response.get_data(as_text=True)
    assert snapshot(database) == before


@routes(("GET", BASE))
@pytest.mark.parametrize(
    "query,field",
    [
        ({"registroDe": "inválida"}, "registroDe"),
        ({"registroAte": "2030-02-30"}, "registroAte"),
        ({"entregaDe": "20/10/2030"}, "entregaDe"),
        ({"entregaAte": "2030-13-01"}, "entregaAte"),
        ({"registroDe": "2030-10-31", "registroAte": "2030-10-01"}, "registroAte"),
        ({"entregaDe": "2030-12-31", "entregaAte": "2030-12-01"}, "entregaAte"),
    ],
)
def test_ct15_filtros_invalidos(client, headers, database, two_works, query, field):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.get(BASE, query_string=query, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before

