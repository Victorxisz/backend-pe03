"""Consulta UC-09 em outro processo usando apenas o cluster de teste explícito."""

import base64
from contextlib import nullcontext
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask_jwt_extended import create_access_token
from freezegun import freeze_time
from pymongo import MongoClient

from support import TEST_INSTANT, isolated_app


def main():
    name = os.environ["TEST_UC09_DATABASE"]
    if not name.startswith("tests_uc09_"):
        raise ValueError("Banco exclusivo de teste obrigatório")
    with MongoClient(
        os.environ["TEST_UC09_MONGO_URI"], serverSelectionTimeoutMS=5000
    ) as mongo:
        with isolated_app(mongo[name]) as app:
            app.config["CONSTRUTORA_ID"] = os.environ["TEST_UC09_ACCOUNT"]
            with app.app_context():
                token = create_access_token(
                    identity=app.config["CONSTRUTORA_ID"],
                    additional_claims={
                        "tipo": "construtora",
                        "sessao_id": "teste-reinicio",
                    },
                )
            response = app.test_client().get(
                os.environ["TEST_UC09_PATH"],
                headers={"Authorization": "Bearer " + token},
            )
            resultado = {"status": response.status_code, "body": response.get_json()}
            if (
                os.environ.get("TEST_UC09_FETCH_CONTENT") == "1"
                and response.status_code == 200
            ):
                arquivo = app.test_client().get(
                    response.get_json()["midias"][0]["conteudo"],
                    headers={"Authorization": "Bearer " + token},
                )
                resultado["arquivo_status"] = arquivo.status_code
                resultado["arquivo_base64"] = base64.b64encode(arquivo.data).decode(
                    "ascii"
                )
            print(json.dumps(resultado))


if __name__ == "__main__":
    try:
        relogio = (
            freeze_time(TEST_INSTANT, ignore=["pymongo"])
            if os.environ.get("TEST_UC09_FREEZE") == "1"
            else nullcontext()
        )
        with relogio:
            main()
    except Exception:
        sys.exit(1)  # Credenciais e detalhes do servidor não vão para stdout/stderr.
