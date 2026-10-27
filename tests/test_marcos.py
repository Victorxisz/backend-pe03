"""CT-18/19: cadastro de marcos e validações sem gravação parcial."""

from bson import ObjectId
import pytest
from pymongo.errors import PyMongoError

from support import snapshot


PATH = "/obras/{}/marcos"


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


def test_lista_marcos_da_obra_ordenados_sem_incluir_outra_obra(
    client, headers, database, obra
):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    outra_obra_id = database.tbl_obras.insert_one({**obra, "_id": ObjectId()}).inserted_id
    cadastrados = []
    for nome in ("Fundação", "Alvenaria", "Estrutura", "Estrutura"):
        resposta = client.post(
            PATH.format(obra_id), json={**payload(), "nome": nome}, headers=headers
        )
        assert resposta.status_code == 201
        cadastrados.append(resposta.get_json())
    resposta = client.post(PATH.format(outra_obra_id), json=payload(), headers=headers)
    assert resposta.status_code == 201
    antes = snapshot(database)

    resposta = client.get(PATH.format(obra_id), headers=headers)

    assert resposta.status_code == 200
    assert resposta.get_json() == [
        {campo: marco[campo] for campo in ("id", "nome", "estado")}
        for marco in sorted(cadastrados, key=lambda item: (item["nome"], item["id"]))
    ]
    assert snapshot(database) == antes


def test_lista_vazia_para_obra_sem_marcos(client, headers, database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    antes = snapshot(database)

    resposta = client.get(PATH.format(obra_id), headers=headers)

    assert resposta.status_code == 200
    assert resposta.get_json() == []
    assert snapshot(database) == antes


@pytest.mark.parametrize("obra_id,status", [("id-invalido", 400), (str(ObjectId()), 404)])
def test_listagem_rejeita_obra_invalida_ou_inexistente(
    client, headers, database, obra_id, status
):
    antes = snapshot(database)
    resposta = client.get(PATH.format(obra_id), headers=headers)

    assert resposta.status_code == status
    assert resposta.get_json()["mensagem"]
    assert resposta.get_json()["campos"] == ["obra_id"]
    assert snapshot(database) == antes


def test_listagem_exige_autenticacao(client, database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    antes = snapshot(database)

    resposta = client.get(PATH.format(obra_id))

    assert resposta.status_code == 401
    assert snapshot(database) == antes


def test_listagem_trata_falha_de_banco(client, headers, database, obra, monkeypatch):
    from app.marcos import repository

    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    antes = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    monkeypatch.setattr(repository, "buscar_marcos_da_obra", falhar)
    resposta = client.get(PATH.format(obra_id), headers=headers)

    assert resposta.status_code == 500
    assert resposta.get_json()["mensagem"]
    assert "detalhe interno simulado" not in resposta.get_data(as_text=True)
    assert snapshot(database) == antes
