import pytest
from unittest.mock import patch, ANY
from bson import ObjectId


# O db.py exige uma URI mesmo com o MongoClient simulado.
# Não carrega o .env nem conecta ao MongoDB real.
with patch.dict("os.environ", {
    "MONGO_URI": "mongodb://localhost/banco_testes"
}), patch("pymongo.MongoClient"), patch("dotenv.load_dotenv"):
    from api import app


@pytest.fixture
def client():
    """Cria um cliente de teste para a API."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("usuarios.colecao_usuarios")
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