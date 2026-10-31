"""CT-74 a CT-78: aceitação preservada e separada do estado do problema."""

from bson import ObjectId
import pytest


@pytest.fixture
def ocorrencia(database):
    documento = {"_id": ObjectId(), "estado": "sem solução", "titulo": "Infiltração"}
    database.tbl_ocorrencias.insert_one(documento)
    return documento


def url(ocorrencia):
    return f"/ocorrencias/{ocorrencia['_id']}/aceitacoes"


def test_aceita_sem_medida_e_releitura_a_partir_do_banco(client, database, headers, account, ocorrencia):
    resposta = client.post(url(ocorrencia), json={"justificativa": "Limitação estrutural."}, headers=headers)
    assert resposta.status_code == 201
    item = resposta.get_json()
    assert item["justificativa"] == "Limitação estrutural."
    assert item["autor"] == str(account["_id"])
    assert item["data"]
    salvo = database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]})
    assert salvo["estado"] == "sem solução"
    assert client.get(url(ocorrencia), headers=headers).get_json() == [item]


def test_aceitacao_antiga_permanece_apos_mudanca_de_estado(client, database, headers, ocorrencia):
    assert client.post(url(ocorrencia), json={"justificativa": "Decisão."}, headers=headers).status_code == 201
    database.tbl_ocorrencias.update_one({"_id": ocorrencia["_id"]}, {"$set": {"estado": "resolvida"}})
    assert len(client.get(url(ocorrencia), headers=headers).get_json()) == 1
    database.tbl_ocorrencias.update_one({"_id": ocorrencia["_id"]}, {"$set": {"estado": "aberta"}})
    assert len(client.get(url(ocorrencia), headers=headers).get_json()) == 1


def test_justificativa_obrigatoria_nao_persiste(client, database, headers, ocorrencia):
    resposta = client.post(url(ocorrencia), json={"justificativa": "  "}, headers=headers)
    assert resposta.status_code == 422
    assert "aceitacoes" not in database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]})


@pytest.mark.parametrize("estado", ["aberta", "resolvida"])
def test_estado_incompativel_nao_persiste(client, database, headers, ocorrencia, estado):
    database.tbl_ocorrencias.update_one({"_id": ocorrencia["_id"]}, {"$set": {"estado": estado}})
    resposta = client.post(url(ocorrencia), json={"justificativa": "Decisão."}, headers=headers)
    assert resposta.status_code == 409
    assert "aceitacoes" not in database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]})


def test_medida_compensatoria_opcional_e_preservada(client, headers, ocorrencia):
    resposta = client.post(url(ocorrencia), json={
        "justificativa": "Não é possível corrigir agora.",
        "medida_compensatoria": "Inspeção trimestral.",
    }, headers=headers)
    assert resposta.status_code == 201
    assert resposta.get_json()["medida_compensatoria"] == "Inspeção trimestral."


def test_reenvio_com_mesma_chave_nao_duplica_e_chave_nova_preserva_historico(client, headers, ocorrencia):
    corpo = {"justificativa": "Decisão registrada."}
    cabecalhos = {**headers, "Idempotency-Key": "decisao-1"}
    primeira = client.post(url(ocorrencia), json=corpo, headers=cabecalhos)
    repetida = client.post(url(ocorrencia), json=corpo, headers=cabecalhos)
    assert primeira.status_code == 201
    assert repetida.status_code == 200
    assert repetida.get_json() == primeira.get_json()
    outra = client.post(url(ocorrencia), json=corpo,
                        headers={**headers, "Idempotency-Key": "decisao-2"})
    assert outra.status_code == 201
    assert len(client.get(url(ocorrencia), headers=headers).get_json()) == 2
