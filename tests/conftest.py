import uuid
from unittest.mock import patch
from datetime import timedelta

import mongomock
import pytest
from bson import ObjectId
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token
from freezegun import freeze_time
from werkzeug.exceptions import HTTPException

from mongo_support import BancoDaExecucao, NOME_DO_BANCO, conectar_mongo, obter_mongo_uri
from support import TEST_INSTANT, isolated_app


def pytest_addoption(parser):
    parser.addoption("--atlas", action="store_true", help="Usar MONGO_URI do ambiente ou .env")
    parser.addoption("--uc09-atlas", action="store_true", help="UC-09 em cluster exclusivo TEST_UC09_MONGO_URI")
    parser.addoption("--uc09-cloudinary", action="store_true", help="UC-09 com Cloudinary exclusivo de teste")
    parser.addoption(
        "--require-routes",
        action="store_true",
        help="Falhar se uma rota estiver ausente",
    )


@pytest.fixture(scope="session")
def storage(request):
    if not request.config.getoption("--atlas"):
        with mongomock.MongoClient() as client:
            yield client
        return
    try:
        client = conectar_mongo()
    except RuntimeError as erro:
        pytest.fail(str(erro), pytrace=False)
    try:
        with patch.dict("os.environ", {"MONGO_URI": obter_mongo_uri()}):
            yield client
    finally:
        client.close()


@pytest.fixture
def database(storage):
    db = BancoDaExecucao(storage[NOME_DO_BANCO], "tests_" + uuid.uuid4().hex + "_")
    try:
        yield db
    finally:
        db.limpar_colecoes()


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
            f"{request.node.name}: exige --atlas com MONGO_URI; memória não comprova persistência"
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
    with freeze_time(TEST_INSTANT, ignore=["pymongo"]):
        yield


@pytest.fixture
def client(app, clock):
    with app.test_client() as client:
        yield client


@pytest.fixture
def account(database, app):
    account = {
        "_id": ObjectId(),
        "nome": "Construtora Teste",
        "email": "construtora@example.com",
        "senha_hash": Bcrypt().generate_password_hash("Senha_teste123!").decode(),
        "ativo": True,
    }
    database.tbl_construtora.insert_one(account)
    app.config["CONSTRUTORA_ID"] = str(account["_id"])
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
