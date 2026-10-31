"""CT-01, CT-02 e CT-04 no contrato público de sessões."""
import pytest
from bson import ObjectId
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, decode_token

from support import snapshot


@pytest.fixture(autouse=True)
def configurar_conta(app, account):
    app.config["CONSTRUTORA_ID"] = str(account["_id"])


def test_ct01_e_ct04_ciclo_da_sessao(app, client, account, database):
    # Preparação
    credenciais = {"email": account["email"], "senha": "Senha_teste123!"}

    # Execução
    login = client.post("/sessoes", json=credenciais)
    assert login.status_code == 200
    tokens = login.get_json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    atual = client.get("/sessoes/atual", headers=headers)
    saida = client.delete("/sessoes/atual", headers=headers)
    depois = client.get("/sessoes/atual", headers=headers)
    refresh = client.post("/construtora/refresh/", headers={"Authorization": "Bearer " + tokens["refresh_token"]})

    # Verificação
    assert atual.status_code == 200
    assert atual.get_json()["construtora"]["id"] == str(account["_id"])
    assert "senha_hash" not in atual.get_json()["construtora"]
    assert saida.status_code == 200
    assert depois.status_code == refresh.status_code == 401
    with app.app_context():
        sessao_id = decode_token(tokens["access_token"])["sessao_id"]
    revogada = database.tbl_sessoes_revogadas.find_one({"_id": sessao_id})
    assert revogada["construtora_id"] == str(account["_id"])


@pytest.mark.parametrize("email,senha", [("construtora@example.com", "errada"), ("ausente@example.com", "Senha_teste123!")])
def test_ct02_credenciais_invalidas(client, account, database, email, senha):
    # Preparação
    antes = snapshot(database)

    # Execução
    resposta = client.post("/sessoes", json={"email": email, "senha": senha})

    # Verificação
    assert resposta.status_code == 401
    assert resposta.get_json() == {"erro": "Email ou senha incorretos"}
    assert "access_token" not in resposta.get_json()
    assert snapshot(database) == antes


def test_ct02_segunda_conta_nao_pode_entrar_ou_acessar(app, client, account, database):
    # Preparação
    outra = {"_id": ObjectId(), "nome": "Outra", "email": "outra@example.com", "ativo": True,
             "senha_hash": Bcrypt().generate_password_hash("Senha_outra123!").decode()}
    database.tbl_construtora.insert_one(outra)
    with app.app_context():
        token = create_access_token(identity=str(outra["_id"]), additional_claims={"tipo": "construtora", "sessao_id": "outra-sessao"})
    antes = snapshot(database)

    # Execução
    login = client.post("/sessoes", json={"email": outra["email"], "senha": "Senha_outra123!"})
    antigo = client.post("/construtora/login/", json={"email": outra["email"], "senha": "Senha_outra123!"})
    acesso = client.get("/sessoes/atual", headers={"Authorization": "Bearer " + token})

    # Verificação
    assert login.status_code == antigo.status_code == acesso.status_code == 401
    assert snapshot(database) == antes


def test_ct02_cadastro_publico_nao_cria_conta(client, database):
    # Preparação
    antes = snapshot(database)

    # Execução
    resposta = client.post("/construtora/", json={"nome": "Outra", "email": "outra@example.com", "senha": "Senha_outra123!"})

    # Verificação
    assert resposta.status_code == 403
    assert "access_token" not in resposta.get_json()
    assert snapshot(database) == antes


def test_ct02_configuracao_ausente_nao_autentica(app, client, account, database):
    # Preparação
    app.config["CONSTRUTORA_ID"] = ""
    antes = snapshot(database)

    # Execução
    resposta = client.post("/sessoes", json={"email": account["email"], "senha": "Senha_teste123!"})

    # Verificação
    assert resposta.status_code == 503
    assert "access_token" not in resposta.get_json()
    assert snapshot(database) == antes


@pytest.mark.parametrize("situacao,status", [("ausente", 401), ("expirado", 401), ("outro_tipo", 403)])
def test_ct01_consultar_sessao_requer_acesso_valido(client, database, account, emitir_headers, situacao, status):
    # Preparação
    antes = snapshot(database)
    headers = {}
    if situacao == "expirado":
        headers = emitir_headers(expirado=True)
    elif situacao == "outro_tipo":
        headers = emitir_headers(claims={"tipo": "outro"})

    # Execução
    resposta = client.get("/sessoes/atual", headers=headers)

    # Verificação
    assert resposta.status_code == status
    assert "construtora" not in resposta.get_json()
    assert snapshot(database) == antes
