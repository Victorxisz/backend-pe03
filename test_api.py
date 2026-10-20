import re
from freezegun import freeze_time
import pytest
from copy import deepcopy
from runpy import run_module
from unittest.mock import patch, ANY
from bson import ObjectId
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta, timezone
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

# ============================================================
# UC-03 - Listar, filtrar e consultar obras (CT-11 a CT-15)
# ============================================================

@pytest.fixture
def client_com_data_fixa(client):
    # Reutiliza o cliente compartilhado e controla o relógio apenas no UC-03.
    with freeze_time("2026-10-20 12:00:00"):
        yield client


@pytest.fixture
def headers_autenticacao(client_com_data_fixa):
    # Não inicializa JWT na API: essa configuração pertence à implementação.
    emissor = Flask("emissor_de_tokens_de_teste")
    emissor.config["JWT_SECRET_KEY"] = app.config["JWT_SECRET_KEY"]
    JWTManager(emissor)
    with emissor.app_context():
        token = create_access_token(identity="construtora_teste")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def obras_exemplo():
    return [
        {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "nome": "Residencial Aurora",
            "cliente": "Cliente Aurora",
            "estado": "em andamento",
            "localizacao": "Campinas, SP",
            "descricao": "Construção de apartamentos",
            "tipo": "apartamentos",
            "inicio": "2026-10-01",
            "data_registro": datetime(2026, 10, 10, 15, tzinfo=timezone.utc),
            "entrega": {"modalidade": "data_exata", "data": "2026-12-01"}
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "nome": "Casa Ipê",
            "cliente": "Cliente Ipê",
            "estado": "planejada",
            "localizacao": "São Paulo, SP",
            "descricao": "Construção de casa",
            "tipo": "casa",
            "inicio": "2026-11-01",
            "data_registro": datetime(2026, 10, 15, 9, tzinfo=timezone.utc),
            "entrega": {
                "modalidade": "intervalo_estimado",
                "inicio": "2026-12-01", "fim": "2026-12-31"
            }
        }
    ]


@pytest.fixture
def colecao_obras():
    # Alvo existente: a futura rota deve obter a coleção de db.banco_dados.
    # O mock fica restrito à coleção de obras.
    with patch("db.banco_dados") as mock_banco:
        colecao = mock_banco.__getitem__.return_value
        colecao.find.return_value = []
        colecao.find_one.return_value = None
        yield colecao
        # Toda consulta deste UC deve ser somente leitura.
        colecao.insert_one.assert_not_called()
        colecao.update_one.assert_not_called()
        colecao.update_many.assert_not_called()
        colecao.replace_one.assert_not_called()
        colecao.delete_one.assert_not_called()
        colecao.delete_many.assert_not_called()


# CT-11: lista duas obras e preserva os dados de cada uma.
def test_listar_obras(client_com_data_fixa, headers_autenticacao, obras_exemplo, colecao_obras):
    colecao_obras.find.return_value = deepcopy(obras_exemplo)

    response = client_com_data_fixa.get("/api/v1/obras", headers=headers_autenticacao)

    assert response.status_code == 200
    obras = response.get_json()["obras"]
    assert len(obras) == 2
    por_id = {obra["id"]: obra for obra in obras}
    for esperada in obras_exemplo:
        dados = por_id[str(esperada["_id"])]
        for campo in ("nome", "cliente", "estado", "tipo", "entrega"):
            assert dados[campo] == esperada[campo]
    colecao_obras.find.assert_called_once_with({})


@pytest.mark.parametrize("indice", [0, 1])
def test_consultar_obra_correta(
    client_com_data_fixa, headers_autenticacao, obras_exemplo, colecao_obras, indice
):
    esperada = obras_exemplo[indice]
    colecao_obras.find_one.return_value = deepcopy(esperada)

    response = client_com_data_fixa.get(
        f"/api/v1/obras/{esperada['_id']}", headers=headers_autenticacao
    )

    assert response.status_code == 200
    dados = response.get_json()
    assert dados["id"] == str(esperada["_id"])
    for campo in ("nome", "cliente", "estado", "tipo", "entrega"):
        assert dados[campo] == esperada[campo]
    colecao_obras.find_one.assert_called_once_with({"_id": esperada["_id"]})


# CT-12: verifica também o filtro entregue ao banco, não apenas a resposta.
@pytest.mark.parametrize("parametros,filtro", [
    ({"nome": "Aurora"}, {"nome": {"$regex": "Aurora", "$options": "i"}}),
    ({"nome": "Casa (A)"}, {
        "nome": {"$regex": re.escape("Casa (A)"), "$options": "i"}
    }),
    ({"cliente": "Cliente Aurora"}, {
        "cliente": {"$regex": "Cliente Aurora", "$options": "i"}
    }),
    ({"estado": "em andamento"}, {"estado": "em andamento"}),
    ({"registroDe": "2026-10-01", "registroAte": "2026-10-31"}, {
        "data_registro": {
            "$gte": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "$lt": datetime(2026, 11, 1, tzinfo=timezone.utc)
        }
    }),
    ({"entregaDe": "2026-12-01", "entregaAte": "2026-12-31"}, {
        "$or": [
            {"entrega.modalidade": "data_exata", "entrega.data": {
                "$gte": "2026-12-01", "$lte": "2026-12-31"
            }},
            {"entrega.modalidade": "intervalo_estimado", "entrega.fim": {
                "$gte": "2026-12-01", "$lte": "2026-12-31"
            }}
        ]
    })
])
def test_filtros_individuais(
    client_com_data_fixa, headers_autenticacao, colecao_obras, parametros, filtro
):
    response = client_com_data_fixa.get(
        "/api/v1/obras", query_string=parametros, headers=headers_autenticacao
    )

    assert response.status_code == 200
    assert response.get_json()["obras"] == []
    colecao_obras.find.assert_called_once_with(filtro)


# CT-13: combina os critérios com interseção; ausência de resultado não é erro.
@pytest.mark.parametrize("tem_resultado", [True, False])
def test_combinar_filtros(
    client_com_data_fixa, headers_autenticacao, obras_exemplo, colecao_obras, tem_resultado
):
    colecao_obras.find.return_value = [deepcopy(obras_exemplo[0])] if tem_resultado else []

    response = client_com_data_fixa.get(
        "/api/v1/obras",
        query_string={"nome": "Aurora", "cliente": "Cliente Aurora"},
        headers=headers_autenticacao
    )

    assert response.status_code == 200
    dados = response.get_json()["obras"]
    if tem_resultado:
        assert len(dados) == 1
        assert dados[0]["id"] == str(obras_exemplo[0]["_id"])
    else:
        assert dados == []
    colecao_obras.find.assert_called_once_with({
        "nome": {"$regex": "Aurora", "$options": "i"},
        "cliente": {"$regex": "Cliente Aurora", "$options": "i"}
    })


# CT-14: data final só vence depois do dia indicado; a consulta deriva o alerta.
@pytest.mark.parametrize("modalidade,fim,atrasada", [
    ("data_exata", "2026-10-21", False),
    ("data_exata", "2026-10-20", False),
    ("data_exata", "2026-10-19", True),
    ("intervalo_estimado", "2026-10-25", False),
    ("intervalo_estimado", "2026-10-20", False),
    ("intervalo_estimado", "2026-10-19", True)
])
def test_calcular_atraso(
    client_com_data_fixa, headers_autenticacao, obras_exemplo, colecao_obras,
    modalidade, fim, atrasada
):
    obra = deepcopy(obras_exemplo[0])
    if modalidade == "data_exata":
        obra["entrega"] = {"modalidade": modalidade, "data": fim}
    else:
        obra["entrega"] = {
            "modalidade": modalidade,
            "inicio": "2026-10-22" if fim == "2026-10-25" else "2026-10-10",
            "fim": fim
        }
    # Não coloca 'atrasada' no mock: a aplicação precisa calculá-la.
    colecao_obras.find_one.return_value = obra

    response = client_com_data_fixa.get(
        f"/api/v1/obras/{obra['_id']}", headers=headers_autenticacao
    )

    assert response.status_code == 200
    dados = response.get_json()
    assert ("atrasada" in dados["alertas"]) is atrasada
    assert dados["estado"] == "em andamento"


def test_impedir_edicao_manual_do_atraso(
    client_com_data_fixa, headers_autenticacao, obras_exemplo, colecao_obras
):
    obra = obras_exemplo[0]
    colecao_obras.find_one.return_value = deepcopy(obra)

    response = client_com_data_fixa.patch(
        f"/api/v1/obras/{obra['_id']}",
        json={"alertas": ["atrasada"]}, headers=headers_autenticacao
    )

    assert response.status_code == 422


# CT-15: não inventa dados para ID desconhecido e valida antes de consultar.
def test_obra_inexistente(client_com_data_fixa, headers_autenticacao, colecao_obras):
    obra_id = ObjectId("507f1f77bcf86cd799439099")

    response = client_com_data_fixa.get(f"/api/v1/obras/{obra_id}", headers=headers_autenticacao)

    assert response.status_code == 404
    colecao_obras.find_one.assert_called_once_with({"_id": obra_id})


@pytest.mark.parametrize("parametros", [
    {"registroDe": "data-invalida"},
    {"registroAte": "2026-02-30"},
    {"entregaDe": "20/10/2026"},
    {"entregaAte": "2026-13-01"},
    {"registroDe": "2026-10-31", "registroAte": "2026-10-01"},
    {"entregaDe": "2026-12-31", "entregaAte": "2026-12-01"}
])
def test_rejeitar_filtros_invalidos(
    client_com_data_fixa, headers_autenticacao, colecao_obras, parametros
):
    response = client_com_data_fixa.get(
        "/api/v1/obras", query_string=parametros, headers=headers_autenticacao
    )

    assert response.status_code == 422
    colecao_obras.find.assert_not_called()
