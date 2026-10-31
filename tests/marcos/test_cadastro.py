"""CT-18/19 e CT-21: cadastro, rejeições e persistência de marcos."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError, WriteError

from support import snapshot


CAMINHO_MARCOS = "/obras/{}/marcos"


def dados_do_marco():
    return {
        "nome": "Fundação",
        "descricao": "Fundação concluída e conferida",
        "inicio_previsto": "2030-02-01",
        "fim_previsto": "2030-02-15",
    }


@pytest.fixture
def obra_cadastrada(client, headers, obra):
    resposta = client.post("/obras", json=obra, headers=headers)
    assert resposta.status_code == 201
    return resposta.get_json()["id"]


def conferir_resposta_de_cadastro(resposta, obra_id):
    assert resposta.status_code == 201, resposta.get_data(as_text=True)
    marco = resposta.get_json()
    assert isinstance(marco["id"], str) and ObjectId.is_valid(marco["id"])
    assert marco == {
        **dados_do_marco(),
        "id": marco["id"],
        "obra_id": obra_id,
        "estado": "a iniciar",
    }
    assert resposta.headers["Location"] == f"{CAMINHO_MARCOS.format(obra_id)}/{marco['id']}"
    return marco


def conferir_marco_salvo(database, marco):
    marco_esperado = {
        **marco,
        "_id": ObjectId(marco["id"]),
        "obra_id": ObjectId(marco["obra_id"]),
    }
    marco_esperado.pop("id")
    assert database.tbl_marcos.find_one({"_id": marco_esperado["_id"]}) == marco_esperado
    assert database.tbl_marcos.count_documents({}) == 1


def conferir_rejeicao(resposta, status, campos):
    assert resposta.status_code == status
    assert resposta.get_json()["mensagem"]
    assert resposta.get_json()["campos"] == campos


def test_ct18_cria_marco_vinculado_e_com_estado_inicial(
    client, headers, database, obra_cadastrada
):
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), json=dados_do_marco(), headers=headers
    )
    marco = conferir_resposta_de_cadastro(resposta, obra_cadastrada)
    conferir_marco_salvo(database, marco)


def test_ct18_remove_espacos_dos_textos(client, headers, database, obra_cadastrada):
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), headers=headers,
        json={
            **dados_do_marco(),
            "nome": " Fundação ",
            "descricao": " Fundação concluída e conferida ",
        },
    )
    marco = conferir_resposta_de_cadastro(resposta, obra_cadastrada)
    conferir_marco_salvo(database, marco)


def test_ct18_aceita_inicio_e_fim_no_mesmo_dia(
    client, headers, database, obra_cadastrada
):
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), headers=headers,
        json={**dados_do_marco(), "fim_previsto": "2030-02-01"},
    )
    assert resposta.status_code == 201
    assert resposta.get_json()["fim_previsto"] == "2030-02-01"
    conferir_marco_salvo(database, resposta.get_json())


@pytest.mark.parametrize(
    "alteracoes,campos",
    [
        pytest.param({"nome": ""}, ["nome"], id="nome-vazio"),
        pytest.param({"nome": "  "}, ["nome"], id="nome-em-branco"),
        pytest.param({"nome": 123}, ["nome"], id="nome-numerico"),
        pytest.param({"descricao": None}, ["descricao"], id="descricao-nula"),
        pytest.param({"descricao": " "}, ["descricao"], id="descricao-em-branco"),
        pytest.param({"inicio_previsto": "31/01/2030"}, ["inicio_previsto"], id="formato"),
        pytest.param({"inicio_previsto": "2030-02-30"}, ["inicio_previsto"], id="dia-inexistente"),
        pytest.param({"inicio_previsto": "20300201"}, ["inicio_previsto"], id="data-compacta"),
        pytest.param({"inicio_previsto": "2030-W05-5"}, ["inicio_previsto"], id="data-semanal"),
        pytest.param({"fim_previsto": None}, ["fim_previsto"], id="data-nula"),
        pytest.param(
            {"fim_previsto": "2030-01-31"}, ["inicio_previsto", "fim_previsto"],
            id="periodo-invertido",
        ),
        pytest.param({"estado": "concluído"}, ["estado"], id="estado-reservado"),
        pytest.param({"obra_id": "outra-obra"}, ["obra_id"], id="vinculo-reservado"),
        pytest.param({"id": "outro-marco"}, ["id"], id="id-reservado"),
        pytest.param({"_id": "outro-marco"}, ["_id"], id="id-mongo-reservado"),
    ],
)
def test_ct19_dados_invalidos_nao_criam_marco(
    client, headers, database, obra_cadastrada, alteracoes, campos
):
    banco_antes = snapshot(database)
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), headers=headers,
        json={**dados_do_marco(), **alteracoes},
    )
    conferir_rejeicao(resposta, 422, campos)
    assert snapshot(database) == banco_antes


@pytest.mark.parametrize("campo", ["nome", "descricao", "inicio_previsto", "fim_previsto"])
def test_ct19_campo_obrigatorio_ausente(
    client, headers, database, obra_cadastrada, campo
):
    dados_incompletos = dados_do_marco()
    dados_incompletos.pop(campo)
    banco_antes = snapshot(database)
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), json=dados_incompletos, headers=headers
    )
    conferir_rejeicao(resposta, 422, [campo])
    assert snapshot(database) == banco_antes


@pytest.mark.parametrize("corpo", ["{", "[]", "null", '"texto"'])
def test_ct19_corpo_invalido(client, headers, database, obra_cadastrada, corpo):
    banco_antes = snapshot(database)
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), headers=headers,
        data=corpo, content_type="application/json",
    )
    conferir_rejeicao(resposta, 422, ["corpo"])
    assert snapshot(database) == banco_antes


@pytest.mark.parametrize(
    "obra_id,status", [("id-invalido", 400), (str(ObjectId()), 404)]
)
def test_ct19_obra_invalida_ou_inexistente(
    client, headers, database, obra_id, status
):
    banco_antes = snapshot(database)
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_id), json=dados_do_marco(), headers=headers
    )
    conferir_rejeicao(resposta, status, ["obra_id"])
    assert snapshot(database) == banco_antes


def test_cadastro_de_marco_exige_autenticacao(client, database, obra_cadastrada):
    banco_antes = snapshot(database)
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), json=dados_do_marco()
    )
    assert resposta.status_code == 401
    assert snapshot(database) == banco_antes


@pytest.mark.parametrize(
    "falha", [WriteError("rejeitada"), ServerSelectionTimeoutError("indisponível")]
)
def test_falha_ao_salvar_marco_nao_anuncia_sucesso(
    client, headers, database, obra_cadastrada, falha
):
    banco_antes = snapshot(database)
    with patch("db.colecao_marcos.insert_one", side_effect=falha):
        resposta = client.post(
            CAMINHO_MARCOS.format(obra_cadastrada), json=dados_do_marco(), headers=headers
        )
    assert resposta.status_code == 500
    assert resposta.get_json()["mensagem"]
    assert "Location" not in resposta.headers
    assert snapshot(database) == banco_antes


def consultar_marco_em_novo_processo(database, id_marco):
    processo = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "restart_marcos_probe.py")],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_MARCO_ID=id_marco),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert processo.returncode == 0, "Falha na releitura após reinício; credenciais omitidas"
    return json.loads(processo.stdout)


@pytest.mark.atlas
def test_ct21_persistencia_atlas_apos_reinicio(
    client, headers, database, obra_cadastrada
):
    resposta = client.post(
        CAMINHO_MARCOS.format(obra_cadastrada), json=dados_do_marco(), headers=headers
    )
    marco = conferir_resposta_de_cadastro(resposta, obra_cadastrada)
    assert consultar_marco_em_novo_processo(database, marco["id"]) == {
        **dados_do_marco(),
        "_id": marco["id"],
        "obra_id": obra_cadastrada,
        "estado": "a iniciar",
    }
