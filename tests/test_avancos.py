"""CT-31 a CT-36: registro e consulta de avanços em rascunho."""

from io import BytesIO
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError
from support import snapshot


@pytest.fixture(autouse=True)
def transacao_local(app, database, monkeypatch, request):
    """Memória simula rollback; Atlas usa sessões reais quando habilitado."""
    if request.config.getoption("--atlas"):
        return
    import db
    from mongomock.collection import Collection

    apagar, inserir = Collection.delete_many, Collection.insert_many

    class Sessao:
        def with_transaction(self, gravar):
            antes = snapshot(database)
            try:
                return gravar(self)
            except Exception:
                for nome in database.list_collection_names():
                    apagar(database[nome], {})
                for nome, documentos in antes.items():
                    inserir(database[nome], deepcopy(documentos))
                raise

    monkeypatch.setattr(db.cliente_mongo, "start_session", lambda: nullcontext(Sessao()))

    def sem_sessao(original):
        @wraps(original)
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return original(*args, **kwargs)
        return executar

    for nome in ("find", "find_one", "update_one", "insert_one", "insert_many", "find_one_and_update"):
        monkeypatch.setattr(Collection, nome, sem_sessao(getattr(Collection, nome)))


class ServicoMidiasFalso:
    def executar_com_midias(self, arquivos, salvar):
        assert arquivos
        return salvar([{
            "tipo": "foto", "nome": "evidencia.png", "tamanho": 4,
            "mime": "image/png", "referencia_externa": {
                "provedor": "cloudinary", "public_id": "privado",
                "resource_type": "image", "delivery_type": "authenticated",
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
    # BSON sem tz_aware é lido em UTC sem tzinfo; a resposta HTTP explicita o fuso.
    registro = datetime.fromisoformat(body["data_registro"].replace("Z", "+00:00"))
    assert registro == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert salvo["data_registro"].replace(tzinfo=timezone.utc) == registro
    midia = database.tbl_midias.find_one({"avanco_id": salvo["_id"]})
    assert midia["referencia_externa"]["public_id"] == "privado"
    assert "midias" not in salvo


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


def test_cadastro_e_publicacao_compartilham_as_mesmas_midias(client, headers, database, marco):
    obra_id = database.tbl_obras.insert_one({"nome": "Obra de teste"}).inserted_id
    database.tbl_marcos.update_one({"_id": ObjectId(marco)}, {"$set": {"obra_id": obra_id}})
    with patch("app.avancos.service.ServicoMidias", return_value=ServicoMidiasFalso()):
        cadastro = enviar(client, headers, marco)
    assert cadastro.status_code == 201
    avanco_id = cadastro.get_json()["id"]
    midias = client.get(f"/avancos/{avanco_id}/midias", headers=headers).get_json()["midias"]
    assert len(midias) == 1
    with patch("app.publicacoes.service.ArmazenamentoCloudinary") as armazenamento:
        armazenamento.return_value.obter_conteudo.return_value = b"test"
        publicacao = client.post(f"/avancos/{avanco_id}/publicacoes", headers=headers)
    assert publicacao.status_code == 201
    assert publicacao.get_json()["midias"][0]["id"] == midias[0]["id"]
    assert client.delete(f"/avancos/{avanco_id}", headers=headers).status_code == 409
    assert database.tbl_midias.count_documents({}) == 1


def test_falha_nas_midias_nao_deixa_avanco_sem_evidencias(client, headers, database, marco):
    antes = snapshot(database)
    with patch("app.avancos.service.ServicoMidias", return_value=ServicoMidiasFalso()), patch.object(
        database.tbl_midias, "insert_many", side_effect=PyMongoError("falha simulada")
    ):
        resposta = enviar(client, headers, marco)
    assert resposta.status_code == 503
    assert snapshot(database) == antes
