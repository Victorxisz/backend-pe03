"""Persistência de trabalhadores: --atlas usa coleções temporárias e nova conexão."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from bson import ObjectId

from mongo_support import BancoDaExecucao, conectar_mongo
from support import snapshot


pytestmark = pytest.mark.atlas


def reler_em_novo_processo(database, caminho):
    """Repete a leitura autenticada em um processo e conexão recém-criados."""
    sonda = Path(__file__).resolve().parents[1] / "restart_probe.py"
    ambiente = dict(
        os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=caminho
    )
    resultado = subprocess.run(
        [sys.executable, str(sonda)], env=ambiente,
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0, "Falha no processo novo; credenciais omitidas"
    return json.loads(resultado.stdout)


def test_cadastro_listado_e_consultado_apos_reinicio(
    client, headers, database, trabalhador, obra_existente, obra
):
    """CT-94: listagem e detalhe sobrevivem ao reinício; obra sem vínculo não mostra."""
    # Preparação
    obra_id = str(obra_existente["_id"])
    outra_obra = database.tbl_obras.insert_one(dict(obra)).inserted_id

    # Execução
    criado = client.post(f"/trabalhadores/obra/{obra_id}/", headers=headers, json=trabalhador)
    assert criado.status_code == 201
    identificador = criado.get_json()["id"]
    detalhe = reler_em_novo_processo(database, f"/trabalhadores/{identificador}/")
    listagem = reler_em_novo_processo(database, f"/trabalhadores/obra/{obra_id}/")
    sem_vinculo = reler_em_novo_processo(database, f"/trabalhadores/obra/{outra_obra}/")

    # Verificação
    assert criado.headers["Location"] == f"/trabalhadores/{identificador}/"
    assert detalhe["status"] == 200
    assert detalhe["body"]["id"] == identificador
    assert detalhe["body"]["obras"] == [obra_id]
    assert detalhe["body"]["ativo"] is True
    assert detalhe["body"]["data_cadastro"]
    for campo, valor in trabalhador.items():
        assert detalhe["body"][campo] == valor, f"Campo não recuperado: {campo}"
    assert listagem["status"] == 200
    assert listagem["body"] == [detalhe["body"]]
    assert sem_vinculo["status"] == 200
    assert sem_vinculo["body"] == []


def test_detalhe_de_trabalhador_ausente_apos_reinicio(client, headers, database, pessoa):
    """Trabalhador inexistente permanece 404 e não vira erro de banco."""
    antes = snapshot(database)
    ausente = reler_em_novo_processo(database, f"/trabalhadores/{ObjectId()}/")
    existente = reler_em_novo_processo(database, f"/trabalhadores/{pessoa['_id']}/")

    assert ausente["status"] == 404
    assert ausente["body"] == {"erro": "Trabalhador não encontrado"}
    assert existente["status"] == 200
    assert existente["body"]["id"] == str(pessoa["_id"])
    with conectar_mongo() as fresh:
        assert snapshot(BancoDaExecucao(fresh[database.name], database.prefixo)) == antes


def test_cadastro_edicao_e_exclusao_persistem_em_nova_conexao(
    client, headers, database, trabalhador, obra_existente
):
    path = f"/trabalhadores/obra/{obra_existente['_id']}/"
    response = client.post(path, headers=headers, json=trabalhador)
    assert response.status_code == 201
    identificador = response.get_json()["id"]
    filtro = {"_id": ObjectId(identificador)}
    with conectar_mongo() as fresh:
        banco = BancoDaExecucao(fresh[database.name], database.prefixo)
        salvo = banco.tbl_trabalhadores.find_one(filtro)
        assert salvo is not None
        assert salvo["obras"] == [str(obra_existente["_id"])]
        assert salvo["email"] == trabalhador["email"]
        assert banco.tbl_obras.find_one({"_id": obra_existente["_id"]}) == obra_existente

        response = client.patch(
            f"/trabalhadores/{identificador}/", headers=headers,
            json={"email": "novo@example.com", "obras": []},
        )
        assert response.status_code == 200
        assert banco.tbl_trabalhadores.find_one(filtro) == {
            **salvo, "email": "novo@example.com", "obras": []
        }
        response = client.delete(f"/trabalhadores/{identificador}/", headers=headers)
        assert response.status_code == 200
        assert banco.tbl_trabalhadores.find_one(filtro) is None
        assert banco.tbl_obras.find_one({"_id": obra_existente["_id"]}) == obra_existente


def test_rejeicao_de_vinculo_inexistente_preserva_banco_real(
    client, headers, database, pessoa
):
    antes = snapshot(database)
    response = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"obras": [str(ObjectId())]},
    )
    assert response.status_code == 422
    with conectar_mongo() as fresh:
        assert snapshot(BancoDaExecucao(fresh[database.name], database.prefixo)) == antes
