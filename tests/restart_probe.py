"""Processo independente usado exclusivamente por CT-09."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from support import TEST_INSTANT, isolated_app
from freezegun import freeze_time


@freeze_time(TEST_INSTANT)
def main():
    name = os.environ["TEST_DATABASE_NAME"]
    if not name.startswith("tests_"):
        raise ValueError("Namespace de teste obrigatório")
    with MongoClient(
        os.environ["TEST_MONGO_URI"], serverSelectionTimeoutMS=5000
    ) as mongo:
        with isolated_app(mongo[name]) as app:
            with app.app_context():
                from construtora import gerar_tokens_construtora

                account = mongo[name].tbl_construtora.find_one({"email": "construtora@example.com"})
                token, _ = gerar_tokens_construtora(account["_id"])
            response = app.test_client().get(
                os.environ["TEST_RESOURCE_PATH"],
                headers={"Authorization": "Bearer " + token},
            )
            print(
                json.dumps(
                    {"status": response.status_code, "body": response.get_json()}
                )
            )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)  # Não expõe URI/credenciais em traceback do processo filho.
