"""UC-16: CT-74 a CT-78, reenvio, concorrência, falhas e persistência."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from unittest.mock import patch

from bson import ObjectId
from pymongo.errors import AutoReconnect, WriteError
import pytest

from support import isolated_app, snapshot


@pytest.fixture
def cenario(client, headers, obra):
    cadastrada = client.post("/obras", headers=headers, json=obra)
    assert cadastrada.status_code == 201
    obra_id = cadastrada.json["id"]
    r = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers, json={
        "titulo": "Infiltração", "descricao": "Umidade na fachada", "estado": "sem solução"})
    assert r.status_code == 201
    return {"url": r.headers["Location"], "aceitacoes": r.headers["Location"] + "/aceitacoes",
            "item": r.json, "obra_id": obra_id}


def aceitar(client, headers, cenario, corpo=None, chave="decisao-1"):
    auth = dict(headers)
    if chave is not None:
        auth["Idempotency-Key"] = chave
    return client.post(cenario["aceitacoes"], headers=auth,
                       json={"justificativa": " Limitação técnica constatada "} if corpo is None else corpo)


def mudar(client, headers, cenario, estado, versao=0):
    return client.patch(cenario["url"], headers=headers, json={"versao": versao,
        "transicao": {"estado": estado, "motivo": "Decisão de acompanhamento"}})


def test_ct74_ct77_aceita_sem_medida_sem_mudar_estado(client, headers, database, account, cenario):
    r = aceitar(client, headers, cenario)
    assert r.status_code == 201
    item = r.json
    assert ObjectId.is_valid(item["id"])
    assert item["justificativa"] == "Limitação técnica constatada"
    assert item["autor"] == str(account["_id"])
    assert datetime.fromisoformat(item["data"]) == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert "medida_compensatoria" not in item and item["episodio"] == 0
    assert r.headers["Location"] == cenario["aceitacoes"]
    antes = cenario["item"]
    depois = client.get(cenario["url"], headers=headers).json
    for campo in set(antes) - {"aceitacoes", "aceitacoes_do_estado_atual"}:
        assert depois[campo] == antes[campo]
    assert depois["estado"] == "sem solução" and depois["aceitacoes"] == [item]
    assert depois["aceitacoes_do_estado_atual"] == [item]
    assert client.get(r.headers["Location"], headers=headers).json == [item]
    assert r.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("medida", [None, " Monitoramento mensal "])
def test_ct77_medida_opcional(client, headers, cenario, medida):
    r = aceitar(client, headers, cenario, {"justificativa": "Limitação técnica", "medida_compensatoria": medida})
    assert r.status_code == 201
    if medida is None:
        assert "medida_compensatoria" not in r.json
    else:
        assert r.json["medida_compensatoria"] == medida.strip()


@pytest.mark.parametrize("corpo", [None, [], "texto", {}, {"justificativa": None},
    {"justificativa": " "}, {"justificativa": 123}, {"justificativa": []},
    {"justificativa": "Motivo", "medida_compensatoria": " "},
    {"justificativa": "Motivo", "medida_compensatoria": []},
    {"justificativa": "Motivo", "autor": "forjado"},
    {"justificativa": "Motivo", "data": "2000-01-01"},
    {"justificativa": "Motivo", "episodio": 99},
    {"justificativa": "Motivo", "estado": "resolvida"},
    {"justificativa": "Motivo", "id": str(ObjectId())}])
def test_ct75_corpo_invalido_preserva_ocorrencia(client, headers, database, cenario, corpo):
    antes = snapshot(database)
    r = client.post(cenario["aceitacoes"], headers=headers, data=json.dumps(corpo), content_type="application/json")
    assert r.status_code == 422 and snapshot(database) == antes


@pytest.mark.parametrize("estado", ["aberta", "resolvida"])
def test_ct76_estado_incompativel(client, headers, database, cenario, estado):
    assert mudar(client, headers, cenario, estado).status_code == 200
    antes = snapshot(database)
    assert aceitar(client, headers, cenario).status_code == 409
    assert snapshot(database) == antes


def test_lista_vazia_id_invalido_e_inexistente(client, headers, database, cenario):
    assert client.get(cenario["aceitacoes"], headers=headers).json == []
    antes = snapshot(database)
    for identificador, status in [("invalido", 400), (str(ObjectId()), 404)]:
        url = f"/ocorrencias/{identificador}/aceitacoes"
        assert client.get(url, headers=headers).status_code == status
        assert client.post(url, headers=headers, json={"justificativa": "Decisão"}).status_code == status
    assert snapshot(database) == antes


@pytest.mark.parametrize("chave", ["", " ", "a" * 129, "decisão", "chave com espaco", ":inicial"])
def test_chave_invalida_nao_gera_nova_decisao(client, headers, database, cenario, chave):
    antes = snapshot(database)
    r = aceitar(client, headers, cenario, chave=chave)
    assert r.status_code == 422 and "Idempotency-Key" in r.json["campos"]
    assert snapshot(database) == antes


def test_reenvio_normalizado_e_nova_decisao(client, headers, cenario):
    primeira = aceitar(client, headers, cenario)
    repetida = aceitar(client, headers, cenario, {"justificativa": "Limitação técnica constatada", "medida_compensatoria": None})
    assert primeira.status_code == 201 and repetida.status_code == 200 and repetida.json == primeira.json
    nova = aceitar(client, headers, cenario, chave="decisao-2")
    assert nova.status_code == 201 and nova.json["id"] != primeira.json["id"]
    assert client.get(cenario["aceitacoes"], headers=headers).json == [primeira.json, nova.json]


@pytest.mark.parametrize("corpo", [{"justificativa": "Outra decisão"},
    {"justificativa": "Limitação técnica constatada", "medida_compensatoria": "Inspeção trimestral"}])
def test_mesma_chave_outro_conteudo_retorna_conflito(client, headers, database, cenario, corpo):
    assert aceitar(client, headers, cenario).status_code == 201
    antes = snapshot(database)
    assert aceitar(client, headers, cenario, corpo).status_code == 409
    assert snapshot(database) == antes


def test_sem_chave_cada_post_e_uma_decisao(client, headers, cenario):
    primeira = aceitar(client, headers, cenario, chave=None)
    segunda = aceitar(client, headers, cenario, chave=None)
    assert primeira.status_code == segunda.status_code == 201 and primeira.json["id"] != segunda.json["id"]
    assert len(client.get(cenario["aceitacoes"], headers=headers).json) == 2


def test_ct73_reenvio_apos_resolver_nao_reaplica_aceitacao(client, headers, cenario):
    primeira = aceitar(client, headers, cenario).json
    assert mudar(client, headers, cenario, "resolvida").status_code == 200
    repetida = aceitar(client, headers, cenario)
    assert repetida.status_code == 200 and repetida.json == primeira
    assert aceitar(client, headers, cenario, chave="decisao-2").status_code == 409
    assert mudar(client, headers, cenario, "aberta", 1).status_code == 200
    assert mudar(client, headers, cenario, "sem solução", 2).status_code == 200
    repetida = aceitar(client, headers, cenario)
    assert repetida.status_code == 200 and repetida.json == primeira
    item = client.get(cenario["url"], headers=headers).json
    assert item["aceitacoes"] == [primeira] and item["aceitacoes_do_estado_atual"] == []
    nova = aceitar(client, headers, cenario, chave="decisao-2")
    assert nova.status_code == 201 and nova.json["episodio"] == 3


@pytest.mark.parametrize("voltar", [False, True])
def test_transicao_entre_validacao_e_repositorio_nao_aceita_episodio_novo(client, headers, cenario, voltar):
    from app.ocorrencias.repository import RepositorioOcorrencias
    original = RepositorioOcorrencias.aceitar
    def alterar_antes(repo, ocorrencia_id, aceitacao, chave=None, **opcoes):
        outro = client.application.test_client()
        assert mudar(outro, headers, cenario, "resolvida").status_code == 200
        if voltar:
            assert mudar(outro, headers, cenario, "sem solução", 1).status_code == 200
        return original(repo, ocorrencia_id, aceitacao, chave, **opcoes)
    with patch.object(RepositorioOcorrencias, "aceitar", alterar_antes):
        r = aceitar(client, headers, cenario)
    assert r.status_code == 409
    assert client.get(cenario["aceitacoes"], headers=headers).json == []


def verificar_posts_simultaneos(app, client, headers, cenario, mesma_chave):
    from app.ocorrencias.repository import RepositorioOcorrencias
    barreira = Barrier(2)
    original = RepositorioOcorrencias.aceitar
    def sincronizar(repo, *args, **opcoes):
        barreira.wait(timeout=15)
        return original(repo, *args, **opcoes)
    def chamar(indice):
        with app.test_client() as outro:
            return aceitar(outro, headers, cenario, chave="simultanea" if mesma_chave else f"simultanea-{indice}")
    with patch.object(RepositorioOcorrencias, "aceitar", sincronizar), ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(chamar, range(2)))
    assert sorted(r.status_code for r in respostas) == ([200, 201] if mesma_chave else [201, 201])
    salvas = client.get(cenario["aceitacoes"], headers=headers).json
    assert len(salvas) == (1 if mesma_chave else 2)
    if mesma_chave:
        assert respostas[0].json == respostas[1].json == salvas[0]


@pytest.mark.parametrize("mesma_chave", [True, False])
def test_posts_simultaneos_nao_duplicam_nem_perdem_decisoes(app, client, headers, cenario, mesma_chave):
    verificar_posts_simultaneos(app, client, headers, cenario, mesma_chave)


@pytest.mark.atlas
@pytest.mark.parametrize("mesma_chave", [True, False])
def test_posts_simultaneos_mongo_real(app, client, headers, cenario, mesma_chave):
    verificar_posts_simultaneos(app, client, headers, cenario, mesma_chave)


def verificar_aceitacao_e_transicao(app, client, headers, cenario):
    from app.ocorrencias.repository import RepositorioOcorrencias
    barreira = Barrier(2)
    aceitar_original, atualizar_original = RepositorioOcorrencias.aceitar, RepositorioOcorrencias.atualizar
    def sincronizar_aceitacao(repo, *args, **opcoes):
        barreira.wait(timeout=15)
        return aceitar_original(repo, *args, **opcoes)
    def sincronizar_transicao(repo, *args, **opcoes):
        barreira.wait(timeout=15)
        return atualizar_original(repo, *args, **opcoes)
    def chamar(operacao):
        with app.test_client() as outro:
            return aceitar(outro, headers, cenario) if operacao == "aceitar" else mudar(outro, headers, cenario, "resolvida")
    with patch.object(RepositorioOcorrencias, "aceitar", sincronizar_aceitacao), \
            patch.object(RepositorioOcorrencias, "atualizar", sincronizar_transicao), ThreadPoolExecutor(max_workers=2) as executor:
        aceita, resolvida = list(executor.map(chamar, ["aceitar", "resolver"]))
    assert aceita.status_code in (201, 409) and resolvida.status_code == 200
    item = client.get(cenario["url"], headers=headers).json
    assert item["estado"] == "resolvida" and item["aceitacoes_do_estado_atual"] == []
    assert len(item["aceitacoes"]) == (1 if aceita.status_code == 201 else 0)
    if aceita.status_code == 201:
        assert item["aceitacoes"] == [aceita.json] and aceita.json["episodio"] == 0


def test_aceitacao_e_resolucao_simultaneas(app, client, headers, cenario):
    verificar_aceitacao_e_transicao(app, client, headers, cenario)


@pytest.mark.atlas
def test_aceitacao_e_resolucao_simultaneas_mongo_real(app, client, headers, cenario):
    verificar_aceitacao_e_transicao(app, client, headers, cenario)


@pytest.mark.parametrize("commit", [False, True])
def test_timeout_pode_ser_reenviado_sem_duplicar(client, headers, database, cenario, commit):
    original = database.tbl_ocorrencias.find_one_and_update
    def falhar(*args, **opcoes):
        if commit:
            original(*args, **opcoes)
        raise AutoReconnect("resposta perdida")
    with patch.object(database.tbl_ocorrencias, "find_one_and_update", side_effect=falhar):
        r = aceitar(client, headers, cenario)
    assert r.status_code == 503 and "Location" not in r.headers
    antes = client.get(cenario["aceitacoes"], headers=headers).json
    assert len(antes) == (1 if commit else 0)
    repetida = aceitar(client, headers, cenario)
    assert repetida.status_code == (200 if commit else 201)
    assert client.get(cenario["aceitacoes"], headers=headers).json == [repetida.json]


def test_rejeicao_no_banco_preserva_registro(client, headers, database, cenario):
    antes = snapshot(database)
    with patch.object(database.tbl_ocorrencias, "find_one_and_update", side_effect=WriteError("falha")):
        assert aceitar(client, headers, cenario).status_code == 503
    assert snapshot(database) == antes


def test_falha_de_leitura_nao_retorna_historico_vazio(client, headers, database, cenario):
    with patch.object(database.tbl_ocorrencias, "find_one", side_effect=AutoReconnect("falha")):
        assert client.get(cenario["aceitacoes"], headers=headers).status_code == 503


@pytest.mark.parametrize("situacao,status", [("sem_token", 401), ("expirado", 401), ("refresh", 422),
    ("perfil", 403), ("inativa", 401), ("revogada", 401), ("removida", 401)])
def test_ct03_endpoints_protegidos(client, headers, emitir_headers, database, account, cenario, situacao, status):
    auth = {}
    if situacao == "expirado":
        auth = emitir_headers(expirado=True)
    elif situacao == "refresh":
        auth = emitir_headers(tipo_token="refresh")
    elif situacao == "perfil":
        auth = emitir_headers(claims={"tipo": "trabalhador"})
    elif situacao == "inativa":
        auth = headers
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    elif situacao == "removida":
        auth = headers
        database.tbl_construtora.delete_one({"_id": account["_id"]})
    elif situacao == "revogada":
        auth = headers
        client.post("/construtora/logout/", headers=headers)
    antes = snapshot(database)
    assert aceitar(client, auth, cenario).status_code == status
    assert client.get(cenario["aceitacoes"], headers=auth).status_code == status
    assert snapshot(database) == antes


@pytest.mark.parametrize("situacao", ["outra_construtora", "obra_removida", "sem_vinculo_com_obra"])
def test_contexto_da_obra(client, headers, database, cenario, situacao):
    if situacao == "outra_construtora":
        database.tbl_obras.update_one({"_id": ObjectId(cenario["obra_id"])}, {"$set": {"autor": str(ObjectId())}})
    elif situacao == "obra_removida":
        database.tbl_obras.delete_one({"_id": ObjectId(cenario["obra_id"])})
    else:
        database.tbl_ocorrencias.update_one({"_id": ObjectId(cenario["item"]["id"])}, {"$unset": {"obra_id": ""}})
    antes = snapshot(database)
    assert aceitar(client, headers, cenario).status_code == 404
    assert client.get(cenario["aceitacoes"], headers=headers).status_code == 404
    assert snapshot(database) == antes


def test_formato_nao_json_rejeitado(client, headers, cenario):
    assert client.post(cenario["aceitacoes"], headers=headers, data={"justificativa": "Decisão"}).status_code == 415


def test_ct78_nova_aplicacao_preserva_aceitacao(client, headers, database, cenario):
    aceita = aceitar(client, headers, cenario)
    assert aceita.status_code == 201
    with isolated_app(database) as reiniciada:
        novo = reiniciada.test_client()
        assert novo.get(cenario["aceitacoes"], headers=headers).json == [aceita.json]
        assert novo.get(cenario["url"], headers=headers).json["aceitacoes_do_estado_atual"] == [aceita.json]
        assert aceitar(novo, headers, cenario).json == aceita.json


@pytest.mark.atlas
def test_ct78_persistencia_em_novo_processo(client, headers, database, cenario):
    aceita = aceitar(client, headers, cenario)
    assert aceita.status_code == 201
    processo = subprocess.run([sys.executable, "-B", str(Path(__file__).parent / "restart_probe.py")],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=cenario["aceitacoes"]),
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert processo.returncode == 0, "Falha ao reler aceitação em processo independente; credenciais omitidas"
    assert json.loads(processo.stdout) == {"status": 200, "body": [aceita.json]}
