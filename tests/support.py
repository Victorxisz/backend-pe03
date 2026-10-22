"""Carregamento isolado: nunca lê .env nem escolhe a base da demonstração."""

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEST_INSTANT = "2030-10-20 12:00:00"
SECRET = "chave-ficticia-de-testes-jwt-com-mais-de-32-bytes"


class RestrictedClient:
    def __init__(self, database):
        self.database = database

    def __getitem__(self, name):
        # db.py ainda fixa banco_de_dados. Redireciona para o namespace descartável.
        return self.database

    def get_database(self, *args, **kwargs):
        return self.database

    def get_default_database(self, *args, **kwargs):
        return self.database

    def start_session(self, *args, **kwargs):
        return self.database.client.start_session(*args, **kwargs)


@contextmanager
def isolated_app(database):
    names = {p.stem for p in ROOT.glob("*.py")} | {"app"}
    removed = {
        k: v for k, v in list(sys.modules.items()) if k in names or k.startswith("app.")
    }
    for k in removed:
        del sys.modules[k]
    try:
        with patch.dict(
            "os.environ",
            {
                "MONGO_URI": "mongodb://127.0.0.1/tests_disabled",
                "JWT_SECRET_KEY": SECRET,
            },
        ), patch("dotenv.load_dotenv"), patch(
            "pymongo.MongoClient", return_value=RestrictedClient(database)
        ):
            app = importlib.import_module("api").app
            app.config.update(TESTING=True, JWT_SECRET_KEY=SECRET)
            yield app
    finally:
        for k in list(sys.modules):
            if k in names or k.startswith("app."):
                del sys.modules[k]
        sys.modules.update(removed)


def snapshot(database):
    return {
        name: sorted(list(database[name].find()), key=lambda d: str(d["_id"]))
        for name in database.list_collection_names()
        if database[name].count_documents({})
    }
