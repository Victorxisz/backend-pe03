"""Correções e versões por HTTP; banco em memória e armazenamento simulado."""
from datetime import datetime

from bson import ObjectId
import pytest

from support import snapshot
from support_midias import config, conteudos
from test_avancos_uc09 import backend, transacao_local


def semear_publicacao(database, **campos):
    """Documento mínimo publicado; os testes alteram só a condição examinada."""
    conteudo = {"data": "2030-01-01", "descricao": "Texto original", "midias": []}
    documento = {"_id": ObjectId(), "estado": "publicado", "autor": "autor-original",
                 "revisao": 1, **conteudo,
                 "publicacao": {**conteudo, "autor": "publicador", "instante": datetime(2030, 1, 2)},
                 **campos}
    database.tbl_avancos.insert_one(documento)
    return documento


@pytest.mark.parametrize("campo,valor", [
    ("publicacao", None), ("publicacao", {}),
    ("publicacao", {"data": "2030-01-01", "descricao": ["texto"], "midias": []}),
    ("correcoes", [{"antes": {}, "depois": {}}]),
    ("correcoes", [False]),
])
def test_historia_malformada_retorna_conflito_sem_inventar_versoes(client, headers, database, campo, valor):
    documento = semear_publicacao(database, **{campo: valor})
    antes = snapshot(database)
    resposta = client.get(f"/avancos/{documento['_id']}/versoes", headers=headers)
    assert resposta.status_code == 409
    assert resposta.json["codigo"] == "HISTORICO_INDISPONIVEL"
    assert snapshot(database) == antes


@pytest.mark.parametrize("vinculo", ["removida", "outra_publicacao"])
def test_referencia_historica_sem_midia_retida_nao_oferece_link(client, headers, database, vinculo):
    midia_id = ObjectId()
    midia = {"id": str(midia_id), "nome": "original.png", "conteudo": f"/midias/{midia_id}/conteudo"}
    documento = semear_publicacao(database, midias=[midia])
    database.tbl_avancos.update_one({"_id": documento["_id"]}, {"$set": {"publicacao.midias": [midia]}})
    if vinculo == "outra_publicacao":
        database.tbl_midias.insert_one({"_id": midia_id, "avanco_id": ObjectId()})
    antes = snapshot(database)
    resposta = client.get(f"/avancos/{documento['_id']}/versoes", headers=headers)
    assert resposta.status_code == 200
    historica = resposta.json["versoes"][0]["conteudo"]["midias"][0]
    assert historica["id"] == str(midia_id) and historica["nome"] == "original.png"
    assert historica["retida"] is False and historica["conteudo"] is None
    assert snapshot(database) == antes


def test_ids_bson_em_autoria_e_midia_sao_serializados(client, headers, database):
    autor, midia_id = ObjectId(), ObjectId()
    midia = {"id": midia_id, "nome": "original.png", "conteudo": "https://endereco.example/antigo"}
    documento = semear_publicacao(database, autor=autor, midias=[midia])
    database.tbl_avancos.update_one({"_id": documento["_id"]}, {"$set": {"publicacao.midias": [midia]}})
    database.tbl_midias.insert_one({"_id": midia_id, "avanco_id": documento["_id"]})
    resposta = client.get(f"/avancos/{documento['_id']}/versoes", headers=headers)
    assert resposta.status_code == 200
    versao = resposta.json["versoes"][0]
    assert versao["autor_original"] == str(autor)
    assert versao["conteudo"]["midias"][0]["conteudo"] == f"/midias/{midia_id}/conteudo"
    assert versao["conteudo"]["midias"][0]["retida"] is True


@pytest.mark.parametrize("revisao", [True, -1, "1", None])
def test_correcao_rejeita_revisao_invalida_sem_alterar_registros(client, headers, database, transacao_local, revisao):
    documento = semear_publicacao(database, revisao=revisao)
    antes = snapshot(database)
    resposta = client.patch(f"/avancos/{documento['_id']}", headers=headers,
                             json={"descricao": "Corrigida", "motivo": "Ajuste"})
    assert resposta.status_code == 409
    assert snapshot(database) == antes


def test_correcao_com_upload_sem_configuracao_retorna_indisponibilidade(client, headers, database, monkeypatch, conteudos):
    from io import BytesIO
    for chave in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.delenv(chave, raising=False)
    documento = semear_publicacao(database)
    antes = snapshot(database)
    resposta = client.patch(f"/avancos/{documento['_id']}", headers=headers,
                             content_type="multipart/form-data",
                             data={"motivo": "Foto atualizada", "midias": (BytesIO(conteudos["png"]), "foto.png")})
    assert resposta.status_code == 503
    assert snapshot(database) == antes


def test_correcao_com_midia_preserva_consultas_publicacao_e_autoria(
    client, headers, account, database, backend, transacao_local, conteudos
):
    """Exercita os consumidores HTTP após duas correções reais no serviço."""
    from copy import deepcopy
    from io import BytesIO
    obra_id, marco_id = ObjectId(), ObjectId()
    database.tbl_obras.insert_one({"_id": obra_id})
    database.tbl_marcos.insert_one({"_id": marco_id, "obra_id": obra_id, "nome": "Estrutura"})
    documento = semear_publicacao(database, marco_id=marco_id, origem_simulada={"perfil": "engenheiro", "nome": "Engenheira exemplo"},
                                  data_registro=datetime(2030, 1, 1))
    documento["publicacao"]["marco"] = {"id": marco_id, "nome": "Estrutura"}
    database.tbl_avancos.update_one({"_id": documento["_id"]}, {"$set": {"publicacao": documento["publicacao"]}})
    original = deepcopy(documento["publicacao"])
    rota = f"/avancos/{documento['_id']}"
    primeira = client.patch(rota, headers=headers, content_type="multipart/form-data",
                            data={"motivo": "Foto anexada", "midias": (BytesIO(conteudos["png"]), "foto.png")})
    segunda = client.patch(rota, headers=headers, json={"motivo": "Texto ajustado", "descricao": "Texto corrigido"})
    assert primeira.status_code == segunda.status_code == 200
    versoes = client.get(rota + "/versoes", headers=headers).json["versoes"]
    assert len(versoes) == 3 and [item["atual"] for item in versoes] == [False, False, True]
    assert versoes[-1]["autor_original"] == "autor-original"
    assert versoes[-1]["origem_simulada"] == documento["origem_simulada"]
    assert all(item["correcao"]["autor"] == str(account["_id"]) for item in versoes[1:])
    salvo = database.tbl_avancos.find_one({"_id": documento["_id"]})
    assert salvo["publicacao"] == original
    assert "retida" not in salvo["midias"][0]
    assert all("retida" not in midia for correcao in salvo["correcoes"]
               for lado in ("antes", "depois") for midia in correcao[lado]["midias"])
    antes = snapshot(database)
    detalhe = client.get(rota, headers=headers)
    lista = client.get(f"/marcos/{marco_id}/avancos", headers=headers)
    publicacoes = client.get(rota + "/publicacoes", headers=headers)
    previa = client.get(f"/obras/{obra_id}/previa", headers=headers)
    repetida = client.post(rota + "/publicacoes", headers=headers)
    for resposta in (detalhe, lista, publicacoes, previa, repetida):
        assert resposta.status_code == 200, resposta.get_data(as_text=True)
    for item in (detalhe.json, lista.json[0], publicacoes.json["publicacoes"][0], previa.json["atualizacoes"][0], repetida.json):
        assert item["descricao"] == "Texto corrigido"
        assert item["midias"][0]["id"] == versoes[-1]["conteudo"]["midias"][0]["id"]
    assert previa.json["atualizacoes"][0]["editado"] is True
    midia = versoes[-1]["conteudo"]["midias"][0]
    assert client.get(midia["conteudo"], headers=headers).data == conteudos["png"]
    assert client.delete(rota, headers=headers).status_code == 409
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_correcao_real_preserva_cadeia_e_reverte_falha_no_banco(client, headers, database, monkeypatch):
    """A falha é injetada após o UPDATE, ainda dentro da transação real."""
    from pymongo.errors import PyMongoError
    documento = semear_publicacao(database)
    rota = f"/avancos/{documento['_id']}"
    for descricao in ("Primeira correção", "Segunda correção"):
        resposta = client.patch(rota, headers=headers, json={"motivo": "Revisão", "descricao": descricao})
        assert resposta.status_code == 200
    antes = snapshot(database)
    consulta = client.get(rota + "/versoes", headers=headers)
    assert [item["conteudo"]["descricao"] for item in consulta.json["versoes"]] == [
        "Texto original", "Primeira correção", "Segunda correção"
    ]
    from pymongo.collection import Collection
    atualizar = Collection.update_one
    chamadas = []

    def falhar_apos_atualizar(colecao, *args, **kwargs):
        resultado = atualizar(colecao, *args, **kwargs)
        if colecao.name != database.tbl_avancos.name:
            return resultado
        assert kwargs["session"] is not None
        salvo = database.tbl_avancos.find_one({"_id": documento["_id"]}, session=kwargs["session"])
        assert salvo["descricao"] == "Não deve persistir" and len(salvo["correcoes"]) == 3
        chamadas.append(True)
        raise PyMongoError("falha simulada após a escrita")

    monkeypatch.setattr(Collection, "update_one", falhar_apos_atualizar)
    resposta = client.patch(rota, headers=headers, json={"motivo": "Revisão", "descricao": "Não deve persistir"})
    assert resposta.status_code == 503 and chamadas == [True]
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_correcao_concorrente_nao_sobrescreve_historico(client, headers, database, monkeypatch):
    from app.avancos import repository
    documento = semear_publicacao(database)
    salvar = repository.salvar_correcao_publicada

    def gravar_apos_concorrencia(*args, **kwargs):
        database.tbl_avancos.update_one({"_id": documento["_id"]}, {"$inc": {"revisao": 1}})
        return salvar(*args, **kwargs)

    monkeypatch.setattr(repository, "salvar_correcao_publicada", gravar_apos_concorrencia)
    resposta = client.patch(f"/avancos/{documento['_id']}", headers=headers,
                             json={"motivo": "Revisão", "descricao": "Não deve persistir"})
    assert resposta.status_code == 409
    salvo = database.tbl_avancos.find_one({"_id": documento["_id"]})
    assert salvo["descricao"] == "Texto original" and "correcoes" not in salvo


@pytest.mark.atlas
def test_rollback_real_tambem_remove_novas_midias_e_compensa_upload(
    client, headers, database, monkeypatch, backend, conteudos
):
    from io import BytesIO
    from pymongo.collection import Collection
    from pymongo.errors import PyMongoError
    documento = semear_publicacao(database)
    antes = snapshot(database)
    atualizar = Collection.update_one
    chamadas = []

    def falhar_apos_atualizar(colecao, *args, **kwargs):
        resultado = atualizar(colecao, *args, **kwargs)
        if colecao.name != database.tbl_avancos.name:
            return resultado
        sessao = kwargs["session"]
        assert database.tbl_midias.count_documents({"avanco_id": documento["_id"]}, session=sessao) == 1
        salvo = database.tbl_avancos.find_one({"_id": documento["_id"]}, session=sessao)
        assert len(salvo["correcoes"]) == 1 and salvo["descricao"] == "Texto corrigido"
        chamadas.append(True)
        raise PyMongoError("falha simulada após registrar a nova mídia e a correção")

    monkeypatch.setattr(Collection, "update_one", falhar_apos_atualizar)
    resposta = client.patch(f"/avancos/{documento['_id']}", headers=headers,
                             content_type="multipart/form-data", data={
                                 "descricao": "Texto corrigido", "motivo": "Foto atualizada",
                                 "midias": (BytesIO(conteudos["png"]), "foto.png"),
                             })
    assert resposta.status_code == 503 and chamadas == [True]
    assert snapshot(database) == antes
    assert backend[0] == {}


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
    esperados = [{**conteudo, "midias": [{**midia, "retida": False, "conteudo": None}
                                       for midia in conteudo["midias"]]}
                 for conteudo in (primeira, segunda, terceira)]
    assert [v["conteudo"] for v in versoes] == esperados
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
