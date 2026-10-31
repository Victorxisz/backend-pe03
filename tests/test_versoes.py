"""Correções e versões por HTTP; banco em memória e armazenamento simulado."""
from datetime import datetime

from bson import ObjectId

from support import snapshot
from support_midias import config, conteudos
from test_avancos_uc09 import backend, transacao_local


def test_publicacao_sem_correcoes_retorna_snapshot_original(client, headers, database):
    # Preparação
    avanco = ObjectId()
    marco = ObjectId()
    documento = {"_id": avanco, "estado": "publicado", "autor": "autor-original",
                 "descricao": "Texto original", "data": "2030-01-01",
                 "publicacao": {"autor": "publicador", "instante": datetime(2030, 1, 2),
                                "descricao": "Texto original", "data": "2030-01-01",
                                "marco": {"id": marco, "nome": "Marco"}, "midias": []}}
    database.tbl_avancos.insert_one(documento)
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 200
    versao = resposta.json["versoes"][0]
    assert versao["numero"] == 1 and versao["atual"] is True
    assert versao["conteudo"]["descricao"] == "Texto original"
    assert versao["autor_original"] == "autor-original"
    assert versao["correcao"] is None
    assert snapshot(database) == antes


def test_avanco_inexistente_e_rascunho_sao_diferentes(client, headers, database):
    # Preparação
    avanco = database.tbl_avancos.insert_one({"estado": "rascunho"}).inserted_id

    # Execução
    inexistente = client.get(f"/avancos/{ObjectId()}/versoes", headers=headers)
    rascunho = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert inexistente.status_code == 404
    assert rascunho.status_code == 200 and rascunho.json["versoes"] == []


def test_publicacao_alterada_sem_historico_nao_inventa_versoes(client, headers, database):
    # Preparação
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "descricao": "alterado", "data": "2030-01-01",
        "publicacao": {"descricao": "original", "data": "2030-01-01", "midias": []},
    }).inserted_id
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 409
    assert resposta.json["codigo"] == "HISTORICO_INDISPONIVEL"
    assert snapshot(database) == antes


def test_consulta_exige_sessao(client):
    # Preparação e execução
    resposta = client.get(f"/avancos/{ObjectId()}/versoes")

    # Verificação
    assert resposta.status_code == 401


def test_ct46_ct47_ct50_ct51_cadeia_preexistente_continua_consultavel(client, headers, database):
    # Preparação: verifica a leitura de versões já persistidas.
    avanco = ObjectId()
    primeira = {"data": "2030-01-01", "descricao": "Parede branca", "midias": [{"id": "foto-1", "nome": "antes.png"}]}
    segunda = {"data": "2030-01-01", "descricao": "Parede azul", "midias": [{"id": "foto-1", "nome": "antes.png"}]}
    terceira = {"data": "2030-01-02", "descricao": "Parede azul", "midias": [{"id": "foto-2", "nome": "depois.png"}]}
    database.tbl_avancos.insert_one({"_id": avanco, "estado": "publicado", "autor": "autor inicial",
        "origem_simulada": True, **terceira,
        "publicacao": {**primeira, "autor": "publicador", "instante": datetime(2030, 1, 1)},
        "correcoes": [{"antes": primeira, "depois": segunda, "autor": "corretor 1", "motivo": "Cor", "instante": datetime(2030, 1, 2)},
                      {"antes": segunda, "depois": terceira, "autor": "corretor 2", "motivo": "Foto", "instante": datetime(2030, 1, 3)}]})
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 200
    versoes = resposta.json["versoes"]
    assert [v["numero"] for v in versoes] == [1, 2, 3]
    assert [v["atual"] for v in versoes] == [False, False, True]
    assert [v["conteudo"] for v in versoes] == [primeira, segunda, terceira]
    assert versoes[1]["correcao"]["autor"] == "corretor 1"
    assert versoes[2]["correcao"]["campos"] == ["data", "midias"]
    assert versoes[0]["origem_simulada"] is True
    trechos = versoes[1]["correcao"]["diferencas_texto"]
    assert "".join(t["antes"] for t in trechos) == primeira["descricao"]
    assert "".join(t["depois"] for t in trechos) == segunda["descricao"]
    assert snapshot(database) == antes


def test_duas_correcoes_http_persistem_e_mantem_cadeia(client, headers, database, monkeypatch):
    # Preparação: sessão do mongomock não implementa transações reais.
    from contextlib import nullcontext
    from mongomock.collection import Collection
    import db

    class Sessao:
        def with_transaction(self, callback):
            return callback(self)

    monkeypatch.setattr(db.cliente_mongo, "start_session", lambda: nullcontext(Sessao()))
    original = Collection.update_one

    def sem_sessao(self, *args, **kwargs):
        kwargs.pop("session", None)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Collection, "update_one", sem_sessao)
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "autor original", "origem_simulada": True,
        "data": "2030-01-01", "descricao": "Parede branca", "revisao": 1,
        "publicacao": {"autor": "publicador", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Parede branca", "midias": []},
    }).inserted_id

    # Execução
    primeira = client.patch(f"/avancos/{avanco}", json={"descricao": "Parede azul", "motivo": "Cor corrigida"}, headers=headers)
    segunda = client.patch(f"/avancos/{avanco}", json={"data": "2030-01-02", "motivo": "Data corrigida"}, headers=headers)
    consulta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert primeira.status_code == segunda.status_code == consulta.status_code == 200
    versoes = consulta.json["versoes"]
    assert [v["conteudo"]["descricao"] for v in versoes] == ["Parede branca", "Parede azul", "Parede azul"]
    assert [v["atual"] for v in versoes] == [False, False, True]
    assert database.tbl_avancos.find_one({"_id": avanco})["revisao"] == 3
    assert len(database.tbl_avancos.find_one({"_id": avanco})["correcoes"]) == 2


def test_correcao_http_com_nova_midia_e_conteudo_recuperavel(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    versoes = resposta.json["versoes"]
    assert len(versoes) == 2
    assert versoes[0]["conteudo"]["midias"] == []
    midia = versoes[1]["conteudo"]["midias"][0]
    assert client.get(midia["conteudo"], headers=headers).data == conteudos["png"]
    assert database.tbl_midias.count_documents({"avanco_id": avanco}) == 1


def test_falha_ao_gravar_correcao_remove_upload_e_nao_altera_publicacao(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    from pymongo.errors import PyMongoError
    from app.avancos import repository
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id
    antes = snapshot(database)
    monkeypatch.setattr(repository, "salvar_correcao_publicada", lambda *args: (_ for _ in ()).throw(PyMongoError("falha")))

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 503
    assert snapshot(database) == antes
    assert backend[0] == {}


def test_falha_na_compensacao_preserva_diario_para_reconciliacao(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    from pymongo.errors import PyMongoError
    from app.avancos import repository
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id
    antes = database.tbl_avancos.find_one({"_id": avanco})
    monkeypatch.setattr(repository, "salvar_correcao_publicada", lambda *args: (_ for _ in ()).throw(PyMongoError("falha")))
    backend[2].side_effect = RuntimeError("remoção indisponível")

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 503
    assert database.tbl_avancos.find_one({"_id": avanco}) == antes
    diario = database.tbl_uploads_pendentes.find_one({"avanco_id": avanco})
    assert diario["estado"] == "pendente" and diario["referencias"]
    assert diario["referencias"][0]["public_id"] in backend[0]


def test_midia_selecionada_indisponivel_recusa_correcao(
    client, headers, database, monkeypatch, backend, transacao_local
):
    # Preparação
    avanco = ObjectId()
    midia_id = ObjectId()
    referencia = {"provedor": "cloudinary", "public_id": "pe03/evidencias/" + "a" * 32,
                  "resource_type": "image", "delivery_type": "authenticated", "formato": "png"}
    midia = {"_id": midia_id, "avanco_id": avanco, "tipo": "foto", "nome": "ausente.png",
             "tamanho": 100, "mime": "image/png", "referencia_externa": referencia}
    database.tbl_midias.insert_one(midia)
    from app.avancos.acesso_midias import midia_para_dict
    publica = {"data": "2030-01-01", "descricao": "Antes", "midias": [midia_para_dict(midia)]}
    database.tbl_avancos.insert_one({"_id": avanco, "estado": "publicado", "autor": "original",
        "data": "2030-01-01", "descricao": "Antes", "revisao": 1,
        "publicacao": {**publica, "autor": "original", "instante": datetime(2030, 1, 1)}})
    from unittest.mock import Mock
    from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
    obter = Mock(side_effect=ErroArmazenamento("Arquivo ausente", 404))
    monkeypatch.setattr(ArmazenamentoCloudinary, "obter_conteudo", obter)
    antes = snapshot(database)

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        json={"motivo": "Troca", "midias_manter": [str(midia_id)], "descricao": "Depois"})

    # Verificação
    assert resposta.status_code == 422
    assert "midias_manter" in resposta.json["campos"]
    obter.assert_called_once_with(referencia, 100)
    assert snapshot(database) == antes
