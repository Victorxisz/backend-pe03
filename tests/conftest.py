import os
import uuid
from datetime import timedelta

import mongomock
import pytest
from bson import ObjectId
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token
from freezegun import freeze_time
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri
from werkzeug.exceptions import HTTPException

from support import TEST_INSTANT, isolated_app


def pytest_addoption(parser):
    parser.addoption("--atlas", action="store_true", help="Usar somente TEST_MONGO_URI")
    parser.addoption(
        "--require-routes",
        action="store_true",
        help="Falhar se uma rota estiver ausente",
    )


@pytest.fixture(scope="session")
def storage(request):
    if not request.config.getoption("--atlas"):
        yield mongomock.MongoClient(), "tests_memory"
        return
    uri = os.environ.get("TEST_MONGO_URI", "")
    # Valida antes de criar cliente. Não imprime URI/credenciais em erros.
    try:
        parsed = parse_uri(uri)
        valid = uri.startswith("mongodb+srv://") and (
            parsed["database"] or ""
        ).startswith("tests_")
    except Exception:
        valid = False
    if not valid:
        pytest.fail(
            "--atlas exige TEST_MONGO_URI do Atlas com banco iniciado por tests_; .env não é lido",
            pytrace=False,
        )
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        pytest.fail(
            "Atlas de teste indisponível; verifique acesso e credenciais de teste",
            pytrace=False,
        )
    yield client, parsed["database"]
    client.close()


@pytest.fixture
def database(storage):
    client, prefix = storage
    # O Atlas Free limita o nome do banco a 38 bytes.
    name = prefix[:13] + "_" + uuid.uuid4().hex[:24]
    assert name.startswith("tests_")
    db = client[name]
    yield db
    # Só remove o namespace aleatório criado por esta fixture.
    client.drop_database(name)


@pytest.fixture
def app(database):
    with isolated_app(database) as application:
        yield application


@pytest.fixture(autouse=True)
def prerequisites(request):
    if request.node.get_closest_marker("atlas") and not request.config.getoption(
        "--atlas"
    ):
        pytest.skip(
            f"{request.node.name}: exige --atlas e TEST_MONGO_URI; memória não comprova persistência"
        )
    marker = request.node.get_closest_marker("routes")
    if not marker:
        return
    app = request.getfixturevalue("app")
    missing = []
    for method, path in marker.args:
        try:
            app.url_map.bind("localhost").match(path, method=method)
        except HTTPException:
            missing.append(f"{method} {path}")
    if missing:
        reason = "Dependência de implementação: " + ", ".join(missing)
        if request.config.getoption("--require-routes"):
            pytest.fail(reason, pytrace=False)
        pytest.skip(reason)


@pytest.fixture
def clock():
    with freeze_time(TEST_INSTANT):
        yield


@pytest.fixture
def client(app, clock):
    with app.test_client() as client:
        yield client


@pytest.fixture
def account(database):
    account = {
        "_id": ObjectId(),
        "nome": "Construtora Teste",
        "email": "construtora@example.com",
        "senha_hash": Bcrypt().generate_password_hash("Senha_teste123!").decode(),
        "ativo": True,
    }
    database.tbl_construtora.insert_one(account)
    return account


@pytest.fixture
def headers(app, client, account):
    with app.app_context():
        from construtora import gerar_tokens_construtora

        token, _ = gerar_tokens_construtora(account["_id"])
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def emitir_headers(app, client, account):
    """Emite tokens reais, inclusive para os cenários negativos de autenticação."""
    def emitir(tipo_token="access", identidade=None, claims=None, expirado=False):
        informacoes = {"tipo": "construtora", "sessao_id": uuid.uuid4().hex}
        if claims is not None:
            informacoes.update(claims)
        criar = create_refresh_token if tipo_token == "refresh" else create_access_token
        opcoes = {"expires_delta": timedelta(seconds=-60)} if expirado else {}
        with app.app_context():
            token = criar(
                identity=str(account["_id"]) if identidade is None else identidade,
                additional_claims=informacoes,
                **opcoes,
            )
        return {"Authorization": "Bearer " + token}

    return emitir


@pytest.fixture
def obra():
    return {
        "nome": "Casa Teste",
        "tipo": "casa",
        "cliente": "Cliente Fictício",
        "localizacao": "Campinas, SP",
        "descricao": "Construção residencial",
        "inicio": "2030-01-15",
        "entrega": {"modalidade": "data_exata", "data": "2030-12-20"},
    }
