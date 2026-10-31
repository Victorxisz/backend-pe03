"""Banco descartável para integrações UC-09 opt-in."""
import os
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri

from support import TEST_INSTANT, isolated_app
from support_avancos import backend, dados
from support_midias import config, conteudos


@pytest.fixture
def banco_uc09(request):
    if not request.config.getoption("--uc09-atlas"):
        pytest.skip(
            "Exige --uc09-atlas e TEST_UC09_MONGO_URI de cluster exclusivo de teste"
        )
    uri = os.environ.get("TEST_UC09_MONGO_URI", "")
    try:
        parsed = parse_uri(uri)
        valid = uri.startswith("mongodb+srv://") and (
            parsed["database"] or ""
        ).startswith("tests_uc09_")
    except Exception:
        valid = False
    if not valid:
        pytest.fail(
            "Informe TEST_UC09_MONGO_URI do cluster de teste com banco tests_uc09_*",
            pytrace=False,
        )
    cliente = MongoClient(uri, serverSelectionTimeoutMS=5000)
    nome = "tests_uc09_" + uuid4().hex
    try:
        cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.fail("Cluster exclusivo de teste indisponível", pytrace=False)
    try:
        yield cliente[nome]
    finally:
        try:
            if cliente[nome].tbl_uc09_cleanup_failures.count_documents({}):
                pytest.fail(
                    f"Banco de teste {nome} preservado: limpeza pendente", pytrace=False
                )
            cliente.drop_database(nome)
        finally:
            cliente.close()
