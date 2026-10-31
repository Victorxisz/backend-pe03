"""Processo independente para releitura autenticada de recursos no Atlas."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mongo_support import conectar_mongo, recuperar_banco_da_execucao
from support import TEST_INSTANT, isolated_app
from freezegun import freeze_time


@freeze_time(TEST_INSTANT, ignore=["pymongo"])
def main():
    with conectar_mongo() as mongo:
        database = recuperar_banco_da_execucao(mongo)
        with isolated_app(database) as app:
            with app.app_context():
                from construtora import gerar_tokens_construtora

                account = database.tbl_construtora.find_one({"email": "construtora@example.com"})
                app.config["CONSTRUTORA_ID"] = str(account["_id"])
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
