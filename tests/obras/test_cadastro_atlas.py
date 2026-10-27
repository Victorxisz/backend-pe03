"""CT-09: persistência após novo processo no Atlas."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
import pytest
from support_obras import BASE, DETAIL, ID, assert_created

routes = pytest.mark.routes


@pytest.mark.atlas
@routes(("POST", BASE), ("GET", DETAIL))
def test_ct09_persistencia_atlas_apos_novo_processo(
    app, client, headers, database, obra
):
    # Preparação
    probe = Path(__file__).resolve().parents[1] / "restart_probe.py"
    expected_fields = deepcopy(obra)

    # Execução
    created = client.post(BASE, json=obra, headers=headers)
    identifier = (created.get_json() or {}).get("id", "id-ausente")
    path = BASE + "/" + identifier
    with app.test_client() as fresh:
        reloaded = fresh.get(path, headers=headers)
    env = dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=path)
    result = subprocess.run(
        [sys.executable, str(probe)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Verificação
    created_body = assert_created(created, database, obra)
    assert reloaded.status_code == 200
    assert result.returncode == 0, "Falha no processo novo; credenciais omitidas"
    restarted = json.loads(result.stdout)
    assert restarted["status"] == 200
    for recovered in (reloaded.get_json(), restarted["body"]):
        assert recovered["id"] == identifier
        for field, value in expected_fields.items():
            assert recovered[field] == value, f"Campo não recuperado: {field}"
        for field in ("autor", "data_registro"):
            assert recovered[field] == created_body[field]
    assert restarted["body"] == reloaded.get_json()

