"""UC-14, CT-64 a CT-68 e CT-03; provedor simulado e Mongo isolado."""

from io import BytesIO
from pathlib import Path
import json
import os
import subprocess
import sys
from unittest.mock import patch

from bson import ObjectId
from pymongo.errors import WriteError, AutoReconnect, WriteConcernError
import pytest
from werkzeug.datastructures import MultiDict

from support import isolated_app, snapshot
from support_avancos import backend
from support_midias import config, conteudos


@pytest.fixture
def contexto(client, headers, obra, database):
    resposta = client.post("/obras", json=obra, headers=headers)
    assert resposta.status_code == 201
    obra_id = resposta.json["id"]
    marco = client.post(f"/obras/{obra_id}/marcos", headers=headers, json={
        "nome": "Fundação", "descricao": "Base", "inicio_previsto": "2030-01-20",
        "fim_previsto": "2030-02-20"})
    assert marco.status_code == 201
    responsavel = client.post(f"/trabalhadores/obra/{obra_id}/", headers=headers, json={
        "nome": "Ana Souza", "email": "ana@example.com", "telefone": "11987654321", "cargo": "Pedreira"})
    assert responsavel.status_code == 201
    return {"obra": obra_id, "marco": marco.json["id"], "responsavel": responsavel.json["id"],
            "lista": f"/obras/{obra_id}/ocorrencias"}


def dados(**alteracoes):
    return {"titulo": " Infiltração ", "descricao": " Água na parede ", "estado": "aberta", **alteracoes}


def enviar_midia(client, headers, contexto, conteudo, **alteracoes):
    return client.post(contexto["lista"], headers=headers, data={
        **dados(estado="sem solução", marco_id=contexto["marco"],
                responsavel_id=contexto["responsavel"], **alteracoes),
        "midias": (BytesIO(conteudo), "evidencia.png")}, content_type="multipart/form-data")


def test_ct64_criacao_minima_e_consultas(client, headers, account, database, contexto):
    r = client.post(contexto["lista"], headers=headers, json=dados())
    assert r.status_code == 201
    item = r.json
    assert item["titulo"] == "Infiltração" and item["descricao"] == "Água na parede"
    assert item["autor"] == str(account["_id"])
    assert item["data_registro"] == "2030-10-20T12:00:00+00:00"
    assert item["estado"] == "aberta" and item["aceitacoes"] == item["midias"] == []
    assert item["marco_id"] is item["responsavel_id"] is None
    assert client.get(r.headers["Location"], headers=headers).json == item
    assert client.get(contexto["lista"], headers=headers).json == {"ocorrencias": [item]}
    assert database.tbl_ocorrencias.find_one()["obra_id"] == ObjectId(contexto["obra"])
    assert database.tbl_avancos.count_documents({}) == 0


@pytest.mark.parametrize("opcional", [None, "", "  "])
def test_opcionais_vazios_aceitos(client, headers, contexto, opcional):
    r = client.post(contexto["lista"], headers=headers,
                    json=dados(marco_id=opcional, responsavel_id=opcional))
    assert r.status_code == 201 and r.json["marco_id"] is r.json["responsavel_id"] is None


@pytest.mark.parametrize("extensao", ["png", "jpg", "pdf", "mp4"])
def test_ct65_opcionais_e_acesso_protegido(client, headers, database, contexto, backend, conteudos, extensao):
    r = enviar_midia(client, headers, contexto, conteudos[extensao])
    assert r.status_code == 201
    item = r.json
    assert item["estado"] == "sem solução" and item["aceitacoes"] == []
    assert item["marco_id"] == contexto["marco"] and item["responsavel_id"] == contexto["responsavel"]
    midia = item["midias"][0]
    assert midia["ocorrencia_id"] == item["id"] and "avanco_id" not in midia
    assert "referencia_externa" not in r.text and "public_id" not in r.text
    assert client.get(midia["conteudo"]).status_code == 401
    assert client.get(midia["conteudo"], headers=headers).data == conteudos[extensao]
    assert client.get(f"/midias/{midia['id']}", headers=headers).json == midia
    assert client.get(f"/obras/{contexto['obra']}/previa", headers=headers).json == {"atualizacoes": []}
    assert database.tbl_avancos.count_documents({}) == database.tbl_midias.count_documents({}) == 0
    # UC-16 é a única ação que acrescenta a aceitação.
    assert client.get(f"/ocorrencias/{item['id']}/aceitacoes", headers=headers).json == []
    aceitar = client.post(f"/ocorrencias/{item['id']}/aceitacoes", headers=headers,
                         json={"justificativa": "Decisão formal"})
    assert aceitar.status_code == 201


@pytest.mark.parametrize("campo,valor", [
    ("titulo", None), ("titulo", " "), ("titulo", 12), ("descricao", ""), ("descricao", []),
    ("estado", "resolvida"), ("estado", "aceita"), ("estado", None), ("estado", []),
    ("autor", "forjado"), ("data_registro", "2000-01-01"), ("id", str(ObjectId())),
    ("aceitacoes", []), ("midias", []),
])
def test_ct67_campos_invalidos(client, headers, database, contexto, campo, valor):
    antes = snapshot(database)
    r = client.post(contexto["lista"], headers=headers, json=dados(**{campo: valor}))
    assert r.status_code == 422 and campo in r.json["campos"]
    assert snapshot(database) == antes


@pytest.mark.parametrize("campo", ["titulo", "descricao", "estado"])
def test_ct67_campos_ausentes(client, headers, contexto, campo):
    corpo = dados()
    del corpo[campo]
    r = client.post(contexto["lista"], headers=headers, json=corpo)
    assert r.status_code == 422 and campo in r.json["campos"]


@pytest.mark.parametrize("campo", ["marco_id", "responsavel_id"])
@pytest.mark.parametrize("situacao,status", [("outra_obra", 404), ("ausente", 404), ("invalido", 400)])
def test_ct66_vinculos_invalidos(client, headers, database, contexto, campo, situacao, status):
    identificador = ObjectId()
    if situacao == "outra_obra":
        colecao = database.tbl_marcos if campo == "marco_id" else database.tbl_trabalhadores
        colecao.insert_one({"_id": identificador, "obra_id": ObjectId(), "obras": [str(ObjectId())]})
    antes = snapshot(database)
    r = client.post(contexto["lista"], headers=headers,
                    json=dados(**{campo: "invalido" if situacao == "invalido" else str(identificador)}))
    assert r.status_code == status and campo in r.json["campos"]
    assert snapshot(database) == antes


def test_lista_vazia_obra_inexistente_e_contexto(client, headers, database, contexto):
    assert client.get(contexto["lista"], headers=headers).json == {"ocorrencias": []}
    assert client.get(f"/obras/{ObjectId()}/ocorrencias", headers=headers).status_code == 404
    assert client.post(f"/obras/{ObjectId()}/ocorrencias", headers=headers, json=dados()).status_code == 404
    assert client.get(f"/ocorrencias/{ObjectId()}", headers=headers).status_code == 404
    criado = client.post(contexto["lista"], headers=headers, json=dados()).json
    database.tbl_obras.update_one({"_id": ObjectId(contexto["obra"])}, {"$set": {"autor": str(ObjectId())}})
    assert client.get(contexto["lista"], headers=headers).status_code == 404
    assert client.get(f"/ocorrencias/{criado['id']}", headers=headers).status_code == 404


@pytest.mark.parametrize("situacao,status", [("sem_token", 401), ("expirado", 401), ("refresh", 422),
                                            ("perfil", 403), ("inativa", 401), ("revogada", 401)])
def test_ct03_novos_endpoints(client, headers, emitir_headers, account, database, contexto, situacao, status):
    criado = client.post(contexto["lista"], headers=headers, json=dados()).json
    auth = {}
    if situacao == "expirado":
        auth = emitir_headers(expirado=True)
    elif situacao == "refresh":
        auth = emitir_headers(tipo_token="refresh")
    elif situacao == "perfil":
        auth = emitir_headers(claims={"tipo": "trabalhador"})
    elif situacao in {"inativa", "revogada"}:
        auth = headers
        if situacao == "inativa":
            database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
        else:
            assert client.post("/construtora/logout/", headers=headers).status_code == 200
    antes = snapshot(database)
    for metodo, caminho in [("POST", contexto["lista"]), ("GET", contexto["lista"]),
                            ("GET", f"/ocorrencias/{criado['id']}")]:
        r = client.open(caminho, method=metodo, headers=auth, json=dados())
        assert r.status_code == status
    assert snapshot(database) == antes


@pytest.mark.parametrize("com_midia", [False, True])
def test_ct68_releitura_em_nova_aplicacao(client, headers, database, contexto, backend, conteudos, com_midia):
    r = (enviar_midia(client, headers, contexto, conteudos["png"]) if com_midia
         else client.post(contexto["lista"], headers=headers, json=dados()))
    assert r.status_code == 201
    with isolated_app(database) as reiniciada:
        novo = reiniciada.test_client()
        assert novo.get(r.headers["Location"], headers=headers).json == r.json
        assert novo.get(contexto["lista"], headers=headers).json == {"ocorrencias": [r.json]}
        if com_midia:
            assert novo.get(r.json["midias"][0]["conteudo"], headers=headers).data == conteudos["png"]


def test_midia_invalida_nao_envia_nem_grava(client, headers, database, contexto, backend):
    r = enviar_midia(client, headers, contexto, b"conteudo falso")
    assert r.status_code == 422
    backend[1].assert_not_called()
    assert database.tbl_ocorrencias.count_documents({}) == 0


@pytest.mark.parametrize("quantidade,status", [(2, 201), (6, 422)])
def test_lote_de_midias_e_limite(client, headers, database, contexto, backend, conteudos, quantidade, status):
    formulario = MultiDict(dados())
    for indice in range(quantidade):
        formulario.add("midias", (BytesIO(conteudos["png"]), f"foto{indice}.png"))
    r = client.post(contexto["lista"], headers=headers, data=formulario)
    assert r.status_code == status
    if status == 201:
        assert len(r.json["midias"]) == quantidade
    else:
        backend[1].assert_not_called()
        assert database.tbl_ocorrencias.count_documents({}) == 0


def test_falha_no_segundo_upload_compensa_primeiro(client, headers, database, contexto, backend, conteudos):
    upload = backend[1].side_effect
    def enviar(stream, **opcoes):
        if backend[1].call_count == 2:
            raise OSError("falha de rede")
        return upload(stream, **opcoes)
    backend[1].side_effect = enviar
    formulario = MultiDict(dados())
    for _ in range(2):
        formulario.add("midias", (BytesIO(conteudos["png"]), "foto.png"))
    r = client.post(contexto["lista"], headers=headers, data=formulario)
    assert r.status_code == 503 and not backend[0]
    assert database.tbl_ocorrencias.count_documents({}) == 0


def test_responsavel_de_outra_construtora_rejeitado(client, headers, database, contexto):
    database.tbl_trabalhadores.update_one({"_id": ObjectId(contexto["responsavel"])},
                                         {"$set": {"construtora_id": str(ObjectId())}})
    r = client.post(contexto["lista"], headers=headers, json=dados(responsavel_id=contexto["responsavel"]))
    assert r.status_code == 404 and database.tbl_ocorrencias.count_documents({}) == 0


@pytest.mark.parametrize("remover", ["obra", "marco", "vinculo_midia"])
def test_contexto_invalido_nao_libera_midia(client, headers, database, contexto, backend, conteudos, remover):
    r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 201
    if remover == "obra":
        database.tbl_obras.delete_one({"_id": ObjectId(contexto["obra"])})
    elif remover == "marco":
        database.tbl_marcos.update_one({"_id": ObjectId(contexto["marco"])}, {"$set": {"obra_id": ObjectId()}})
    else:
        database.tbl_ocorrencias.update_one({"_id": ObjectId(r.json["id"])},
                                            {"$set": {"midias.0.ocorrencia_id": ObjectId()}})
    assert client.get(r.json["midias"][0]["conteudo"], headers=headers).status_code == 404
    if remover != "vinculo_midia":
        assert client.get(r.headers["Location"], headers=headers).status_code == 404


@pytest.mark.parametrize("remover", ["marco", "responsavel"])
def test_vinculos_revalidados_apos_upload(client, headers, database, contexto, backend, conteudos, remover):
    upload = backend[1].side_effect
    def enviar(stream, **opcoes):
        colecao = database.tbl_marcos if remover == "marco" else database.tbl_trabalhadores
        colecao.delete_one({"_id": ObjectId(contexto[remover])})
        return upload(stream, **opcoes)
    backend[1].side_effect = enviar
    r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 404 and not backend[0]
    assert database.tbl_ocorrencias.count_documents({}) == 0


def test_falha_no_diario_nao_envia_arquivo(client, headers, database, contexto, backend, conteudos):
    with patch.object(database.tbl_uploads_pendentes, "update_one", side_effect=WriteError("falha")):
        r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 503
    backend[1].assert_not_called()
    assert database.tbl_ocorrencias.count_documents({}) == 0


def test_falha_ao_concluir_diario_preserva_cadastro(client, headers, database, contexto, backend, conteudos):
    with patch("app.ocorrencias.repository.RepositorioOcorrencias.concluir_operacao", side_effect=AutoReconnect("falha")):
        r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 201 and backend[0]
    assert client.get(r.headers["Location"], headers=headers).json == r.json
    from app.avancos.reconciliacao import ServicoReconciliacao
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    pendente = database.tbl_uploads_pendentes.find_one({"estado": "pendente"})
    ServicoReconciliacao(ArmazenamentoCloudinary(), banco=database).reconciliar(
        pendente["_id"], aplicacao_parada=True)
    assert backend[0]


@pytest.mark.parametrize("corpo", [None, [], "texto"])
def test_corpo_json_invalido(client, headers, contexto, corpo):
    r = client.post(contexto["lista"], headers=headers, data=json.dumps(corpo), content_type="application/json")
    assert r.status_code == 422


def test_multipart_campos_repetidos_e_arquivo_sem_nome(client, headers, contexto):
    formulario = MultiDict(dados())
    formulario.add("titulo", "Outro título")
    assert client.post(contexto["lista"], headers=headers, data=formulario,
                       content_type="multipart/form-data").status_code == 422
    formulario = {**dados(), "midias": (BytesIO(b""), "")}
    r = client.post(contexto["lista"], headers=headers, data=formulario)
    assert r.status_code == 201 and r.json["midias"] == []


@pytest.mark.parametrize("limpeza_falha", [False, True])
def test_falha_banco_compensa_ou_mantem_diario(client, headers, database, contexto, backend, conteudos, limpeza_falha):
    if limpeza_falha:
        backend[2].side_effect = OSError("falha do provedor")
    with patch.object(database.tbl_ocorrencias, "insert_one", side_effect=WriteError("falha")):
        r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 503 and "Location" not in r.headers
    assert database.tbl_ocorrencias.count_documents({}) == 0
    if limpeza_falha:
        pendente = database.tbl_uploads_pendentes.find_one({"estado": "pendente"})
        assert "ocorrencia_id" in pendente and "avanco_id" not in pendente
        backend[2].side_effect = lambda **opcoes: (backend[0].pop(opcoes["public_id"], None), {"result": "ok"})[1]
        from app.avancos.reconciliacao import ServicoReconciliacao
        from app.integracoes.armazenamento import ArmazenamentoCloudinary
        assert ServicoReconciliacao(ArmazenamentoCloudinary(), banco=database).reconciliar(
            pendente["_id"], aplicacao_parada=True) == "limpa"
    assert not backend[0]


@pytest.mark.parametrize("erro", [AutoReconnect, WriteConcernError])
@pytest.mark.parametrize("commit", [False, True])
def test_timeout_preserva_referencias_ate_reconciliar(client, headers, database, contexto, backend, conteudos, commit, erro):
    inserir = database.tbl_ocorrencias.insert_one
    def falhar(documento):
        if commit:
            inserir(documento)
        raise erro("resposta perdida")
    with patch.object(database.tbl_ocorrencias, "insert_one", side_effect=falhar):
        r = enviar_midia(client, headers, contexto, conteudos["png"])
    assert r.status_code == 503 and "Location" not in r.headers
    assert backend[0]
    from app.avancos.reconciliacao import ServicoReconciliacao
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    pendente = database.tbl_uploads_pendentes.find_one({"estado": "pendente"})
    assert ServicoReconciliacao(ArmazenamentoCloudinary(), banco=database).reconciliar(
        pendente["_id"], aplicacao_parada=True) == "limpa"
    assert bool(backend[0]) == commit


@pytest.mark.atlas
@pytest.mark.parametrize("com_midia", [False, True])
def test_ct68_mongo_real_em_novo_processo(client, headers, database, contexto, backend, conteudos, com_midia):
    r = (enviar_midia(client, headers, contexto, conteudos["png"]) if com_midia
         else client.post(contexto["lista"], headers=headers, json=dados()))
    assert r.status_code == 201
    processo = subprocess.run([sys.executable, "-B", str(Path(__file__).parent / "restart_probe.py")],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=r.headers["Location"]),
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert processo.returncode == 0, "Falha na releitura em processo independente"
    assert json.loads(processo.stdout) == {"status": 200, "body": r.json}
