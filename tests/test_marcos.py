"""CT-18/19: cadastro de marcos e validações sem gravação parcial."""

from bson import ObjectId

from support import snapshot


PATH = "/api/v1/obras/{}/marcos"


def payload():
    return {
        "nome": "Fundação",
        "descricao": "Fundação concluída e conferida",
        "inicio_previsto": "2030-02-01",
        "fim_previsto": "2030-02-15",
    }


def test_ct18_cria_marco_vinculado_e_com_estado_inicial(client, headers, database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id

    response = client.post(PATH.format(obra_id), json=payload(), headers=headers)

    assert response.status_code == 201
    body = response.get_json()
    assert body["estado"] == "a iniciar"
    assert body["obra_id"] == str(obra_id)
    assert response.headers["Location"] == f"{PATH.format(obra_id)}/{body['id']}"
    saved = database.tbl_marcos.find_one({"_id": ObjectId(body["id"])})
    assert saved["obra_id"] == obra_id
    assert saved["estado"] == "a iniciar"
    assert saved["nome"] == "Fundação"
    assert database.tbl_marcos.count_documents({}) == 1


def test_ct19_dados_invalidos_nao_criam_marco(client, headers, database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    invalidos = [
        {**payload(), "nome": "  "},
        {**payload(), "fim_previsto": "2030-01-31"},
        {**payload(), "inicio_previsto": "31/01/2030"},
        {campo: valor for campo, valor in payload().items() if campo != "descricao"},
    ]

    for dados in invalidos:
        before = snapshot(database)
        response = client.post(PATH.format(obra_id), json=dados, headers=headers)
        assert response.status_code == 422
        assert response.get_json()["mensagem"]
        assert snapshot(database) == before


def test_ct19_obra_inexistente_nao_cria_marco(client, headers, database):
    before = snapshot(database)

    response = client.post(
        PATH.format(ObjectId()), json=payload(), headers=headers
    )

    assert response.status_code == 404
    assert snapshot(database) == before
