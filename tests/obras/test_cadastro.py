"""CT-05 a CT-10: cadastro e validações de obras."""

from unittest.mock import patch
import pytest
from pymongo.errors import PyMongoError
from support import snapshot
from support_obras import BASE, DETAIL, ID, assert_error, assert_created, seed

routes = pytest.mark.routes


def test_rotas_de_obras_seguem_contrato(app):
    # Preparação
    endpoints = {"cadastrar_obra", "corrigir_descricao"}

    # Execução
    caminhos = {
        regra.rule for regra in app.url_map.iter_rules()
        if regra.endpoint.rsplit(".", 1)[-1] in endpoints
    }

    # Verificação
    assert caminhos == {"/obras", "/obras/<string:obra_id>"}


@routes(("POST", BASE))
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

    # Verificação
    assert_created(response, database, obra)
    assert database.tbl_obras.count_documents({}) == 1
    saved = database.tbl_obras.find_one()
    assert set(saved["entrega"]) == set(obra["entrega"])


@routes(("POST", BASE), ("GET", DETAIL))
@pytest.mark.parametrize("interval", [False, True], ids=["data-exata", "intervalo"])
def test_ct05_ct06_releitura_http(client, headers, database, obra, interval):
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
    body = assert_created(response, database, obra)
    fetched = client.get(BASE + "/" + body["id"], headers=headers)

    # Verificação
    assert fetched.status_code == 200
    for field in (*obra, "autor", "data_registro", "id"):
        assert fetched.get_json()[field] == body[field]


def test_ct05_cadastro_e_edicao(client, headers, database, obra):
    # Preparação
    changes = {"cliente": "Cliente corrigido"}

    # Execução
    created = client.post("/obras", json=obra, headers=headers)
    body = created.get_json()
    path = "/obras/" + body["id"]
    edited = client.patch(path, json=changes, headers=headers)

    # Verificação
    assert created.status_code == 201
    assert created.headers["Location"] == path
    assert "cliente_referencia" not in body
    assert "criado_em" not in body
    assert edited.status_code == 200
    saved = database.tbl_obras.find_one()
    assert saved["cliente"] == changes["cliente"]
    assert saved["autor"] == body["autor"]


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
        ({"cliente": []}, "cliente"),
        ({"descricao": None}, "descricao"),
        ({"localizacao": 123}, "localizacao"),
        ({"tipo": "apartamento"}, "tipo"),
        ({"tipo": []}, "tipo"),
        ({"inicio": "2030-02-30"}, "inicio"),
        ({"inicio": "20300115"}, "inicio"),
        ({"inicio": 20300115}, "inicio"),
        ({"entrega": None}, "entrega"),
        ({"entrega": []}, "entrega"),
        ({"entrega": "2030-12-20"}, "entrega"),
        ({"entrega": {}}, "entrega.modalidade"),
        ({"entrega": {"modalidade": []}}, "entrega.modalidade"),
        ({"entrega": {"modalidade": "data_exata"}}, "entrega.data"),
        ({"entrega": {"modalidade": "data_exata", "data": None}}, "entrega.data"),
        (
            {"entrega": {"modalidade": "intervalo_estimado", "fim": "2030-12-20"}},
            "entrega.inicio",
        ),
        (
            {"entrega": {"modalidade": "intervalo_estimado", "inicio": "2030-11-01"}},
            "entrega.fim",
        ),
        (
            {"entrega": {"modalidade": "intervalo_estimado", "data": "2030-12-20"}},
            "entrega",
        ),
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
@pytest.mark.parametrize("body", ["null", "[]", '"texto"', "123", "true", "{invalido"])
def test_ct08_corpo_invalido(client, headers, database, body):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.post(BASE, data=body, content_type="application/json", headers=headers)

    # Verificação
    assert_error(response, 422, "corpo")
    assert snapshot(database) == before


@routes(("POST", BASE))
@pytest.mark.parametrize("field", ["cliente_referencia", "criado_em", "estado", "critica", "extra"])
def test_ct08_campos_nao_permitidos(client, headers, database, obra, field):
    # Preparação
    obra[field] = "valor enviado pelo cliente"
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before


@routes(("POST", BASE))
@pytest.mark.parametrize("field", ["nome", "tipo", "cliente", "localizacao", "descricao", "inicio", "entrega"])
def test_ct08_campo_obrigatorio_ausente(client, headers, database, obra, field):
    # Preparação
    del obra[field]
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_error(response, 422, field)
    assert snapshot(database) == before


@routes(("POST", BASE))
def test_ct06_intervalo_de_um_dia(client, headers, database, obra):
    # Preparação
    obra["entrega"] = {
        "modalidade": "intervalo_estimado",
        "inicio": "2030-12-20",
        "fim": "2030-12-20",
    }

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert_created(response, database, obra)


def test_ct03_cadastro_sem_token(client, database, obra):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=obra)

    # Verificação
    assert response.status_code == 401
    assert snapshot(database) == before


def test_ct04_logout_bloqueia_cadastro(client, headers, database, obra):
    # Preparação
    logout = client.post("/construtora/logout/", headers=headers)
    assert logout.status_code == 200
    before = snapshot(database)

    # Execução
    response = client.post(BASE, json=obra, headers=headers)

    # Verificação
    assert response.status_code == 401
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

