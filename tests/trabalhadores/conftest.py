"""Dados e adaptação de sessões compartilhados pelos testes de trabalhadores."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


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
def pessoa(database, trabalhador, obra_existente):
    documento = {
        **trabalhador,
        "_id": ObjectId(),
        "obras": [str(obra_existente["_id"])],
        "ativo": True,
    }
    database.tbl_trabalhadores.insert_one(documento)
    database.tbl_obras.update_one(
        {"_id": obra_existente["_id"]},
        {"$set": {"trabalhadores": [documento["email"]]}},
    )
    return documento


@pytest.fixture
def modulo_trabalhadores(app):
    # O app precisa ser carregado antes do import para isolar o banco.
    import trabalhadores

    return trabalhadores


@pytest.fixture
def sessao_cadastro(modulo_trabalhadores, request):
    """Memória verifica o fluxo; --atlas usa sessões e transações reais."""
    if request.config.getoption("--atlas"):
        yield None
        return

    session = MagicMock(name="sessao_ficticia")
    session.__enter__.return_value = session

    def sem_sessao(method):
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return method(*args, **kwargs)

        return executar

    with ExitStack() as stack:
        start = stack.enter_context(patch.object(
            modulo_trabalhadores.cliente_mongo, "start_session", return_value=session
        ))
        for collection, name in (
            (modulo_trabalhadores.colecao_obras, "find_one"),
            (modulo_trabalhadores.colecao_obras, "update_one"),
            (modulo_trabalhadores.colecao_trabalhadores, "insert_one"),
        ):
            method = getattr(collection, name)
            stack.enter_context(patch.object(
                collection, name, side_effect=sem_sessao(method)
            ))
        yield start, session
