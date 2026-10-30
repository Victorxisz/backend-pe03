"""CT-31 a CT-36: registro e consulta de avanços em rascunho."""

from io import BytesIO
from unittest.mock import patch

import pytest
from bson import ObjectId


class ServicoMidiasFalso:
    def executar_com_midias(self, arquivos, salvar):
        assert arquivos
        return salvar([{
            "tipo": "foto", "nome": "evidencia.png", "tamanho": 4,
            "mime": "image/png", "referencia_externa": {
                "provedor": "falso", "public_id": "privado"
            },
        }])


@pytest.fixture
def marco(database):
    identifier = ObjectId()
    database.tbl_marcos.insert_one({"_id": identifier, "nome": "Fundação"})
    return str(identifier)


def enviar(client, headers, marco_id, data="2030-02-01", descricao="Concretagem"):
    return client.post(
        f"/marcos/{marco_id}/avancos", headers=headers,
        data={"data": data, "descricao": descricao,
              "midias": (BytesIO(b"test"), "evidencia.png")},
        content_type="multipart/form-data",
    )


def test_ct31_registra_rascunho_com_midia_sem_expor_referencia(
    client, headers, database, marco
):
    with patch("app.avancos.service.ServicoMidias", return_value=ServicoMidiasFalso()):
        response = enviar(client, headers, marco)
    assert response.status_code == 201
    body = response.get_json()
    assert body["estado"] == "rascunho"
    assert body["data"] == "2030-02-01"
    assert body["midias"] == [{"tipo": "foto", "nome": "evidencia.png",
                               "tamanho": 4, "mime": "image/png"}]
    assert "referencia_externa" not in response.get_data(as_text=True)
    salvo = database.tbl_avancos.find_one({"_id": ObjectId(body["id"])})
    assert salvo["marco_id"] == ObjectId(marco)
    assert salvo["estado"] == "rascunho"
    assert salvo["autor"]
    assert salvo["data_registro"].tzinfo is not None
    assert salvo["midias"][0]["referencia_externa"]["public_id"] == "privado"


@pytest.mark.parametrize("data,descricao", [("2030-02-30", "texto"), ("2030-02-01", " ")])
def test_ct32_campos_invalidos_nao_registram_avanco(
    client, headers, database, marco, data, descricao
):
    response = enviar(client, headers, marco, data, descricao)
    assert response.status_code == 422
    assert database.tbl_avancos.count_documents({}) == 0


def test_ct36_aceita_dias_nao_consecutivos_e_consultas(
    client, headers, database, marco
):
    with patch("app.avancos.service.ServicoMidias", return_value=ServicoMidiasFalso()):
        primeiro = enviar(client, headers, marco, "2030-02-01").get_json()
        segundo = enviar(client, headers, marco, "2030-02-17").get_json()
    assert primeiro["data"] != segundo["data"]
    assert client.get(f"/marcos/{marco}/avancos", headers=headers).get_json() == [primeiro, segundo]
    resposta = client.get(f"/avancos/{primeiro['id']}", headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json() == primeiro
