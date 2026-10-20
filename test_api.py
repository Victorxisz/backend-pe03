import pytest
from copy import deepcopy
from runpy import run_module
from unittest.mock import patch, ANY
from bson import ObjectId
from flask_bcrypt import Bcrypt
from datetime import timedelta
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from pymongo.errors import PyMongoError

# O db.py exige uma URI mesmo com o MongoClient simulado.
# Não carrega o .env nem conecta ao MongoDB real.
with patch.dict("os.environ", {
    "MONGO_URI": "mongodb://localhost/banco_testes"
}), patch("pymongo.MongoClient"), patch("dotenv.load_dotenv"):
    from api import app


@pytest.fixture
def client(monkeypatch):
    """Cria um cliente de teste para a API."""
    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(
        app.config, "JWT_SECRET_KEY",
        "chave-ficticia-de-testes-jwt-com-mais-de-32-bytes"
    )
    with app.test_client() as client:
        yield client

@patch("db.banco_dados")
def test_login_valido(mock_banco, client):
    bcrypt = Bcrypt()
    mock_usuarios = mock_banco.__getitem__.return_value

    mock_usuarios.find_one.return_value = {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "username": "construtora_teste",
        "password": bcrypt.generate_password_hash("Senha_teste123!").decode("utf-8")
    }

    dados_login = {
        "username": "construtora_teste",
        "password": "Senha_teste123!"
    }

    response = client.post("/login", json = dados_login)
    assert response.status_code == 200

    dados_resposta = response.get_json()

    assert "access_token" in dados_resposta
    assert isinstance(dados_resposta["access_token"], str)
    assert dados_resposta["access_token"]

    mock_usuarios.find_one.assert_called_once_with({
        "username": "construtora_teste"
    })

@pytest.mark.parametrize("usuario_existe", [True, False])
@patch("db.banco_dados")
def test_login_invalido(mock_banco, client, usuario_existe):
    mock_usuarios = mock_banco.__getitem__.return_value

    if usuario_existe:
        bcrypt = Bcrypt()

        mock_usuarios.find_one.return_value = {
            "username": "construtora_teste",
            "password": bcrypt.generate_password_hash("SenhaCorreta123!").decode("utf-8")
        }

    else:
        mock_usuarios.find_one.return_value = None

    response = client.post("/login", json={"username": "construtora_teste",
                                            "password": "SenhaErrada123!"})
    assert response.status_code == 401
    assert response.get_json() == {
        "msg": "Usuário ou senha inválidos"
    }
    assert "access_token" not in response.get_json()

@pytest.mark.parametrize("metodo,rota", [
    ("GET", "/api/v1/obras"),
    ("POST", "/api/v1/obras"),
    ("PATCH", "/api/v1/obras/507f1f77bcf86cd799439011"),
    ("DELETE", "/api/v1/obras/507f1f77bcf86cd799439011")
])
def test_acesso_sem_token(client, metodo, rota):
    response = client.open(
        rota,
        method = metodo,
        json={}
    )

    assert response.status_code == 401

def test_acesso_token_expirado(client):

    emissor = Flask("emissor_de_tokens_de_teste")
    emissor.config["JWT_SECRET_KEY"] = app.config["JWT_SECRET_KEY"]
    JWTManager(emissor)

    with emissor.app_context():
        token = create_access_token(
            identity="construtora_teste",
            expires_delta=timedelta(seconds=-60)
        )
    response = client.get(
        "/api/v1/obras",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401

@patch("db.banco_dados")
def test_logout_invalida_token(mock_banco, client):
    bcrypt = Bcrypt()
    mock_usuarios =  mock_banco.__getitem__.return_value
    mock_usuarios.find_one.return_value = {
        "username": "construtora_teste",
        "password": bcrypt.generate_password_hash(
            "SenhaCorreta123!"
        ).decode("utf-8")
    }

    response_login = client.post("/login", json={"username": "construtora_teste",
                                                "password": "SenhaCorreta123!"})

    assert response_login.status_code == 200

    token = response_login.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    mock_banco.__getitem__.return_value.find.return_value = []
    response_antes = client.get("/api/v1/obras", headers=headers)
    assert response_antes.status_code == 200

    response_logout = client.post(
        "/logout",
        headers=headers
    )
    assert response_logout.status_code == 200

    response_depois = client.get(
        "/api/v1/obras",
        headers=headers
    )
    assert response_depois.status_code == 401

# A rota /usuarios ainda precisa ser implementada.
# Sem patch de um módulo inexistente: o teste deve falhar com 404.
def test_cria_usuario_construtora(client):
    novo_usuario = {
        "nome": "Construtora Teste",
        "cnpj": "00.000.000/0000-00",
        "email": "construtora@example.com",
        "telefone": "16991736767"
    }

    response = client.post("/usuarios", json=novo_usuario)

    assert response.status_code == 201


@patch("trabalhadores.colecao_trabalhadores")
def test_cria_usuario_trabalhador(mock_colecao, client):
    mock_colecao.insert_one.return_value.inserted_id = "2"

    novo_usuario = {
        "nome": "João",
        "email": "joao@email.com",
        "telefone": "16991736767",
        "cargo": "pedreiro"
    }

    response = client.post("/trabalhadores/obra/123/", json=novo_usuario)

    assert response.status_code == 201
    assert response.get_json() == {
        "mensagem": "Trabalhador criado com sucesso",
        "id": "2"
    }

    mock_colecao.insert_one.assert_called_once_with({
        "nome": "João",
        "email": "joao@email.com",
        "telefone": "16991736767",
        "cargo": "pedreiro",
        "obras": [123],
        "ativo": True,
        "data_cadastro": ANY
    })


@pytest.mark.parametrize("campos_faltantes", ["nome", "email", "telefone", "cargo"])
@patch("trabalhadores.colecao_trabalhadores")
def test_criar_trabalhador_campos_faltantes(mock_colecao, client, campos_faltantes):

    novo_usuario = {
        "nome": "João",
        "email": "joao@email.com",
        "telefone": "16991736767",
        "cargo": "pedreiro"
    }

    del novo_usuario[campos_faltantes]

    response = client.post("/trabalhadores/obra/123/",json=novo_usuario)
    assert response.status_code == 422

    mock_colecao.insert_one.assert_not_called()

@patch("obras.colecao_obras")
def test_cria_obra_casa_data_exata(mock_colecao, client):
    mock_colecao.insert_one.return_value.inserted_id = "1"

    nova_obra = {
        "nome": "Casa Teste",
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-12-20"
        }
    }

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 201
    mock_colecao.insert_one.assert_called_once()


# CT-06: criar apartamentos com intervalo válido.
@patch("obras.colecao_obras")
def test_cria_obra_apartamentos_intervalo(mock_colecao, client):
    mock_colecao.insert_one.return_value.inserted_id = "2"

    nova_obra = {
        "nome": "Apartamentos Teste",
        "tipo": "apartamentos",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {
            "modalidade": "intervalo_estimado",
            "inicio": "2030-10-01",
            "fim": "2030-12-20"
        }
    }

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 201
    mock_colecao.insert_one.assert_called_once()


# CT-07: rejeitar duas modalidades juntas ou modalidade ausente.
@pytest.mark.parametrize("dados_entrega", [
    {
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-12-20",
            "inicio": "2030-10-01",
            "fim": "2030-12-20"
        }
    },
    {}
])
@patch("obras.colecao_obras")
def test_cria_obra_modalidade_invalida(mock_colecao, client, dados_entrega):
    nova_obra = {
        "nome": "Obra Teste",
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15"
    }

    nova_obra.update(dados_entrega)

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 422
    mock_colecao.insert_one.assert_not_called()


# CT-08: rejeitar datas inválidas e intervalo invertido.
@pytest.mark.parametrize("dados_entrega", [
    {
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-02-30"
        }
    },
    {
        "entrega": {
            "modalidade": "data_exata",
            "data": "data inválida"
        }
    },
    {
        "entrega": {
            "modalidade": "intervalo_estimado",
            "inicio": "2030-02-30",
            "fim": "2030-12-20"
        }
    },
    {
        "entrega": {
            "modalidade": "intervalo_estimado",
            "inicio": "2030-10-01",
            "fim": "2030-13-20"
        }
    },
    {
        "entrega": {
            "modalidade": "intervalo_estimado",
            "inicio": "2030-12-20",
            "fim": "2030-10-01"
        }
    }
])
@patch("obras.colecao_obras")
def test_cria_obra_datas_invalidas(mock_colecao, client, dados_entrega):
    nova_obra = {
        "nome": "Obra Teste",
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15"
    }

    nova_obra.update(dados_entrega)

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 422
    mock_colecao.insert_one.assert_not_called()


# CT-08: rejeitar nome vazio.
@pytest.mark.parametrize("nome", ["", "   "])
@patch("obras.colecao_obras")
def test_cria_obra_nome_vazio(mock_colecao, client, nome):
    nova_obra = {
        "nome": nome,
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-12-20"
        }
    }

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 422
    mock_colecao.insert_one.assert_not_called()


# CT-09: recuperar os dados após recarregar e simular o reinício do Flask.
# O banco é simulado; a persistência real no Atlas exige teste de integração.
@patch("obras.colecao_obras")
def test_obra_persiste_apos_recarregar_reiniciar(mock_colecao, client):
    obra_id = ObjectId("507f1f77bcf86cd799439011")
    documentos = {}
    mock_colecao.insert_one.return_value.inserted_id = obra_id

    def salvar_obra(documento):
        documentos[obra_id] = deepcopy(documento)
        documentos[obra_id]["_id"] = obra_id
        return mock_colecao.insert_one.return_value

    def consultar_obra(filtro):
        return deepcopy(documentos.get(filtro.get("_id")))

    mock_colecao.insert_one.side_effect = salvar_obra
    mock_colecao.find_one.side_effect = consultar_obra

    nova_obra = {
        "nome": "Casa Teste",
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-12-20"
        }
    }

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 201
    assert response.get_json()["id"] == str(obra_id)
    mock_colecao.insert_one.assert_called_once()

    # Um novo cliente consulta a obra sem reutilizar a sessão anterior.
    with app.test_client() as novo_client:
        response_recarregar = novo_client.get(f"/api/v1/obras/{obra_id}")

    assert response_recarregar.status_code == 200
    dados_recarregados = response_recarregar.get_json()
    assert dados_recarregados["id"] == str(obra_id)
    for campo, valor in nova_obra.items():
        assert dados_recarregados[campo] == valor
    mock_colecao.find_one.assert_called_once_with({"_id": obra_id})
    mock_colecao.find_one.reset_mock()

    # Executa a inicialização em outro namespace, criando uma nova aplicação.
    # A coleção simulada mantém somente os documentos salvos pelo POST.
    app_reiniciada = run_module("api", run_name="api_ct09")["app"]
    app_reiniciada.config["TESTING"] = True
    assert app_reiniciada is not app

    with app_reiniciada.test_client() as novo_client:
        response_reiniciar = novo_client.get(f"/api/v1/obras/{obra_id}")

    assert response_reiniciar.status_code == 200
    assert response_reiniciar.get_json() == dados_recarregados
    mock_colecao.find_one.assert_called_once_with({"_id": obra_id})
    mock_colecao.insert_one.assert_called_once()


# CT-10: tratar falha do banco sem retornar sucesso.
@patch("obras.colecao_obras")
def test_cria_obra_falha_banco(mock_colecao, client):
    mock_colecao.insert_one.side_effect = PyMongoError(
        "Falha ao salvar obra"
    )

    nova_obra = {
        "nome": "Casa Teste",
        "tipo": "casa",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {
            "modalidade": "data_exata",
            "data": "2030-12-20"
        }
    }

    response = client.post("/api/v1/obras", json=nova_obra)

    assert response.status_code == 500
    mock_colecao.insert_one.assert_called_once()
