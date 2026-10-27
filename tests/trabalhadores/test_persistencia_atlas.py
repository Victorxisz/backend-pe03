"""Persistência de trabalhadores: --atlas usa coleções temporárias e nova conexão."""

import pytest
from bson import ObjectId

from mongo_support import BancoDaExecucao, conectar_mongo
from support import snapshot


pytestmark = pytest.mark.atlas


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
