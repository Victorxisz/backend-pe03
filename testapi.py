import pytest
from unittest.mock import MagicMock, patch, ANY

with patch("pymongo.MongoClient"), patch("dotenv.load_dotenv"):
    from api import app


@pytest.fixture
def client():
    """Cria um cliente de teste para a API."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("api.conectar_db")
def test_cria_usuario_construtora(mock_conectar_db, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conectar_db.return_value = mock_conn
    mock_conn.__getitem__.return_value = mock_cursor

    mock_cursor.insert_one.return_value.inserted_id = "1"

    novo_usuario = {
        "id": 1,
        "nome": "Perdigão Construções",
        "cnpj": "00.000.000/0000-00",
        "email": "perdigaoconstrucoes@gmail.com",
        "telefone": 16991736767,
        "criado em (meses)": 10,
        "Ativo": True
    }

    response = client.post("/usuarios", json=novo_usuario)

    assert response.status_code == 201
    mock_cursor.insert_one.assert_called_once_with(novo_usuario)


@patch("api.db")
def test_cria_usuario_trabalhador(mock_db, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_db.tbl_trabalhadores = mock_conn
    mock_conn.insert_one.return_value = mock_cursor

    mock_cursor.inserted_id = "2"

    novo_usuario = {
        "nome": "João",
        "email": "joao@email.com",
        "telefone": "16991736767",
        "cargo": "pedreiro"
    }

    response = client.post(
        "/trabalhadores/obra/123/",
        json=novo_usuario
    )

    assert response.status_code == 201
    mock_conn.insert_one.assert_called_once_with({
        "nome": "João",
        "email": "joao@email.com",
        "telefone": "16991736767",
        "cargo": "pedreiro",
        "obras": ["123"],
        "ativo": True,
        "criado_em": ANY
    })