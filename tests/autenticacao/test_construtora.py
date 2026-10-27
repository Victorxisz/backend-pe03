"""Cenários ausentes da suíte CT-01..04; não repete login/logout básicos."""

from datetime import datetime

import pytest
from bson import ObjectId
from flask_bcrypt import Bcrypt
from flask_jwt_extended import decode_token
from pymongo.errors import PyMongoError

from support import snapshot


@pytest.fixture
def modulo(app):
    import construtora

    return construtora


@pytest.fixture
def cadastro():
    return {
        "nome": "  Construtora Nova  ",
        "email": "  NOVA@example.com  ",
        "telefone": "(11) 99999-9999",
        "senha": "Senha_segura123!",
    }


@pytest.mark.parametrize("telefone", [None, "(11) 3333-4444", "(11) 99999-9999"])
def test_cadastro_normaliza_protege_senha_e_autentica(
    app, client, database, cadastro, telefone
):
    if telefone is None:
        cadastro.pop("telefone")
    else:
        cadastro["telefone"] = telefone

    response = client.post("/construtora/", json=cadastro)

    assert response.status_code == 201
    body = response.get_json()
    documento = database.tbl_construtora.find_one({
        "_id": ObjectId(body["construtora"]["id"])
    })
    assert database.tbl_construtora.count_documents({}) == 1
    esperado = None if telefone is None else "".join(c for c in telefone if c.isdigit())
    assert documento["nome"] == "Construtora Nova"
    assert documento["email"] == "nova@example.com"
    assert documento.get("telefone") == esperado
    assert documento["ativo"] is True
    assert documento["data_cadastro"] == datetime(2030, 10, 20, 12)
    assert "senha" not in documento
    assert Bcrypt().check_password_hash(documento["senha_hash"], cadastro["senha"])
    assert body["construtora"] == {
        "id": str(documento["_id"]), "nome": documento["nome"],
        "email": documento["email"], "telefone": esperado,
    }
    with app.app_context():
        access = decode_token(body["access_token"])
        refresh = decode_token(body["refresh_token"])
    assert access["sub"] == refresh["sub"] == str(documento["_id"])
    assert access["tipo"] == refresh["tipo"] == "construtora"
    assert access["sessao_id"] == refresh["sessao_id"]
    assert isinstance(access["sessao_id"], str) and access["sessao_id"]
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"


@pytest.mark.parametrize("campo", ["nome", "email", "senha"])
def test_cadastro_exige_campos_obrigatorios(client, database, cadastro, campo):
    cadastro.pop(campo)
    before = snapshot(database)

    response = client.post("/construtora/", json=cadastro)

    assert response.status_code == 422
    assert "erro" in response.get_json()
    assert snapshot(database) == before


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("payload", [
    {}, [], "texto", {"nome": " "}, {"email": "invalido"},
    {"telefone": "123"}, {"telefone": "+55 11 99999-9999"},
    {"senha": "curta"}, {"senha": "a" * 73}, {"senha": "á" * 37},
    {"ativo": False}, {"nome": None}, {"email": 123},
])
def test_dados_invalidos_nao_gravam(
    client, headers, database, account, cadastro, method, payload
):
    dados = payload
    if method == "POST" and isinstance(payload, dict) and payload:
        dados = {**cadastro, **payload}
    path = "/construtora/" if method == "POST" else f"/construtora/{account['_id']}"
    before = snapshot(database)

    response = client.open(path, method=method, json=dados, headers=headers)

    assert response.status_code == 422
    assert "erro" in response.get_json()
    assert snapshot(database) == before


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("corpo", [None, '{"nome":', "null"])
def test_corpo_ausente_ou_json_malformado(
    client, headers, database, account, method, corpo
):
    path = "/construtora/" if method == "POST" else f"/construtora/{account['_id']}"
    before = snapshot(database)

    response = client.open(
        path, method=method, data=corpo, content_type="application/json", headers=headers
    )

    assert response.status_code == 422
    assert snapshot(database) == before


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_email_duplicado_retorna_409(
    client, headers, database, account, cadastro, method
):
    database.tbl_construtora.insert_one({"email": "ocupado@example.com"})
    path = "/construtora/" if method == "POST" else f"/construtora/{account['_id']}"
    dados = {**cadastro, "email": " OCUPADO@example.com "}
    before = snapshot(database)

    response = client.open(path, method=method, json=dados, headers=headers)

    assert response.status_code == 409
    assert snapshot(database) == before


def test_atualizacao_parcial_normaliza_e_preserva_outros_campos(
    client, headers, database, account
):
    before = database.tbl_construtora.find_one({"_id": account["_id"]})

    response = client.patch(
        f"/construtora/{account['_id']}", headers=headers,
        json={"nome": " Nova Razão ", "email": " NOVO@example.com ",
              "telefone": "(11) 98888-7777"},
    )

    assert response.status_code == 200
    assert database.tbl_construtora.find_one({"_id": account["_id"]}) == {
        **before, "nome": "Nova Razão", "email": "novo@example.com", "telefone": "11988887777"
    }


def test_atualizacao_senha_substitui_hash_e_preserva_dados(
    client, headers, database, account
):
    before = database.tbl_construtora.find_one({"_id": account["_id"]})
    senha = "Outra_senha123!"

    response = client.patch(
        f"/construtora/{account['_id']}", json={"senha": senha}, headers=headers
    )

    assert response.status_code == 200
    after = database.tbl_construtora.find_one({"_id": account["_id"]})
    assert after == {**before, "senha_hash": after["senha_hash"]}
    assert after["senha_hash"] != before["senha_hash"]
    assert Bcrypt().check_password_hash(after["senha_hash"], senha)
    assert not Bcrypt().check_password_hash(after["senha_hash"], "Senha_teste123!")


def test_atualizacao_sem_mudanca_retorna_sucesso(client, headers, database, account):
    before = snapshot(database)
    response = client.patch(
        f"/construtora/{account['_id']}", json={"nome": account["nome"]}, headers=headers
    )
    assert response.status_code == 200
    assert snapshot(database) == before


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("estado,status", [
    ("id-invalido", 400), ("outra-conta", 403), ("conta-removida", 404),
])
def test_alteracoes_rejeitam_id_ou_conta_inacessivel(
    client, headers, database, account, method, estado, status
):
    identificador = str(account["_id"])
    if estado == "id-invalido":
        identificador = "invalido"
    elif estado == "outra-conta":
        identificador = str(database.tbl_construtora.insert_one({
            "email": "outra@example.com", "nome": "Outra construtora"
        }).inserted_id)
    else:
        database.tbl_construtora.delete_one({"_id": account["_id"]})
    before = snapshot(database)

    response = client.open(
        f"/construtora/{identificador}", method=method,
        json={"nome": "Alteração"}, headers=headers,
    )

    assert response.status_code == status
    assert snapshot(database) == before


def test_exclusao_preserva_outra_conta(client, headers, database, account):
    outro = {"_id": ObjectId(), "email": "outra@example.com"}
    database.tbl_construtora.insert_one(outro)

    response = client.delete(f"/construtora/{account['_id']}", headers=headers)

    assert response.status_code == 200
    assert list(database.tbl_construtora.find()) == [outro]


@pytest.mark.parametrize("payload,status", [
    ([], 422), ({}, 422), ({"email": " "}, 422), ({"email": 1}, 422),
    ({"email": "a@example.com"}, 422),
    ({"email": "a@example.com", "senha": " "}, 422),
    ({"email": "a@example.com", "senha": 123}, 422),
    ({"email": "a@example.com", "senha": "á" * 37}, 401),
])
def test_login_rejeita_corpo_e_credenciais_malformadas(client, database, payload, status):
    before = snapshot(database)
    response = client.post("/construtora/login/", json=payload)
    assert response.status_code == status
    assert "access_token" not in response.get_json()
    assert snapshot(database) == before


def test_login_normaliza_email_oculta_hash_e_cria_sessoes_distintas(
    app, client, database, account
):
    before = snapshot(database)
    dados = {"email": " CONSTRUTORA@EXAMPLE.COM ", "senha": "Senha_teste123!"}
    respostas = [client.post("/construtora/login/", json=dados) for _ in range(2)]
    assert all(r.status_code == 200 for r in respostas)
    assert all(r.get_json()["construtora"] == {
        "id": str(account["_id"]), "nome": account["nome"],
        "email": account["email"], "telefone": None,
    } for r in respostas)
    with app.app_context():
        sessoes = [decode_token(r.get_json()["access_token"])["sessao_id"] for r in respostas]
    assert sessoes[0] != sessoes[1]
    assert snapshot(database) == before


@pytest.mark.parametrize("ativo", [False, None, 1])
def test_login_rejeita_conta_sem_ativo_true(client, database, account, ativo):
    database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": ativo}})
    response = client.post("/construtora/login/", json={
        "email": account["email"], "senha": "Senha_teste123!"
    })
    assert response.status_code == 403
    assert "access_token" not in response.get_json()


@pytest.mark.parametrize("estado,status", [("ativa", 200), ("inativa", 403), ("removida", 401)])
def test_refresh_considera_estado_da_conta(
    app, client, database, account, emitir_headers, estado, status
):
    auth = emitir_headers("refresh", claims={"sessao_id": "sessao-renovacao"})
    if estado == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    elif estado == "removida":
        database.tbl_construtora.delete_one({"_id": account["_id"]})
    before = snapshot(database)

    response = client.post("/construtora/refresh/", headers=auth)

    assert response.status_code == status
    assert snapshot(database) == before
    if status == 200:
        with app.app_context():
            token = decode_token(response.get_json()["access_token"])
        assert token["sub"] == str(account["_id"])
        assert token["type"] == "access"
        assert token["tipo"] == "construtora"
        assert token["sessao_id"] == "sessao-renovacao"
    else:
        assert "access_token" not in response.get_json()


def test_refresh_rejeita_identidade_invalida(client, database, emitir_headers):
    before = snapshot(database)
    response = client.post(
        "/construtora/refresh/", headers=emitir_headers("refresh", identidade="invalido")
    )
    assert response.status_code == 401
    assert snapshot(database) == before


ROTAS_PROTEGIDAS = [
    ("PATCH", "/construtora/{id}", "access"),
    ("DELETE", "/construtora/{id}", "access"),
    ("POST", "/construtora/refresh/", "refresh"),
    ("POST", "/construtora/logout/", "access"),
]


@pytest.mark.parametrize("method,path,tipo_token,situacao", [
    (method, path, tipo_token, situacao)
    for method, path, tipo_token in ROTAS_PROTEGIDAS
    for situacao in ("ausente", "expirado", "revogado", "tipo-incorreto")
    # Refresh revogado já é coberto por test_ct04_logout_bloqueia_edicao_e_renovacao.
    if not (path == "/construtora/refresh/" and situacao == "revogado")
])
def test_rotas_protegidas_rejeitam_acesso_invalido(
    client, database, account, emitir_headers, method, path, tipo_token, situacao
):
    auth = {}
    if situacao != "ausente":
        claims = {"tipo": "trabalhador"} if situacao == "tipo-incorreto" else {}
        if situacao == "revogado":
            claims["sessao_id"] = "sessao-encerrada"
            database.tbl_sessoes_revogadas.insert_one({"_id": "sessao-encerrada"})
        auth = emitir_headers(tipo_token, claims=claims, expirado=situacao == "expirado")
    before = snapshot(database)

    response = client.open(
        path.format(id=account["_id"]), method=method,
        json={"nome": "Alteração indevida"}, headers=auth,
    )

    assert response.status_code == (403 if situacao == "tipo-incorreto" else 401)
    assert snapshot(database) == before


@pytest.mark.parametrize("path,tipo_token", [
    ("/construtora/refresh/", "refresh"), ("/construtora/logout/", "access"),
])
@pytest.mark.parametrize("sessao", [None, "", 123])
def test_sessao_ausente_ou_malformada_e_rejeitada(
    client, database, emitir_headers, path, tipo_token, sessao
):
    before = snapshot(database)
    response = client.post(path, headers=emitir_headers(tipo_token, claims={"sessao_id": sessao}))
    assert response.status_code == 401
    assert snapshot(database) == before


@pytest.mark.parametrize("method,path,tipo_token", ROTAS_PROTEGIDAS[:3])
def test_refresh_e_access_nao_sao_intercambiaveis(
    client, database, account, emitir_headers, method, path, tipo_token
):
    errado = "refresh" if tipo_token == "access" else "access"
    before = snapshot(database)
    response = client.open(
        path.format(id=account["_id"]), method=method,
        json={"nome": "Alteração"}, headers=emitir_headers(errado),
    )
    assert response.status_code == 422
    assert snapshot(database) == before


def test_logout_com_refresh_encerra_apenas_a_sessao_informada(
    client, database, account, emitir_headers
):
    refresh = emitir_headers("refresh", claims={"sessao_id": "sessao-a"})
    access = emitir_headers(claims={"sessao_id": "sessao-a"})
    outra = emitir_headers(claims={"sessao_id": "sessao-b"})

    response = client.post("/construtora/logout/", headers=refresh)
    assert response.status_code == 200
    revogada = database.tbl_sessoes_revogadas.find_one({"_id": "sessao-a"})
    assert revogada is not None
    assert revogada["encerrada_em"] == datetime(2030, 10, 20, 12)
    path = f"/construtora/{account['_id']}"
    assert client.patch(path, json={"nome": "Proibido"}, headers=access).status_code == 401
    assert client.post("/construtora/logout/", headers=refresh).status_code == 401
    assert client.patch(path, json={"nome": "Permitido"}, headers=outra).status_code == 200
    assert database.tbl_sessoes_revogadas.count_documents({}) == 1


@pytest.mark.parametrize("method,path,collection,operation", [
    ("POST", "/construtora/", "colecao_construtora", "insert_one"),
    ("PATCH", "/construtora/{id}", "colecao_construtora", "update_one"),
    ("DELETE", "/construtora/{id}", "colecao_construtora", "delete_one"),
    ("POST", "/construtora/login/", "colecao_construtora", "find_one"),
    ("POST", "/construtora/refresh/", "colecao_construtora", "find_one"),
    ("POST", "/construtora/logout/", "colecao_sessoes_revogadas", "update_one"),
])
def test_falha_de_banco_retorna_500_sem_expor_detalhes(
    client, database, account, cadastro, modulo, emitir_headers, monkeypatch,
    method, path, collection, operation
):
    auth = emitir_headers("refresh" if path.endswith("/refresh/") else "access")
    dados = {"email": account["email"], "senha": "Senha_teste123!"} if path.endswith("/login/") else cadastro
    before = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    with monkeypatch.context() as context:
        context.setattr(getattr(modulo, collection), operation, falhar)
        response = client.open(
            path.format(id=account["_id"]), method=method, json=dados, headers=auth
        )

    assert response.status_code == 500
    assert "erro" in response.get_json()
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == before
