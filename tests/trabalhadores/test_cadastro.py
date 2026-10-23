"""Regressão das rotas já existentes na branch MatheusHermida (fora CT-01..17)."""

from contextlib import ExitStack
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from support import snapshot


@pytest.fixture
def trabalhador():
    return {
        "nome": "João Fictício",
        "email": "joao@example.com",
        "telefone": "16991736767",
        "cargo": "pedreiro",
    }


@pytest.fixture
def obra_existente(database, obra):
    documento = {**obra, "_id": ObjectId("507f1f77bcf86cd799439011")}
    database.tbl_obras.insert_one(documento)
    return documento


@pytest.fixture
def sessao_cadastro(app, database, request):
    """Mongomock não implementa sessões; Atlas usa a sessão real, sem adaptações."""
    if request.config.getoption("--atlas"):
        yield None
        return

    import trabalhadores

    session = MagicMock(name="sessao_ficticia")
    session.__enter__.return_value = session

    def sem_sessao(method):
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return method(*args, **kwargs)

        return executar

    with ExitStack() as stack:
        start = stack.enter_context(
            patch.object(
                trabalhadores.cliente_mongo, "start_session", return_value=session
            )
        )
        for collection, name in (
            (trabalhadores.colecao_obras, "find_one"),
            (trabalhadores.colecao_obras, "update_one"),
            (trabalhadores.colecao_trabalhadores, "insert_one"),
        ):
            method = getattr(collection, name)
            stack.enter_context(
                patch.object(collection, name, side_effect=sem_sessao(method))
            )
        yield start, session


def test_cadastro_trabalhador(
    client, headers, database, trabalhador, obra_existente, sessao_cadastro
):
    # Preparação
    obra_id = str(obra_existente["_id"])
    path = f"/trabalhadores/obra/{obra_id}/"

    # Execução
    response = client.post(path, json=trabalhador, headers=headers)

    # Verificação
    assert response.status_code == 201
    body = response.get_json()
    assert body["mensagem"] == "Trabalhador criado com sucesso e vinculado à obra"
    assert body["obra_id"] == obra_id
    saved = database.tbl_trabalhadores.find_one({"_id": ObjectId(body["id"])})
    assert saved is not None
    for field, value in trabalhador.items():
        assert saved[field] == value
    assert saved["obras"] == [obra_id]
    assert saved["ativo"] is True
    assert saved["data_cadastro"] == datetime(2030, 10, 20, 12)
    assert database.tbl_trabalhadores.count_documents({}) == 1
    assert database.tbl_obras.find_one({"_id": obra_existente["_id"]}) == {
        **obra_existente,
        "trabalhadores": [trabalhador["email"]],
    }
    if sessao_cadastro is not None:
        start, session = sessao_cadastro
        start.assert_called_once_with()
        session.start_transaction.assert_called_once_with()
        session.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.parametrize("campo", ["nome", "email", "telefone", "cargo"])
def test_cadastro_trabalhador_campo_ausente(
    client, headers, database, trabalhador, campo, obra_existente
):
    # Preparação
    del trabalhador[campo]
    before = snapshot(database)
    path = f"/trabalhadores/obra/{obra_existente['_id']}/"

    # Execução
    response = client.post(path, json=trabalhador, headers=headers)

    # Verificação
    assert response.status_code == 422
    assert response.get_json() == {
        "erro": f"O campo '{campo}' deve ser um texto preenchido"
    }
    assert snapshot(database) == before
