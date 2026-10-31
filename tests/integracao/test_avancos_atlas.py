"""Integração opt-in em banco descartável e cluster exclusivo de teste."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from bson import ObjectId
from flask_jwt_extended import create_access_token
from freezegun import freeze_time
from pymongo.errors import OperationFailure

from support import TEST_INSTANT, isolated_app
from support_avancos import backend, dados
from support_midias import config, conteudos

from support_atlas import banco_uc09


def test_ct31_uc09_atlas_novo_processo(banco_uc09, backend, conteudos):
    # Preparação: nenhum arquivo ou documento da demonstração é utilizado.
    conta = ObjectId()
    marco = ObjectId()
    banco_uc09.tbl_construtora.insert_one(
        {"_id": conta, "ativo": True, "nome": "Fictícia", "email": "teste@example.com"}
    )
    banco_uc09.tbl_marcos.insert_one({"_id": marco, "nome": "Marco fictício"})
    with freeze_time(TEST_INSTANT, ignore=["pymongo"]), isolated_app(banco_uc09) as app:
        app.config["CONSTRUTORA_ID"] = str(conta)
        with app.app_context():
            token = create_access_token(
                identity=str(conta),
                additional_claims={"tipo": "construtora", "sessao_id": "teste-uc09"},
            )
        # Execução: upload simulado, transação MongoDB real.
        resposta = app.test_client().post(
            f"/marcos/{marco}/avancos",
            headers={"Authorization": "Bearer " + token},
            data=dados(conteudos["png"]),
        )
        assert resposta.status_code == 201
        env = dict(
            os.environ,
            TEST_UC09_DATABASE=banco_uc09.name,
            TEST_UC09_ACCOUNT=str(conta),
            TEST_UC09_PATH=resposta.headers["Location"],
            TEST_UC09_FETCH_CONTENT="0",
            TEST_UC09_FREEZE="1",
        )
        processo = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "uc09_restart_probe.py")],
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        # Verificação
        assert (
            processo.returncode == 0
        ), "Falha ao consultar o banco de teste em processo novo"
        recuperado = json.loads(processo.stdout)
        assert recuperado == {"status": 200, "body": resposta.get_json()}
        assert (
            banco_uc09.tbl_avancos.count_documents({})
            == banco_uc09.tbl_midias.count_documents({})
            == 1
        )
        assert recuperado["body"]["estado"] == "rascunho"


def test_ct35_rollback_real_do_atlas_com_falha_de_gravacao(
    banco_uc09, backend, conteudos
):
    # Preparação
    conta, marco = ObjectId(), ObjectId()
    banco_uc09.tbl_construtora.insert_one(
        {"_id": conta, "ativo": True, "nome": "Fictícia", "email": "teste@example.com"}
    )
    banco_uc09.tbl_marcos.insert_one({"_id": marco, "nome": "Marco fictício"})
    with freeze_time(TEST_INSTANT, ignore=["pymongo"]), isolated_app(banco_uc09) as app:
        app.config["CONSTRUTORA_ID"] = str(conta)
        with app.app_context():
            token = create_access_token(
                identity=str(conta),
                additional_claims={
                    "tipo": "construtora",
                    "sessao_id": "teste-rollback",
                },
            )
        # Execução: o primeiro insert chega ao Atlas; o segundo falha antes do commit.
        with patch.object(
            type(banco_uc09.tbl_midias),
            "insert_many",
            side_effect=OperationFailure("falha fictícia"),
        ):
            resposta = app.test_client().post(
                f"/marcos/{marco}/avancos",
                headers={"Authorization": "Bearer " + token},
                data=dados(conteudos["png"]),
            )
        # Verificação
        assert resposta.status_code == 503
        assert banco_uc09.tbl_avancos.count_documents({}) == 0
        assert banco_uc09.tbl_midias.count_documents({}) == 0
        assert banco_uc09.tbl_uploads_pendentes.count_documents({}) == 0
        assert "_versao_avancos" not in banco_uc09.tbl_marcos.find_one({"_id": marco})
        assert backend[0] == {}
