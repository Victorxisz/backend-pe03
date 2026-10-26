"""CT-01 a CT-04: autenticação e acesso às obras."""

from datetime import timedelta
import pytest
from flask_jwt_extended import create_access_token, decode_token
from support import snapshot
from support_obras import BASE, DETAIL, ID, seed

routes = pytest.mark.routes


@routes(("POST", "/construtora/login/"))
def test_ct01_login_emite_tokens_da_mesma_sessao(app, client, account, database):
    # Preparação
    before = snapshot(database)
    credentials = {"email": account["email"], "senha": "Senha_teste123!"}

    # Execução
    response = client.post("/construtora/login/", json=credentials)

    # Verificação
    assert response.status_code == 200
    with app.app_context():
        access = decode_token(response.get_json()["access_token"])
        refresh = decode_token(response.get_json()["refresh_token"])
    assert access["sub"] == refresh["sub"] == str(account["_id"])
    assert access["tipo"] == refresh["tipo"] == "construtora"
    assert access["sessao_id"] == refresh["sessao_id"]
    assert isinstance(access["sessao_id"], str) and access["sessao_id"]
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"
    assert snapshot(database) == before


@routes(("POST", "/construtora/logout/"), ("POST", "/construtora/refresh/"), ("PATCH", DETAIL))
def test_ct04_logout_bloqueia_edicao_e_renovacao(client, account, database, obra):
    # Preparação
    seed(database, obra)
    login = client.post(
        "/construtora/login/",
        json={"email": account["email"], "senha": "Senha_teste123!"},
    )
    assert login.status_code == 200
    tokens = login.get_json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    refresh_headers = {"Authorization": "Bearer " + tokens["refresh_token"]}
    initial = client.patch(DETAIL, json={"nome": "Nome corrigido"}, headers=headers)
    assert initial.status_code == 200

    # Execução
    logout = client.post("/construtora/logout/", headers=headers)
    before = snapshot(database)
    edited = client.patch(DETAIL, json={"nome": "Nome proibido"}, headers=headers)
    refreshed = client.post("/construtora/refresh/", headers=refresh_headers)

    # Verificação
    assert logout.status_code == 200
    assert edited.status_code == refreshed.status_code == 401
    assert database.tbl_sessoes_revogadas.count_documents({}) == 1
    assert snapshot(database) == before


@routes(("POST", "/construtora/login/"), ("GET", BASE))
def test_ct01_login_valido_abre_obras(app, client, account, database):
    # Preparação
    before = snapshot(database)
    credentials = {"email": account["email"], "senha": "Senha_teste123!"}

    # Execução
    login_response = client.post("/construtora/login/", json=credentials)
    token = (login_response.get_json() or {}).get("access_token", "")
    list_response = client.get(BASE, headers={"Authorization": "Bearer " + token})

    # Verificação
    assert login_response.status_code == 200
    assert token
    with app.app_context():
        assert decode_token(token)["sub"] == str(account["_id"])
    assert list_response.status_code == 200
    assert list_response.get_json()["obras"] == []
    assert snapshot(database) == before


@routes(("POST", "/construtora/login/"))
@pytest.mark.parametrize(
    "email,senha",
    [("construtora@example.com", "Errada!"), ("inexistente@example.com", "Senha_teste123!")],
    ids=["senha-errada", "usuario-inexistente"],
)
def test_ct02_login_invalido(client, account, database, email, senha):
    # Preparação
    before = snapshot(database)

    # Execução
    response = client.post("/construtora/login/", json={"email": email, "senha": senha})

    # Verificação
    assert response.status_code == 401
    assert response.get_json() == {"erro": "Email ou senha incorretos"}
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
def test_ct03_acesso_negado(app, client, account, database, obra, method, path, expired):
    # Preparação
    seed(database, obra)
    before = snapshot(database)
    headers = {}
    if expired:
        with app.app_context():
            token = create_access_token(
                identity=str(account["_id"]),
                additional_claims={"tipo": "construtora", "sessao_id": "sessao-teste-expirada"},
                expires_delta=timedelta(seconds=-60)
            )
        headers = {"Authorization": "Bearer " + token}

    # Execução
    response = client.open(path, method=method, json=obra, headers=headers)

    # Verificação
    assert response.status_code == 401
    assert obra["nome"] not in response.get_data(as_text=True)
    assert "obras" not in response.get_json()
    assert snapshot(database) == before


@routes(("POST", "/construtora/login/"), ("POST", "/construtora/logout/"), ("GET", BASE), ("POST", BASE))
def test_ct04_logout_revoga_token(client, account, database, obra):
    # Preparação
    credentials = {"email": account["email"], "senha": "Senha_teste123!"}

    # Execução
    login_response = client.post("/construtora/login/", json=credentials)
    token = (login_response.get_json() or {}).get("access_token", "")
    headers = {"Authorization": "Bearer " + token}
    initial_response = client.get(BASE, headers=headers)
    logout_response = client.post("/construtora/logout/", headers=headers)
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

