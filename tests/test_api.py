"""Contrato CT-01..17. SKIP indica dependência ausente, nunca aprovação."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from flask_jwt_extended import create_access_token, decode_token
from pymongo.errors import PyMongoError

from support import snapshot
from secret_audit import audit_git

BASE = "/api/v1/obras"
ID = "507f1f77bcf86cd799439011"
DETAIL = BASE + "/" + ID
routes = pytest.mark.routes


def assert_error(response, status, field=None):
    assert response.status_code == status, response.get_data(as_text=True)
    body = response.get_json()
    assert isinstance(body, dict), "Erro deve retornar objeto JSON"
    assert isinstance(body.get("mensagem"), str) and body["mensagem"].strip(), body
    if field:
        assert field in body.get("campos", []), body


def seed(database, obra, **changes):
    doc = deepcopy(obra)
    doc.update(
        _id=ObjectId(ID),
        estado="em andamento",
        autor="construtora_teste",
        data_registro=datetime(2030, 10, 10, 15, tzinfo=timezone.utc),
    )
    doc.update(changes)
    database.tbl_obras.insert_one(doc)
    return doc


def assert_created(response, database, payload):
    assert response.status_code == 201, response.get_data(as_text=True)
    body = response.get_json()
    identifier = body["id"]
    assert response.headers["Location"].endswith(BASE + "/" + identifier)
    saved = database.tbl_obras.find_one({"_id": ObjectId(identifier)})
    assert saved is not None, "201 sem documento persistido"
    for field, value in payload.items():
        assert saved[field] == value, f"Campo salvo incorreto: {field}"
        assert body[field] == value, f"Campo retornado incorreto: {field}"
    assert saved["autor"] == body["autor"] == "construtora_teste"
    instant = datetime.fromisoformat(body["data_registro"].replace("Z", "+00:00"))
    assert instant.tzinfo is not None
    assert instant == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert saved["data_registro"].replace(tzinfo=timezone.utc) == instant
    return body


@routes(("POST", "/login"), ("GET", BASE))
def test_ct01_login_valido_abre_obras(app, client, account, database):
    # Preparação
    before = snapshot(database)
    credentials = {"username": account["username"], "password": "Senha_teste123!"}

    # Execução
    login_response = client.post("/login", json=credentials)
    token = (login_response.get_json() or {}).get("access_token", "")
    list_response = client.get(BASE, headers={"Authorization": "Bearer " + token})

    # Verificação
    assert login_response.status_code == 200
    assert token
    with app.app_context():
        assert decode_token(token)["sub"] == account["username"]
    assert list_response.status_code == 200
    assert list_response.get_json()["obras"] == []
    assert snapshot(database) == before


@routes(("POST", "/login"))
@pytest.mark.parametrize(
    "username,password",
    [("construtora_teste", "Errada!"), ("inexistente", "Senha_teste123!")],
    ids=["senha-errada", "usuario-inexistente"],
)
def test_ct02_login_invalido(client, account, database, username, password):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.post("/login", json={"username": username, "password": password})

    # Verificação
    assert response.status_code == 401
    assert response.get_json() == {"msg": "Usuário ou senha inválidos"}
    assert "access_token" not in response.get_json()
    assert not response.headers.get("Set-Cookie")
    assert snapshot(database) == before


@pytest.mark.parametrize(
    "method,path",
    [
        pytest.param(method, path, marks=routes((method, path)), id=label)
        for method, path, label in [
            ("GET", BASE, "listar"),
            ("GET", DETAIL, "consultar"),
            ("POST", BASE, "criar"),
            ("PATCH", DETAIL, "editar"),
            ("DELETE", DETAIL, "excluir"),
        ]
    ],
)
@pytest.mark.parametrize("expired", [False, True], ids=["sem-token", "expirado"])
def test_ct03_acesso_negado(app, client, database, obra, method, path, expired):
    # Preparação
    seed(database, obra)
    before = snapshot(database)
    headers = {}
    if expired:
        with app.app_context():
            token = create_access_token(
                identity="construtora_teste", expires_delta=timedelta(seconds=-60)
            )
        headers = {"Authorization": "Bearer " + token}

    # Execução
    response = client.open(path, method=method, json=obra, headers=headers)

    # Verificação
    assert response.status_code == 401
    assert obra["nome"] not in response.get_data(as_text=True)
    assert "obras" not in response.get_json()
    assert snapshot(database) == before


@routes(("POST", "/login"), ("POST", "/logout"), ("GET", BASE), ("POST", BASE))
def test_ct04_logout_revoga_token(client, account, database, obra):
    # Preparação
    credentials = {"username": account["username"], "password": "Senha_teste123!"}

    # Execução
    login_response = client.post("/login", json=credentials)
    token = (login_response.get_json() or {}).get("access_token", "")
    headers = {"Authorization": "Bearer " + token}
    initial_response = client.get(BASE, headers=headers)
    logout_response = client.post("/logout", headers=headers)
    before = snapshot(database)
    read_response = client.get(BASE, headers=headers)
    write_response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert login_response.status_code == 200
    assert token
    assert initial_response.status_code == 200
    assert logout_response.status_code == 200
    assert read_response.status_code == 401
    assert write_response.status_code == 401
    assert snapshot(database) == before


def test_ct04_credenciais_no_conteudo_e_historico_git():
    # Preparação
    root = Path(__file__).resolve().parents[1]

    # Execução
    findings = audit_git(root)

    # Verificação
    assert not findings, "Possíveis segredos (valores omitidos): " + repr(findings)


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


@pytest.mark.atlas
@routes(("POST", BASE), ("GET", DETAIL))
def test_ct09_persistencia_atlas_apos_novo_processo(
    app, client, headers, database, obra
):
    # Preparação
    probe = Path(__file__).with_name("restart_probe.py")
    expected_fields = deepcopy(obra)

    # Execução
    created = client.post(BASE, json=obra, headers=headers)
    identifier = (created.get_json() or {}).get("id", "id-ausente")
    path = BASE + "/" + identifier
    with app.test_client() as fresh:
        reloaded = fresh.get(path, headers=headers)
    env = dict(os.environ, TEST_DATABASE_NAME=database.name, TEST_RESOURCE_PATH=path)
    result = subprocess.run(
        [sys.executable, str(probe)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Verificação
    created_body = assert_created(created, database, obra)
    assert reloaded.status_code == 200
    assert result.returncode == 0, "Falha no processo novo; credenciais omitidas"
    restarted = json.loads(result.stdout)
    assert restarted["status"] == 200
    for recovered in (reloaded.get_json(), restarted["body"]):
        assert recovered["id"] == identifier
        for field, value in expected_fields.items():
            assert recovered[field] == value, f"Campo não recuperado: {field}"
        for field in ("autor", "data_registro"):
            assert recovered[field] == created_body[field]
    assert restarted["body"] == reloaded.get_json()


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
