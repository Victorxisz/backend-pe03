"""UC-15: CT-69 a CT-73, autenticação, concorrência e persistência."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from unittest.mock import patch

from bson import ObjectId
from pymongo.errors import WriteError
import pytest

from support import isolated_app, snapshot
from support_avancos import backend
from support_midias import config, conteudos


@pytest.fixture
def cenario(client, headers, obra):
    obra_r = client.post("/obras", headers=headers, json=obra)
    assert obra_r.status_code == 201
    obra_id = obra_r.json["id"]
    marco = client.post(f"/obras/{obra_id}/marcos", headers=headers, json={
        "nome": "Fundação", "descricao": "Base", "inicio_previsto": "2030-01-20", "fim_previsto": "2030-02-20"})
    trabalhador = client.post(f"/trabalhadores/obra/{obra_id}/", headers=headers, json={
        "nome": "Ana Souza", "email": "ana@example.com", "telefone": "11987654321", "cargo": "Pedreira"})
    assert marco.status_code == trabalhador.status_code == 201
    r = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers, json={
        "titulo": "Infiltração", "descricao": "Água na parede", "estado": "aberta"})
    assert r.status_code == 201
    return {"url": r.headers["Location"], "item": r.json, "obra_id": obra_id,
            "marco_id": marco.json["id"], "responsavel_id": trabalhador.json["id"]}


def transicao(client, headers, cenario, estado, versao=0, motivo="Correção verificada"):
    return client.patch(cenario["url"], headers=headers,
                        json={"versao": versao, "transicao": {"estado": estado, "motivo": motivo}})


def test_ct69_resolve_e_registra_decisao(client, headers, database, account, cenario):
    r = transicao(client, headers, cenario, "resolvida")
    assert r.status_code == 200 and r.json["estado"] == "resolvida"
    assert r.json["versao"] == r.json["episodio"] == 1
    evento, = r.json["historico_estados"]
    assert evento["estado_anterior"] == "aberta" and evento["novo_estado"] == "resolvida"
    assert evento["motivo"] == "Correção verificada" and evento["autor"] == str(account["_id"])
    assert datetime.fromisoformat(evento["instante"]) == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert evento["episodio_anterior"] == 0 and evento["episodio"] == 1
    for campo in ("id", "obra_id", "titulo", "descricao", "autor", "data_registro", "midias"):
        assert r.json[campo] == cenario["item"][campo]
    assert client.get(cenario["url"], headers=headers).json == r.json
    salvo = database.tbl_ocorrencias.find_one({"_id": ObjectId(cenario["item"]["id"])})
    assert salvo["estado"] == "resolvida" and len(salvo["historico_estados"]) == 1


def test_ct70_reabre_preservando_ordem_das_decisoes(client, headers, cenario):
    primeira = transicao(client, headers, cenario, "resolvida").json
    segunda = transicao(client, headers, cenario, "aberta", 1, "Nova infiltração").json
    terceira = transicao(client, headers, cenario, "sem solução", 2, "Causa em investigação").json
    assert segunda["historico_estados"][:1] == primeira["historico_estados"]
    assert terceira["historico_estados"][:2] == segunda["historico_estados"]
    assert [evento["novo_estado"] for evento in terceira["historico_estados"]] == ["resolvida", "aberta", "sem solução"]
    assert terceira["versao"] == terceira["episodio"] == 3


@pytest.mark.parametrize("estado", ["aberta", "resolvida", "sem solução"])
def test_ct71_edicao_parcial_preserva_estado_trilha_e_autoria(client, headers, cenario, estado):
    item = cenario["item"]
    if estado != "aberta":
        item = transicao(client, headers, cenario, estado).json
    r = client.patch(cenario["url"], headers=headers, json={
        "versao": item["versao"], "alteracoes": {"titulo": " Infiltração da fachada "}})
    assert r.status_code == 200 and r.json["titulo"] == "Infiltração da fachada"
    assert r.json["versao"] == item["versao"] + 1
    for campo in ("estado", "historico_estados", "episodio", "aceitacoes", "descricao", "autor", "data_registro"):
        assert r.json[campo] == item[campo]


def test_vinculos_opcionais_podem_ser_atribuidos_e_retirados(client, headers, cenario):
    r = client.patch(cenario["url"], headers=headers, json={"versao": 0, "alteracoes": {
        "marco_id": cenario["marco_id"], "responsavel_id": cenario["responsavel_id"], "descricao": "Causa identificada"}})
    assert r.status_code == 200
    assert r.json["marco_id"] == cenario["marco_id"] and r.json["responsavel_id"] == cenario["responsavel_id"]
    r = client.patch(cenario["url"], headers=headers, json={
        "versao": 1, "alteracoes": {"marco_id": " ", "responsavel_id": None}})
    assert r.status_code == 200 and r.json["marco_id"] is r.json["responsavel_id"] is None
    assert r.json["historico_estados"] == [] and r.json["estado"] == "aberta"


def test_edicao_e_transicao_juntas(client, headers, cenario):
    r = client.patch(cenario["url"], headers=headers, json={"versao": 0,
        "alteracoes": {"titulo": "Fachada reparada", "marco_id": cenario["marco_id"]},
        "transicao": {"estado": "resolvida", "motivo": "Inspeção concluída"}})
    assert r.status_code == 200 and r.json["titulo"] == "Fachada reparada"
    assert r.json["estado"] == "resolvida" and r.json["marco_id"] == cenario["marco_id"]
    assert r.json["versao"] == 1 and len(r.json["historico_estados"]) == 1


def test_atualizacao_preserva_evidencias_e_rotas_de_midia(client, headers, cenario, backend, conteudos):
    criada = client.post(f"/obras/{cenario['obra_id']}/ocorrencias", headers=headers, data={
        "titulo": "Fachada", "descricao": "Água", "estado": "aberta",
        "midias": (BytesIO(conteudos["png"]), "fachada.png")})
    assert criada.status_code == 201
    r = client.patch(criada.headers["Location"], headers=headers, json={"versao": 0,
        "alteracoes": {"descricao": "Corrigida", "marco_id": cenario["marco_id"]},
        "transicao": {"estado": "resolvida", "motivo": "Inspeção concluída"}})
    assert r.status_code == 200 and r.json["midias"] == criada.json["midias"]
    midia = r.json["midias"][0]
    assert client.get(midia["conteudo"], headers=headers).data == conteudos["png"]
    assert client.get(f"/midias/{midia['id']}", headers=headers).json == midia
    assert client.get(f"/obras/{cenario['obra_id']}/previa", headers=headers).json == {"atualizacoes": []}


def test_aceitacao_legada_permanece_historica(client, headers, database, cenario):
    legada = {"justificativa": "Decisão anterior", "autor": cenario["item"]["autor"],
              "data": datetime(2029, 1, 1, tzinfo=timezone.utc)}
    database.tbl_ocorrencias.update_one({"_id": ObjectId(cenario["item"]["id"])},
        {"$set": {"estado": "sem solução", "aceitacoes": [legada]}})
    assert len(client.get(cenario["url"], headers=headers).json["aceitacoes_do_estado_atual"]) == 1
    transicao(client, headers, cenario, "resolvida")
    r = transicao(client, headers, cenario, "sem solução", 1)
    assert r.status_code == 200 and len(r.json["aceitacoes"]) == 1
    assert "episodio" not in r.json["aceitacoes"][0]
    assert r.json["aceitacoes_do_estado_atual"] == []


@pytest.mark.parametrize("corpo", [
    None, [], {}, {"versao": 0}, {"versao": 0, "estado": "resolvida", "motivo": "Corrigida"},
    {"versao": 0, "alteracoes": {}}, {"versao": 0, "alteracoes": None},
    {"versao": 0, "alteracoes": {"titulo": " "}}, {"versao": 0, "alteracoes": {"descricao": None}},
    {"versao": 0, "alteracoes": {"estado": "resolvida"}},
    {"versao": 0, "alteracoes": {"obra_id": str(ObjectId())}},
    {"versao": 0, "alteracoes": {"midias": []}}, {"versao": 0, "alteracoes": {"aceitacoes": []}},
    {"versao": 0, "transicao": None}, {"versao": 0, "transicao": {}},
    {"versao": 0, "transicao": {"estado": "fechada", "motivo": "Corrigida"}},
    {"versao": 0, "transicao": {"estado": [], "motivo": "Corrigida"}},
    {"versao": 0, "transicao": {"estado": "resolvida"}},
    {"versao": 0, "transicao": {"estado": "resolvida", "motivo": " "}},
    {"versao": 0, "transicao": {"estado": "resolvida", "motivo": False}},
    {"versao": 0, "transicao": {"estado": "resolvida", "motivo": "Corrigida", "autor": "forjado"}},
    {"versao": True, "alteracoes": {"titulo": "Novo"}},
    {"versao": -1, "alteracoes": {"titulo": "Novo"}},
    {"versao": "0", "alteracoes": {"titulo": "Novo"}},
])
def test_ct72_entrada_invalida_preserva_banco(client, headers, database, cenario, corpo):
    antes = snapshot(database)
    r = client.patch(cenario["url"], headers=headers, data=json.dumps(corpo), content_type="application/json")
    assert r.status_code == 422
    assert snapshot(database) == antes


@pytest.mark.parametrize("campo", ["marco_id", "responsavel_id"])
@pytest.mark.parametrize("tipo,status", [("invalido", 400), ("inexistente", 404), ("outra_obra", 404)])
def test_vinculos_invalidos_rejeitam_inclusive_transicao(client, headers, database, cenario, campo, tipo, status):
    identificador = ObjectId()
    if tipo == "outra_obra":
        colecao = database.tbl_marcos if campo == "marco_id" else database.tbl_trabalhadores
        colecao.insert_one({"_id": identificador, "obra_id": ObjectId(), "obras": [str(ObjectId())]})
    antes = snapshot(database)
    r = client.patch(cenario["url"], headers=headers, json={"versao": 0,
        "alteracoes": {campo: "invalido" if tipo == "invalido" else str(identificador)},
        "transicao": {"estado": "resolvida", "motivo": "Corrigida"}})
    assert r.status_code == status and snapshot(database) == antes


def test_ct73_aceitacoes_historicas_nao_aceitam_novo_episodio(client, headers, cenario):
    transicao(client, headers, cenario, "sem solução")
    url = cenario["url"] + "/aceitacoes"
    auth = {**headers, "Idempotency-Key": "decisao-1"}
    decisao = {"justificativa": "Limitação técnica"}
    aceita = client.post(url, headers=auth, json=decisao)
    assert aceita.status_code == 201 and aceita.json["episodio"] == 1
    assert client.get(cenario["url"], headers=headers).json["aceitacoes_do_estado_atual"] == [aceita.json]
    resolvida = transicao(client, headers, cenario, "resolvida", 1).json
    assert resolvida["aceitacoes"] == [aceita.json] and resolvida["aceitacoes_do_estado_atual"] == []
    assert client.post(url, headers=headers, json=decisao).status_code == 409
    reaberta = transicao(client, headers, cenario, "aberta", 2).json
    assert reaberta["aceitacoes"] == [aceita.json] and reaberta["aceitacoes_do_estado_atual"] == []
    sem_solucao = transicao(client, headers, cenario, "sem solução", 3).json
    assert sem_solucao["aceitacoes_do_estado_atual"] == []
    repetida = client.post(url, headers=auth, json=decisao)
    assert repetida.status_code == 200 and repetida.json == aceita.json
    nova = client.post(url, headers={**headers, "Idempotency-Key": "decisao-2"}, json=decisao)
    assert nova.status_code == 201 and nova.json["episodio"] == 4
    item = client.get(cenario["url"], headers=headers).json
    assert item["aceitacoes"] == [aceita.json, nova.json]
    assert item["aceitacoes_do_estado_atual"] == [nova.json]
    assert client.get(url, headers=headers).json == item["aceitacoes"]


def test_sem_alteracao_nao_cria_evento_nem_versao(client, headers, database, cenario):
    antes = snapshot(database)
    r = transicao(client, headers, cenario, "aberta")
    assert r.status_code == 200 and snapshot(database) == antes
    r = client.patch(cenario["url"], headers=headers, json={"versao": 0, "alteracoes": {"titulo": "Infiltração"}})
    assert r.status_code == 200 and snapshot(database) == antes


def test_versao_antiga_inclusive_apos_estado_ir_e_voltar(client, headers, database, cenario):
    assert transicao(client, headers, cenario, "resolvida").status_code == 200
    assert transicao(client, headers, cenario, "aberta", 1).status_code == 200
    antes = snapshot(database)
    assert transicao(client, headers, cenario, "sem solução", 0).status_code == 409
    assert snapshot(database) == antes


def test_conflito_entre_leitura_e_escrita_preserva_decisao_concorrente(client, headers, database, cenario):
    from app.ocorrencias.repository import RepositorioOcorrencias
    original = RepositorioOcorrencias.atualizar
    def concorrer(repo, anterior, campos, evento):
        concorrente = {**evento, "novo_estado": "sem solução", "motivo": "Decisão concorrente"}
        original(repo, anterior, {"estado": "sem solução"}, concorrente)
        return original(repo, anterior, campos, evento)
    with patch.object(RepositorioOcorrencias, "atualizar", concorrer):
        r = transicao(client, headers, cenario, "resolvida")
    assert r.status_code == 409
    item = client.get(cenario["url"], headers=headers).json
    assert item["estado"] == "sem solução" and len(item["historico_estados"]) == 1


def verificar_concorrencia(app, client, headers, cenario):
    from app.ocorrencias.repository import RepositorioOcorrencias
    barreira = Barrier(2)
    original = RepositorioOcorrencias.atualizar
    def simultaneo(repo, anterior, campos, evento):
        barreira.wait(timeout=15)
        return original(repo, anterior, campos, evento)
    def chamar(estado):
        with app.test_client() as outro:
            return transicao(outro, headers, cenario, estado)
    with patch.object(RepositorioOcorrencias, "atualizar", simultaneo), ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(chamar, ["resolvida", "sem solução"]))
    assert sorted(r.status_code for r in respostas) == [200, 409]
    atual = client.get(cenario["url"], headers=headers).json
    perdedor = "sem solução" if atual["estado"] == "resolvida" else "resolvida"
    r = transicao(client, headers, cenario, perdedor, atual["versao"])
    assert r.status_code == 200 and len(r.json["historico_estados"]) == 2
    assert r.json["historico_estados"][1]["estado_anterior"] == atual["estado"]


def test_transicoes_simultaneas_nao_perdem_eventos(app, client, headers, cenario):
    verificar_concorrencia(app, client, headers, cenario)


@pytest.mark.atlas
def test_concorrencia_em_mongo_real(app, client, headers, cenario):
    verificar_concorrencia(app, client, headers, cenario)


def test_falha_banco_preserva_edicao_estado_e_trilha(client, headers, database, cenario):
    antes = snapshot(database)
    with patch.object(database.tbl_ocorrencias, "find_one_and_update", side_effect=WriteError("falha")):
        r = client.patch(cenario["url"], headers=headers, json={"versao": 0,
            "alteracoes": {"titulo": "Corrigido"}, "transicao": {"estado": "resolvida", "motivo": "Verificada"}})
    assert r.status_code == 503 and snapshot(database) == antes


def test_aceitacao_concorrente_preservada_na_transicao(client, headers, cenario):
    from app.ocorrencias.repository import RepositorioOcorrencias
    transicao(client, headers, cenario, "sem solução")
    original = RepositorioOcorrencias.atualizar
    def aceitar_antes(repo, anterior, campos, evento):
        repo.aceitar(anterior["_id"], {"justificativa": "Decisão simultânea", "autor": "teste", "data": datetime.now(timezone.utc)})
        return original(repo, anterior, campos, evento)
    with patch.object(RepositorioOcorrencias, "atualizar", aceitar_antes):
        r = transicao(client, headers, cenario, "resolvida", 1)
    assert r.status_code == 200 and len(r.json["aceitacoes"]) == 1
    assert r.json["aceitacoes_do_estado_atual"] == []


def test_aceitacao_atrasada_nao_e_atribuida_a_novo_episodio(client, headers, database, cenario):
    transicao(client, headers, cenario, "sem solução")
    original = database.tbl_ocorrencias.find_one_and_update
    def mudar_antes(filtro, modificacao, **opcoes):
        database.tbl_ocorrencias.update_one({"_id": ObjectId(cenario["item"]["id"])}, {"$inc": {"episodio": 2, "versao": 2}})
        return original(filtro, modificacao, **opcoes)
    with patch.object(database.tbl_ocorrencias, "find_one_and_update", side_effect=mudar_antes):
        r = client.post(cenario["url"] + "/aceitacoes", headers=headers, json={"justificativa": "Decisão atrasada"})
    assert r.status_code == 409
    assert client.get(cenario["url"], headers=headers).json["aceitacoes"] == []


@pytest.mark.parametrize("situacao,status", [("sem_token", 401), ("expirado", 401), ("perfil", 403), ("inativa", 401), ("revogada", 401)])
def test_ct03_patch_protegido(client, headers, emitir_headers, database, account, cenario, situacao, status):
    auth = {}
    if situacao == "expirado":
        auth = emitir_headers(expirado=True)
    elif situacao == "perfil":
        auth = emitir_headers(claims={"tipo": "trabalhador"})
    elif situacao == "inativa":
        auth = headers
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    elif situacao == "revogada":
        auth = headers
        client.post("/construtora/logout/", headers=headers)
    antes = snapshot(database)
    assert transicao(client, auth, cenario, "resolvida").status_code == status
    assert snapshot(database) == antes


def test_contexto_e_identificadores(client, headers, database, cenario):
    comando = {"versao": 0, "transicao": {"estado": "resolvida", "motivo": "Verificada"}}
    assert client.patch("/ocorrencias/invalido", headers=headers, json=comando).status_code == 400
    assert client.patch(f"/ocorrencias/{ObjectId()}", headers=headers, json=comando).status_code == 404
    database.tbl_obras.update_one({"_id": ObjectId(cenario["obra_id"])}, {"$set": {"autor": str(ObjectId())}})
    antes = snapshot(database)
    assert transicao(client, headers, cenario, "resolvida").status_code == 404
    assert client.get(cenario["url"] + "/aceitacoes", headers=headers).status_code == 404
    assert client.post(cenario["url"] + "/aceitacoes", headers=headers, json={"justificativa": "Decisão"}).status_code == 404
    assert snapshot(database) == antes


def test_ct73_persistencia_apos_nova_aplicacao(client, headers, database, cenario):
    transicao(client, headers, cenario, "sem solução")
    assert client.post(cenario["url"] + "/aceitacoes", headers=headers, json={"justificativa": "Limitação técnica"}).status_code == 201
    transicao(client, headers, cenario, "resolvida", 1)
    final = transicao(client, headers, cenario, "aberta", 2).json
    with isolated_app(database) as reiniciada:
        assert reiniciada.test_client().get(cenario["url"], headers=headers).json == final


@pytest.mark.atlas
def test_ct73_persistencia_em_novo_processo(client, headers, database, cenario):
    transicao(client, headers, cenario, "sem solução")
    assert client.post(cenario["url"] + "/aceitacoes", headers=headers, json={"justificativa": "Limitação técnica"}).status_code == 201
    transicao(client, headers, cenario, "resolvida", 1)
    final = transicao(client, headers, cenario, "aberta", 2).json
    processo = subprocess.run([sys.executable, "-B", str(Path(__file__).parent / "restart_probe.py")],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=cenario["url"]),
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert processo.returncode == 0, "Falha na releitura em processo independente; credenciais omitidas"
    assert json.loads(processo.stdout) == {"status": 200, "body": final}
