"""CT-21: reinicia a aplicação e lê o marco no Atlas sem depender do futuro GET."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bson import ObjectId

from mongo_support import conectar_mongo, recuperar_banco_da_execucao
from support import isolated_app


def consultar_marco_apos_reinicio(banco_de_teste):
    with isolated_app(banco_de_teste):
        import db

        marco = db.colecao_marcos.find_one({"_id": ObjectId(os.environ["TEST_MARCO_ID"])})
        if marco is None:
            raise RuntimeError("Marco não encontrado após reinício")
        marco["_id"] = str(marco["_id"])
        marco["obra_id"] = str(marco["obra_id"])
        return marco


def executar_consulta():
    with conectar_mongo() as cliente:
        return consultar_marco_apos_reinicio(recuperar_banco_da_execucao(cliente))


if __name__ == "__main__":
    try:
        print(json.dumps(executar_consulta()))
    except Exception:
        sys.exit(1)  # Não expõe URI ou credenciais em erros do processo filho.
