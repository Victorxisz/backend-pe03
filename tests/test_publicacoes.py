"""UC-10: HTTP, persistência e recuperação de mídias; só a rede é simulada."""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import Mock
from contextlib import nullcontext

import pytest
from bson import ObjectId
from cloudinary.exceptions import NotFound
from flask_jwt_extended import decode_token
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot


@pytest.fixture(autouse=True)
def transacao_local(app, database, monkeypatch, request):
    """Memória simula rollback; --atlas usa a sessão e a transação reais."""
    if request.config.getoption("--atlas"):
        return
    import db
    from mongomock.collection import Collection

    class Sessao:
        def with_transaction(self, gravar):
            antes = snapshot(database)
            try:
                return gravar(self)
            except Exception:
                for nome in database.list_collection_names():
                    database[nome].delete_many({})
                for nome, documentos in antes.items():
                    database[nome].insert_many(documentos)
                raise

    monkeypatch.setattr(db.cliente_mongo, "start_session", lambda: nullcontext(Sessao()))
    def sem_sessao(original):
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return original(*args, **kwargs)
        return executar
    for nome in ("find_one_and_update", "update_one", "find", "insert_one"):
        monkeypatch.setattr(Collection, nome, sem_sessao(getattr(Collection, nome)))


@pytest.fixture
def cenario(app, database, account, monkeypatch):
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": "teste", "CLOUDINARY_API_KEY": "teste",
                         "CLOUDINARY_API_SECRET": "segredo-ficticio", "CLOUDINARY_FOLDER": "pe03/evidencias"}.items():
        monkeypatch.setenv(chave, valor)
    obra = ObjectId()
    marco = ObjectId()
    avanco = ObjectId()
    midia = ObjectId()
    database.tbl_obras.insert_one({"_id": obra, "nome": "Casa teste"})
    database.tbl_marcos.insert_one({"_id": marco, "obra_id": obra, "nome": "Fundação"})
    database.tbl_avancos.insert_one({"_id": avanco, "marco_id": marco, "data": "2030-10-19",
                                    "descricao": "Fundação concretada", "estado": "rascunho"})
    referencia = {"provedor": "cloudinary", "public_id": "pe03/evidencias/" + "a" * 32,
                  "resource_type": "image", "delivery_type": "authenticated", "formato": "png"}
    database.tbl_midias.insert_one({"_id": midia, "avanco_id": avanco, "tipo": "foto",
                                   "nome": "fundacao.png", "mime": "image/png", "tamanho": 3,
                                   "referencia_externa": referencia})
    resource = Mock(return_value={"public_id": referencia["public_id"]})
    download = Mock(side_effect=lambda *args, **kwargs: BytesIO(b"png"))
    monkeypatch.setattr("cloudinary.api.resource", resource)
    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", download)
    monkeypatch.setattr("urllib.request.urlopen", download)
    return {"obra": obra, "marco": marco, "avanco": avanco, "midia": midia,
            "resource": resource, "download": download,
            "publicar": f"/avancos/{avanco}/publicacoes", "previa": f"/obras/{obra}/previa"}


def test_ct41_publicacao_com_autoria_midia_e_contexto(client, headers, account, database, cenario):
    r = client.post(cenario["publicar"], headers=headers, json={})
    assert r.status_code == 201
    p = r.get_json()
    assert p["autor"] == str(account["_id"])
    assert datetime.fromisoformat(p["instante"]) == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert p["marco"] == {"id": str(cenario["marco"]), "nome": "Fundação"}
    assert p["midias"][0]["conteudo"] == f"/midias/{cenario['midia']}/conteudo"
    assert "public_id" not in r.get_data(as_text=True)
    assert "referencia_externa" not in r.get_data(as_text=True)
    assert client.get(r.headers["Location"], headers=headers).json == {"publicacoes": [p]}
    assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": [p]}
    assert client.get(p["midias"][0]["conteudo"], headers=headers).data == b"png"
    saved = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    assert saved["estado"] == "publicado" and saved["publicacao"]["autor"] == p["autor"]
    assert r.headers["Cache-Control"] == "private, no-store"


def test_ct42_previa_nao_expoe_rascunhos_nem_outras_obras(client, headers, database, cenario):
    assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": []}
    assert client.get(cenario["publicar"], headers=headers).json == {"publicacoes": []}
    assert client.post(cenario["publicar"], headers=headers).status_code == 201
    publicado = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    outro_marco = ObjectId()
    database.tbl_marcos.insert_one({"_id": outro_marco, "obra_id": ObjectId()})
    for marco, estado in [(cenario["marco"], "rascunho"), (outro_marco, "publicado")]:
        database.tbl_avancos.insert_one({**publicado, "_id": ObjectId(), "marco_id": marco, "estado": estado})
    assert len(client.get(cenario["previa"], headers=headers).json["atualizacoes"]) == 1


@pytest.mark.parametrize("falha,status", [("ausente", 422), ("rede", 503), ("tamanho", 503)])
def test_ct43_midia_irrecuperavel_nao_publica(client, headers, database, cenario, falha, status):
    if falha == "ausente":
        cenario["resource"].side_effect = NotFound("ausente")
    elif falha == "rede":
        cenario["download"].side_effect = OSError("detalhe interno secreto")
    else:
        cenario["download"].side_effect = lambda *a, **kw: BytesIO(b"x")
    antes = snapshot(database)
    r = client.post(cenario["publicar"], headers=headers)
    assert r.status_code == status
    assert "secreto" not in r.get_data(as_text=True)
    assert snapshot(database) == antes
    assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": []}


@pytest.mark.parametrize("campo,valor", [("descricao", " "), ("descricao", None),
                                        ("data", "2030-02-30"), ("data", None),
                                        ("data", "20301019"), ("marco_id", "invalido")])
def test_rascunho_incompleto(client, headers, database, cenario, campo, valor):
    database.tbl_avancos.update_one({"_id": cenario["avanco"]}, {"$set": {campo: valor}})
    antes = snapshot(database)
    r = client.post(cenario["publicar"], headers=headers)
    assert r.status_code == 422 and campo in r.json["campos"]
    assert snapshot(database) == antes
    cenario["resource"].assert_not_called()


def test_ct44_repeticao_preserva_fato_original(client, headers, database, cenario):
    primeiro = client.post(cenario["publicar"], headers=headers)
    antes = snapshot(database)
    cenario["resource"].reset_mock()
    cenario["resource"].side_effect = RuntimeError("não deve consultar novamente")
    segundo = client.post(cenario["publicar"], headers=headers)
    assert segundo.status_code == 200 and segundo.json == primeiro.json
    assert snapshot(database) == antes
    assert database.tbl_avancos.count_documents({"publicacao": {"$exists": True}}) == 1
    cenario["resource"].assert_not_called()


@pytest.mark.parametrize("campo", ["tipo", "mime"])
@pytest.mark.parametrize("valor", [[], {}])
def test_midia_malformada_retorna_422(client, headers, database, cenario, campo, valor):
    database.tbl_midias.update_one({"_id": cenario["midia"]}, {"$set": {campo: valor}})
    antes = snapshot(database)
    resposta = client.post(cenario["publicar"], headers=headers)
    assert resposta.status_code == 422 and resposta.json["campos"] == ["midias"]
    assert snapshot(database) == antes
    cenario["resource"].assert_not_called()


@pytest.mark.parametrize("alvo", ["obras", "marcos", "midias"])
def test_exclusao_antes_da_gravacao_aborta_publicacao(client, headers, database, cenario, monkeypatch, alvo):
    from app.mudanças.ocorrencias.historico import repository
    original = repository.publicar
    def excluir_e_publicar(*args):
        database["tbl_" + alvo].delete_many({})
        return original(*args)
    monkeypatch.setattr(repository, "publicar", excluir_e_publicar)
    resposta = client.post(cenario["publicar"], headers=headers)
    assert resposta.status_code == 409
    salvo = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    assert salvo["estado"] == "rascunho" and "publicacao" not in salvo
    if alvo != "obras":
        assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": []}


def test_falha_na_transacao_preserva_rascunho(client, headers, database, cenario, monkeypatch):
    def falhar(*args, **kwargs):
        raise PyMongoError("Falha simulada após atualizar o avanço")
    monkeypatch.setattr(database.tbl_midias, "update_one", falhar)
    antes = snapshot(database)
    assert client.post(cenario["publicar"], headers=headers).status_code == 503
    assert snapshot(database) == antes


@pytest.mark.parametrize("metodo,rota", [("post", "publicar"), ("get", "publicar"), ("get", "previa")])
@pytest.mark.parametrize("sessao", ["ausente", "expirada", "revogada", "inativa"])
def test_rotas_exigem_sessao(app, client, headers, emitir_headers, account, database, cenario, metodo, rota, sessao):
    auth = headers
    if sessao == "ausente":
        auth = {}
    elif sessao == "expirada":
        auth = emitir_headers(expirado=True)
    elif sessao == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    else:
        with app.app_context():
            claims = decode_token(headers["Authorization"].split()[1])
        database.tbl_sessoes_revogadas.insert_one({"_id": claims["sessao_id"]})
    antes = snapshot(database)
    assert getattr(client, metodo)(cenario[rota], headers=auth).status_code == 401
    assert snapshot(database) == antes
    cenario["resource"].assert_not_called()


def test_ct45_nova_instancia_mantem_previa_e_midia(client, headers, database, cenario):
    publicado = client.post(cenario["publicar"], headers=headers).json
    with isolated_app(database) as nova_app:
        novo_client = nova_app.test_client()
        r = novo_client.get(cenario["previa"], headers=headers)
        assert r.status_code == 200 and r.json == {"atualizacoes": [publicado]}
        midia = novo_client.get(publicado["midias"][0]["conteudo"], headers=headers)
        assert midia.status_code == 200 and midia.data == b"png"


@pytest.mark.parametrize("campo,valor", [
    ("resource_type", []), ("resource_type", {}),
    ("resource_type", None), ("resource_type", "desconhecido"),
    ("resource_type", "video"), ("public_id", ""),
    ("provedor", "outro"), ("delivery_type", "upload"),
])
def test_referencia_invalida_nao_publica(
    client, headers, database, cenario, campo, valor
):
    database.tbl_midias.update_one(
        {"_id": cenario["midia"]},
        {"$set": {f"referencia_externa.{campo}": valor}},
    )
    antes = snapshot(database)

    resposta = client.post(cenario["publicar"], headers=headers)

    assert resposta.status_code == 422
    assert resposta.json["campos"] == ["midias"]
    assert snapshot(database) == antes
    cenario["resource"].assert_not_called()
    cenario["download"].assert_not_called()


@pytest.mark.parametrize("campo,valor", [
    ("nome", " "), ("nome", None),
    ("tamanho", 0), ("tamanho", True),
])
def test_metadados_invalidos_nao_publicam(
    client, headers, database, cenario, campo, valor
):
    database.tbl_midias.update_one(
        {"_id": cenario["midia"]}, {"$set": {campo: valor}},
    )
    antes = snapshot(database)

    resposta = client.post(cenario["publicar"], headers=headers)

    assert resposta.status_code == 422
    assert resposta.json["campos"] == ["midias"]
    assert snapshot(database) == antes
    cenario["resource"].assert_not_called()


@pytest.mark.parametrize("alteracao", ["adicionar", "remover", "alterar"])
def test_mudanca_de_midia_apos_validacao_aborta_publicacao(
    client, headers, database, cenario, monkeypatch, alteracao
):
    """Intercala uma edição após a última consulta do serviço, antes da transação."""
    from app.mudanças.ocorrencias.historico import repository

    original = repository.publicar
    esperado = {}

    def modificar_e_publicar(*args):
        if alteracao == "adicionar":
            nova = database.tbl_midias.find_one({"_id": cenario["midia"]})
            nova["_id"] = ObjectId()
            database.tbl_midias.insert_one(nova)
        elif alteracao == "remover":
            database.tbl_midias.delete_one({"_id": cenario["midia"]})
        else:
            database.tbl_midias.update_one(
                {"_id": cenario["midia"]}, {"$set": {"nome": "alterada.png"}},
            )
        esperado.update(snapshot(database))
        return original(*args)

    monkeypatch.setattr(repository, "publicar", modificar_e_publicar)

    resposta = client.post(cenario["publicar"], headers=headers)

    assert resposta.status_code == 409
    # A publicação é desfeita, mas a edição anterior à transação permanece.
    assert snapshot(database) == esperado
    assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": []}


@pytest.mark.parametrize("revisao", [None, 0, 4])
def test_publicacao_incrementa_revisao_e_repeticao_nao_incrementa(
    client, headers, database, cenario, revisao
):
    # None representa o registro legado sem campo revisao.
    if revisao is not None:
        database.tbl_avancos.update_one(
            {"_id": cenario["avanco"]}, {"$set": {"revisao": revisao}},
        )

    primeira = client.post(cenario["publicar"], headers=headers)
    assert primeira.status_code == 201
    salvo = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    assert salvo["revisao"] == (0 if revisao is None else revisao) + 1
    antes = snapshot(database)

    segunda = client.post(cenario["publicar"], headers=headers)

    assert segunda.status_code == 200
    assert segunda.json == primeira.json
    assert snapshot(database) == antes


def test_edicao_registrada_apos_validacao_impede_publicacao(
    client, headers, database, cenario, monkeypatch
):
    import db
    from app.avancos.revisoes import registrar_alteracao
    from app.mudanças.ocorrencias.historico import repository

    original = repository.publicar
    esperado = {}

    def editar_e_publicar(documento, *args):
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(
                lambda transacao: registrar_alteracao(documento, transacao)
            )
        esperado.update(snapshot(database))
        return original(documento, *args)

    monkeypatch.setattr(repository, "publicar", editar_e_publicar)

    resposta = client.post(cenario["publicar"], headers=headers)

    assert resposta.status_code == 409
    assert snapshot(database) == esperado
    assert client.get(cenario["previa"], headers=headers).json == {"atualizacoes": []}


@pytest.mark.parametrize("revisao", [None, 0, 4])
def test_edicao_incrementa_revisao_e_recusa_documento_desatualizado(
    app, database, cenario, revisao
):
    import db
    from app.avancos.revisoes import ConflitoRascunho, registrar_alteracao

    if revisao is not None:
        database.tbl_avancos.update_one(
            {"_id": cenario["avanco"]}, {"$set": {"revisao": revisao}},
        )
    documento = database.tbl_avancos.find_one({"_id": cenario["avanco"]})

    def editar():
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(
                lambda transacao: registrar_alteracao(documento, transacao)
            )

    editar()
    salvo = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    assert salvo["revisao"] == (0 if revisao is None else revisao) + 1
    antes = snapshot(database)

    with pytest.raises(ConflitoRascunho):
        editar()
    assert snapshot(database) == antes


@pytest.mark.parametrize("revisao", [-1, True, "1", None])
def test_revisao_malformada_aborta_publicacao(
    client, headers, database, cenario, revisao
):
    database.tbl_avancos.update_one(
        {"_id": cenario["avanco"]}, {"$set": {"revisao": revisao}},
    )
    antes = snapshot(database)

    resposta = client.post(cenario["publicar"], headers=headers)

    assert resposta.status_code == 409
    assert snapshot(database) == antes


def test_edicao_nao_modifica_avanco_ja_publicado(client, headers, database, cenario):
    import db
    from app.avancos.revisoes import ConflitoRascunho, registrar_alteracao

    assert client.post(cenario["publicar"], headers=headers).status_code == 201
    documento = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    antes = snapshot(database)

    with pytest.raises(ConflitoRascunho):
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(
                lambda transacao: registrar_alteracao(documento, transacao)
            )

    assert snapshot(database) == antes


def test_falha_apos_incremento_desfaz_revisao_e_insercao_de_midia(app, database, cenario):
    import db
    from app.avancos.revisoes import registrar_alteracao

    documento = database.tbl_avancos.find_one({"_id": cenario["avanco"]})
    antes = snapshot(database)

    def editar_e_falhar(sessao):
        registrar_alteracao(documento, sessao)
        nova = database.tbl_midias.find_one({"_id": cenario["midia"]}, session=sessao)
        nova["_id"] = ObjectId()
        database.tbl_midias.insert_one(nova, session=sessao)
        raise RuntimeError("Falha simulada após a edição")

    with pytest.raises(RuntimeError, match="Falha simulada"):
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(editar_e_falhar)

    assert snapshot(database) == antes


@pytest.mark.atlas
def test_ct45_previa_persistida_apos_novo_processo(client, headers, database, cenario):
    """Atlas real e processo novo; a rede de mídia continua simulada neste teste."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    publicado = client.post(cenario["publicar"], headers=headers)
    assert publicado.status_code == 201
    env = dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo,
               TEST_RESOURCE_PATH=cenario["previa"])
    resultado = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("restart_probe.py"))],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0, "Falha ao consultar a prévia em processo novo"
    assert json.loads(resultado.stdout) == {
        "status": 200, "body": {"atualizacoes": [publicado.json]},
    }
