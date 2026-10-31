"""UC-09 com MongoDB e Cloudinary reais, exclusivamente com credenciais de teste."""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from bson import ObjectId
from flask_jwt_extended import create_access_token

from support import isolated_app
from support_midias import conteudos
from tests.test_avancos_uc09 import dados
from tests.test_avancos_atlas import banco_uc09


@pytest.fixture
def cloud_uc09(request, monkeypatch):
    if not request.config.getoption("--uc09-cloudinary"):
        pytest.skip(
            "Exige --uc09-cloudinary e credenciais TEST_UC09_CLOUDINARY_* exclusivas"
        )
    if not request.config.getoption("--uc09-atlas"):
        pytest.fail("A integração real exige também --uc09-atlas", pytrace=False)
    for name in ("CLOUD_NAME", "API_KEY", "API_SECRET"):
        valor = os.environ.get("TEST_UC09_CLOUDINARY_" + name)
        if not valor:
            pytest.fail(
                "Configure todas as credenciais TEST_UC09_CLOUDINARY_* exclusivas de teste",
                pytrace=False,
            )
        monkeypatch.setenv("CLOUDINARY_" + name, valor)
    monkeypatch.setenv("CLOUDINARY_FOLDER", "tests_uc09/" + uuid4().hex)


@pytest.mark.parametrize("extensao", ["png", "mp4", "pdf"])
def test_ct31_ct32_arquivo_real_apos_reinicio(
    cloud_uc09, banco_uc09, conteudos, extensao
):
    # Preparação
    conta, marco = ObjectId(), ObjectId()
    banco_uc09.tbl_construtora.insert_one(
        {"_id": conta, "ativo": True, "nome": "Fictícia", "email": "teste@example.com"}
    )
    banco_uc09.tbl_marcos.insert_one({"_id": marco, "nome": "Marco fictício"})
    try:
        with isolated_app(banco_uc09) as app:
            app.config["CONSTRUTORA_ID"] = str(conta)
            with app.app_context():
                token = create_access_token(
                    identity=str(conta),
                    additional_claims={
                        "tipo": "construtora",
                        "sessao_id": "integracao-real",
                    },
                )
            # Execução
            resposta = app.test_client().post(
                f"/marcos/{marco}/avancos",
                headers={"Authorization": "Bearer " + token},
                data=dados(conteudos[extensao], extensao),
            )
            assert resposta.status_code == 201
            env = dict(
                os.environ,
                TEST_UC09_DATABASE=banco_uc09.name,
                TEST_UC09_ACCOUNT=str(conta),
                TEST_UC09_PATH=resposta.headers["Location"],
                TEST_UC09_FETCH_CONTENT="1",
                TEST_UC09_FREEZE="0",
            )
            processo = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("uc09_restart_probe.py")),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            # Verificação
            assert (
                processo.returncode == 0
            ), "Falha ao consultar avanço em processo novo"
            resultado = json.loads(processo.stdout)
            assert resultado["status"] == resultado["arquivo_status"] == 200
            assert resultado["body"] == resposta.get_json()
            assert base64.b64decode(resultado["arquivo_base64"]) == conteudos[extensao]
            assert resultado["body"]["estado"] == "rascunho"
    finally:
        # Usa as referências duráveis, inclusive caso ocorra falha após o upload.
        from app.integracoes.armazenamento import ArmazenamentoCloudinary

        armazenamento = ArmazenamentoCloudinary()
        falhas = []
        for operacao in banco_uc09.tbl_uploads_pendentes.find():
            for referencia in operacao.get("referencias", []):
                try:
                    armazenamento.remover(referencia)
                except Exception:
                    falhas.append(referencia)
        if falhas:
            banco_uc09.tbl_uc09_cleanup_failures.insert_one({"referencias": falhas})
            pytest.fail(
                "Falha ao limpar mídias de teste; banco preservado para reconciliação",
                pytrace=False,
            )
