"""O vínculo com a empresa vem da sessão e independe da lista de obras."""

from bson import ObjectId

from support import snapshot


def test_empresa_vem_da_sessao_e_permanece_sem_obras(
    client, headers, database, account, obra_existente, trabalhador,
):
    resposta = client.post(f"/trabalhadores/obra/{obra_existente['_id']}/",
                          json={**trabalhador, "construtora_id": str(ObjectId())}, headers=headers)
    assert resposta.status_code == 201
    identificador = ObjectId(resposta.get_json()["id"])
    salvo = database.tbl_trabalhadores.find_one({"_id": identificador})
    assert salvo["construtora_id"] == str(account["_id"])
    edicao = client.patch(f"/trabalhadores/{identificador}/", json={"obras": []}, headers=headers)
    assert edicao.status_code == 200
    salvo = database.tbl_trabalhadores.find_one({"_id": identificador})
    assert salvo["obras"] == [] and salvo["construtora_id"] == str(account["_id"])


def test_vinculo_expresso_impede_consulta_e_alteracao_por_outra_empresa(
    client, headers, database, trabalhador,
):
    identificador = database.tbl_trabalhadores.insert_one({
        **trabalhador, "construtora_id": str(ObjectId()), "obras": [],
    }).inserted_id
    antes = snapshot(database)
    assert client.patch(f"/trabalhadores/{identificador}/", json={"nome": "Indevido"}, headers=headers).status_code == 404
    assert client.delete(f"/trabalhadores/{identificador}/", headers=headers).status_code == 404
    assert client.get(f"/trabalhadores/cargo/{trabalhador['cargo']}/", headers=headers).get_json() == []
    assert snapshot(database) == antes
