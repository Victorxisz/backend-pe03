"""UC-14: registro e consulta de ocorrências; só a fronteira do provedor é simulada."""

import json
import logging
import os
import subprocess
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bson import ObjectId
from flask_jwt_extended import decode_token
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot
from support_midias import config, conteudos


MINIMA = {
    "titulo": "Vazamento na laje",
    "descricao": "Infiltração aparece depois da chuva",
    "estado": "aberta",
}
COMPLETA = {
    "titulo": "Estrutura sem laudo",
    "descricao": "Serviço parado até a emissão do laudo",
    "estado": "sem solução",
}
AUSENTE = object()


@pytest.fixture(autouse=True)
def transacao_local(app, database, monkeypatch, request):
    """Memória simula o rollback; --atlas usa a sessão e a transação reais."""
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

    for nome in ("find", "insert_one", "insert_many"):
        monkeypatch.setattr(Collection, nome, sem_sessao(getattr(Collection, nome)))


@pytest.fixture
def provedor(monkeypatch, config):
    """Guarda os bytes enviados em memória: upload, consulta, remoção e download reais do adaptador."""
    for chave, valor in {
        "CLOUDINARY_CLOUD_NAME": config.cloud_name,
        "CLOUDINARY_API_KEY": config.api_key,
        "CLOUDINARY_API_SECRET": config.api_secret,
        "CLOUDINARY_FOLDER": config.pasta,
    }.items():
        monkeypatch.setenv(chave, valor)
    objetos = {}

    def enviar(stream, **opcoes):
        conteudo = stream.getvalue()
        objetos[opcoes["public_id"]] = conteudo
        return {"public_id": opcoes["public_id"], "bytes": len(conteudo),
                "resource_type": opcoes["resource_type"], "type": opcoes["type"]}

    def consultar(**opcoes):
        from cloudinary.exceptions import NotFound

        if opcoes["public_id"] not in objetos:
            raise NotFound("objeto ausente")
        return {"public_id": opcoes["public_id"]}

    def remover(**opcoes):
        objetos.pop(opcoes["public_id"], None)
        return {"result": "ok"}

    def baixar(url, timeout):
        return BytesIO(objetos[parse_qs(urlparse(url).query)["public_id"][0]])

    upload, resource, destroy, download = [
        Mock(side_effect=funcao) for funcao in (enviar, consultar, remover, baixar)
    ]
    monkeypatch.setattr("cloudinary.uploader.upload", upload)
    monkeypatch.setattr("cloudinary.api.resource", resource)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", download)
    # Uma nova instância Flask reimporta o adaptador; a fronteira HTTP segue simulada.
    monkeypatch.setattr("urllib.request.urlopen", download)
    return SimpleNamespace(objetos=objetos, upload=upload, resource=resource,
                           destroy=destroy, download=download)


@pytest.fixture
def cenario(app, database, obra, account):
    modelo = dict(obra)
    obra_id = database.tbl_obras.insert_one(dict(modelo)).inserted_id
    outra_obra_id = database.tbl_obras.insert_one(
        {**modelo, "nome": "Prédio Vizinho"}
    ).inserted_id
    marco_id = database.tbl_marcos.insert_one(
        {"obra_id": obra_id, "nome": "Fundação", "estado": "em andamento"}
    ).inserted_id
    marco_alheio_id = database.tbl_marcos.insert_one(
        {"obra_id": outra_obra_id, "nome": "Alvenaria", "estado": "a iniciar"}
    ).inserted_id
    responsavel_id = database.tbl_trabalhadores.insert_one({
        "nome": "Pedro Pedreiro", "cargo": "pedreiro", "email": "pedro@example.com",
        "telefone": "(19) 90000-0000", "obras": [str(obra_id)], "ativo": True,
    }).inserted_id
    alheio_id = database.tbl_trabalhadores.insert_one({
        "nome": "Marcos Mestre", "cargo": "mestre de obras",
        "obras": [str(outra_obra_id)], "ativo": True,
    }).inserted_id
    return SimpleNamespace(
        obra=obra_id, outra_obra=outra_obra_id, marco=marco_id,
        marco_alheio=marco_alheio_id, responsavel=responsavel_id,
        responsavel_alheio=alheio_id,
        registrar=f"/obras/{obra_id}/ocorrencias",
        listar=f"/obras/{obra_id}/ocorrencias",
    )


def formulario(conteudos=None, **campos):
    dados = {**COMPLETA, **campos}
    if conteudos is not None:
        dados["midias"] = (BytesIO(conteudos), "laje.png")
    return {"data": dados, "content_type": "multipart/form-data"}


def test_ct64_ocorrencia_minima_sem_opcionais(client, headers, account, database, cenario):
    # Execução: só título, descrição e estado inicial.
    resposta = client.post(cenario.registrar, headers=headers, json=MINIMA)

    # Verificação
    assert resposta.status_code == 201
    ocorrencia = resposta.get_json()
    assert ocorrencia["obra_id"] == str(cenario.obra)
    assert ocorrencia["titulo"] == MINIMA["titulo"]
    assert ocorrencia["descricao"] == MINIMA["descricao"]
    assert ocorrencia["estado"] == "aberta"
    # ID, autoria e data de registro vêm do servidor.
    assert ObjectId.is_valid(ocorrencia["id"])
    assert ocorrencia["autor"] == str(account["_id"])
    assert datetime.fromisoformat(ocorrencia["data_registro"]) == datetime(
        2030, 10, 20, 12, tzinfo=timezone.utc
    )
    # Opcionais ausentes são aceitos e aparecem vazios, não omitidos.
    assert (ocorrencia["marco"], ocorrencia["responsavel"], ocorrencia["midias"]) == (None, None, [])
    assert ocorrencia["aceita"] is False
    assert resposta.headers["Location"] == f"/ocorrencias/{ocorrencia['id']}"
    assert resposta.headers["Cache-Control"] == "private, no-store"
    # Aparece na obra e no próprio recurso.
    assert client.get(resposta.headers["Location"], headers=headers).get_json() == ocorrencia
    assert client.get(cenario.listar, headers=headers).get_json() == {"ocorrencias": [ocorrencia]}
    salva = database.tbl_ocorrencias.find_one({"_id": ObjectId(ocorrencia["id"])})
    assert salva["obra_id"] == cenario.obra and salva["autor"] == str(account["_id"])
    assert salva["marco_id"] is None and salva["responsavel_id"] is None


def test_ct65_sem_solucao_com_marco_responsavel_e_midia(
    client, headers, database, cenario, provedor, conteudos
):
    # Execução: formulário com os três opcionais preenchidos.
    resposta = client.post(cenario.registrar, headers=headers, **formulario(
        conteudos["png"],
        marco_id=str(cenario.marco),
        responsavel_id=str(cenario.responsavel),
    ))

    # Verificação
    assert resposta.status_code == 201
    ocorrencia = resposta.get_json()
    assert ocorrencia["estado"] == "sem solução"
    # Registrar como "sem solução" não é aceitação: isso pertence à UC-16.
    assert ocorrencia["aceita"] is False
    salva = database.tbl_ocorrencias.find_one({"_id": ObjectId(ocorrencia["id"])})
    assert "aceitacao" not in salva
    # Vínculos corretos, sem expor contato do trabalhador.
    assert ocorrencia["marco"] == {"id": str(cenario.marco), "nome": "Fundação"}
    assert ocorrencia["responsavel"] == {
        "id": str(cenario.responsavel), "nome": "Pedro Pedreiro", "cargo": "pedreiro",
    }
    assert "pedro@example.com" not in resposta.get_data(as_text=True)
    assert salva["marco_id"] == cenario.marco and salva["responsavel_id"] == cenario.responsavel
    # A mídia pertence à ocorrência, não a um avanço inventado.
    midia = ocorrencia["midias"][0]
    assert midia["ocorrencia_id"] == ocorrencia["id"] and "avanco_id" not in midia
    assert (midia["tipo"], midia["mime"], midia["visibilidade"]) == ("foto", "image/png", "privada")
    assert midia["tamanho"] == len(conteudos["png"])
    assert "referencia_externa" not in resposta.get_data(as_text=True)
    assert "public_id" not in resposta.get_data(as_text=True)
    assert database.tbl_midias.find_one({"_id": ObjectId(midia["id"])})["ocorrencia_id"] == ObjectId(
        ocorrencia["id"]
    )
    # Acesso protegido reaproveitado: metadados e conteúdo pelas rotas de mídia.
    assert client.get(f"/midias/{midia['id']}", headers=headers).get_json() == midia
    conteudo = client.get(midia["conteudo"], headers=headers)
    assert conteudo.status_code == 200 and conteudo.data == conteudos["png"]
    assert client.get(f"/ocorrencias/{ocorrencia['id']}", headers=headers).get_json() == ocorrencia


def test_formulario_sem_arquivo_registra_sem_tocar_no_provedor(
    client, headers, cenario, provedor
):
    resposta = client.post(cenario.registrar, headers=headers, **formulario(
        marco_id=str(cenario.marco), responsavel_id=""
    ))

    assert resposta.status_code == 201
    # Opcional enviado em branco equivale a ausente.
    assert resposta.get_json()["responsavel"] is None
    assert resposta.get_json()["midias"] == []
    provedor.upload.assert_not_called()


@pytest.mark.parametrize("chave,campo,status,codigo", [
    ("marco_alheio", "marco_id", 422, "MARCO_DE_OUTRA_OBRA"),
    ("ausente", "marco_id", 422, "MARCO_DE_OUTRA_OBRA"),
    ("id_invalido", "marco_id", 400, "ID_INVALIDO"),
    ("responsavel_alheio", "responsavel_id", 422, "RESPONSAVEL_SEM_VINCULO"),
    ("ausente", "responsavel_id", 422, "RESPONSAVEL_SEM_VINCULO"),
    ("id_invalido", "responsavel_id", 400, "ID_INVALIDO"),
])
def test_ct66_vinculo_invalido_nao_registra_ocorrencia(
    client, headers, database, cenario, chave, campo, status, codigo
):
    valores = {
        "marco_alheio": str(cenario.marco_alheio),
        "responsavel_alheio": str(cenario.responsavel_alheio),
        "ausente": str(ObjectId()),
        "id_invalido": "nao-e-um-identificador",
    }
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers,
                           json={**MINIMA, campo: valores[chave]})

    assert resposta.status_code == status
    assert resposta.get_json()["codigo"] == codigo
    assert resposta.get_json()["campos"] == [campo]
    assert database.tbl_ocorrencias.count_documents({}) == 0
    assert snapshot(database) == antes


def test_ct66_marco_de_outra_obra_recusado_antes_do_upload(
    client, headers, database, cenario, provedor, conteudos
):
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers, **formulario(
        conteudos["png"], marco_id=str(cenario.marco_alheio)
    ))

    assert resposta.status_code == 422
    assert resposta.get_json()["campos"] == ["marco_id"]
    # Vínculo é verificado antes de enviar qualquer arquivo ao provedor.
    provedor.upload.assert_not_called()
    assert provedor.objetos == {}
    assert snapshot(database) == antes


def test_obra_inexistente_ou_invalida_nao_registra(client, headers, database, cenario):
    antes = snapshot(database)

    ausente = client.post(f"/obras/{ObjectId()}/ocorrencias", headers=headers, json=MINIMA)
    invalida = client.post("/obras/nao-e-um-id/ocorrencias", headers=headers, json=MINIMA)

    assert ausente.status_code == 404 and ausente.get_json()["codigo"] == "OBRA_NAO_ENCONTRADA"
    assert invalida.status_code == 400 and invalida.get_json()["codigo"] == "ID_INVALIDO"
    assert snapshot(database) == antes


@pytest.mark.parametrize("mudanca,campo", [
    ({"titulo": AUSENTE}, "titulo"),
    ({"descricao": AUSENTE}, "descricao"),
    ({"estado": AUSENTE}, "estado"),
    ({"titulo": "   "}, "titulo"),
    ({"descricao": ""}, "descricao"),
    ({"titulo": None}, "titulo"),
    ({"descricao": 7}, "descricao"),
    ({"estado": "resolvida"}, "estado"),
    ({"estado": "aceita"}, "estado"),
    ({"estado": "ABERTA"}, "estado"),
    ({"estado": None}, "estado"),
    ({"aceitacao": "aceito de antemão"}, "aceitacao"),
    ({"autor": "outra construtora"}, "autor"),
    ({"data_registro": "2030-01-01"}, "data_registro"),
])
def test_ct67_campos_obrigatorios_e_estado_inicial(
    client, headers, database, cenario, mudanca, campo
):
    corpo = {**MINIMA, **mudanca}
    for chave, valor in mudanca.items():
        if valor is AUSENTE:
            corpo.pop(chave)
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers, json=corpo)

    assert resposta.status_code == 422
    assert campo in resposta.get_json()["campos"]
    assert resposta.get_json()["mensagem"]
    assert database.tbl_ocorrencias.count_documents({}) == 0
    assert snapshot(database) == antes


@pytest.mark.parametrize("corpo", [None, [], "texto", 7])
def test_corpo_nao_objeto_e_recusado(client, headers, database, cenario, corpo):
    antes = snapshot(database)
    opcoes = {} if corpo is None else {"json": corpo}

    resposta = client.post(cenario.registrar, headers=headers, **opcoes)

    assert resposta.status_code == 422 and resposta.get_json()["campos"] == ["corpo"]
    assert snapshot(database) == antes


def test_campo_desconhecido_no_formulario_e_recusado(
    client, headers, database, cenario, provedor, conteudos
):
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers, **formulario(
        **{"prioridade": "alta"}
    ))
    arquivo_fora = client.post(cenario.registrar, headers=headers, data={
        **COMPLETA, "evidencia": (BytesIO(conteudos["png"]), "laje.png"),
    }, content_type="multipart/form-data")

    assert resposta.status_code == 422 and "prioridade" in resposta.get_json()["campos"]
    assert arquivo_fora.status_code == 422 and "evidencia" in arquivo_fora.get_json()["campos"]
    provedor.upload.assert_not_called()
    assert snapshot(database) == antes


def test_midia_invalida_nao_registra_ocorrencia(client, headers, database, cenario, provedor):
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers, **formulario(b"isto-nao-e-uma-foto"))

    assert resposta.status_code == 422 and resposta.get_json()["campos"] == ["midias"]
    provedor.upload.assert_not_called()
    assert database.tbl_ocorrencias.count_documents({}) == 0
    assert snapshot(database) == antes


def test_falha_no_banco_nao_registra_e_remove_arquivos_enviados(
    client, headers, database, cenario, provedor, conteudos, monkeypatch
):
    def falhar(*args, **kwargs):
        raise PyMongoError("falha simulada com detalhe interno")

    monkeypatch.setattr(database.tbl_ocorrencias, "insert_one", falhar)
    antes = snapshot(database)

    resposta = client.post(cenario.registrar, headers=headers, **formulario(conteudos["png"]))

    assert resposta.status_code == 503
    assert "detalhe interno" not in resposta.get_data(as_text=True)
    # Nem ocorrência, nem mídia órfã, nem arquivo sem uso no provedor.
    assert snapshot(database) == antes
    assert database.tbl_ocorrencias.count_documents({}) == 0
    provedor.destroy.assert_called()
    assert provedor.objetos == {}


def test_limpeza_nao_confirmada_deixa_pendencia_rastreavel(
    client, headers, database, cenario, provedor, conteudos, monkeypatch, caplog
):
    def falhar(*args, **kwargs):
        raise PyMongoError("falha simulada")

    monkeypatch.setattr(database.tbl_ocorrencias, "insert_one", falhar)
    provedor.destroy.side_effect = RuntimeError("provedor indisponível")
    antes = snapshot(database)

    with caplog.at_level(logging.ERROR):
        resposta = client.post(cenario.registrar, headers=headers, **formulario(conteudos["png"]))

    assert resposta.status_code == 503
    assert resposta.get_json()["codigo"] == "LIMPEZA_PENDENTE"
    assert "pendente" in caplog.text
    assert snapshot(database) == antes


def test_vinculo_excluido_antes_da_gravacao_nao_registra(
    client, headers, database, cenario, monkeypatch
):
    from app.ocorrencias import repository

    original = repository.salvar

    def excluir_e_salvar(documento, midias):
        database.tbl_marcos.delete_one({"_id": cenario.marco})
        return original(documento, midias)

    monkeypatch.setattr(repository, "salvar", excluir_e_salvar)

    resposta = client.post(cenario.registrar, headers=headers,
                           json={**MINIMA, "marco_id": str(cenario.marco)})

    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "VINCULO_ALTERADO"
    assert database.tbl_ocorrencias.count_documents({}) == 0


def test_lista_vazia_difere_de_obra_inexistente(client, headers, cenario):
    vazia = client.get(cenario.listar, headers=headers)
    ausente = client.get(f"/obras/{ObjectId()}/ocorrencias", headers=headers)
    invalida = client.get("/obras/nao-e-um-id/ocorrencias", headers=headers)

    assert vazia.status_code == 200 and vazia.get_json() == {"ocorrencias": []}
    assert ausente.status_code == 404 and ausente.get_json()["codigo"] == "OBRA_NAO_ENCONTRADA"
    assert invalida.status_code == 400 and invalida.get_json()["codigo"] == "ID_INVALIDO"


def test_ocorrencia_devolvida_somente_no_contexto_correto(client, headers, database, cenario):
    desta = client.post(cenario.registrar, headers=headers, json=MINIMA).get_json()
    outra = client.post(f"/obras/{cenario.outra_obra}/ocorrencias", headers=headers,
                        json=MINIMA).get_json()

    assert client.get(cenario.listar, headers=headers).get_json() == {"ocorrencias": [desta]}
    assert client.get(f"/obras/{cenario.outra_obra}/ocorrencias",
                      headers=headers).get_json() == {"ocorrencias": [outra]}
    assert client.get(f"/ocorrencias/{ObjectId()}", headers=headers).status_code == 404
    assert client.get("/ocorrencias/nao-e-um-id", headers=headers).status_code == 400

    # Sem a obra não há contexto: a ocorrência órfã não é devolvida como válida.
    database.tbl_obras.delete_one({"_id": cenario.obra})
    assert client.get(f"/ocorrencias/{desta['id']}", headers=headers).status_code == 404
    assert client.get(f"/ocorrencias/{outra['id']}", headers=headers).status_code == 200


def test_marco_excluido_depois_nao_finge_vinculo_valido(client, headers, database, cenario):
    ocorrencia = client.post(cenario.registrar, headers=headers,
                             json={**MINIMA, "marco_id": str(cenario.marco)}).get_json()
    database.tbl_marcos.delete_one({"_id": cenario.marco})

    consultada = client.get(f"/ocorrencias/{ocorrencia['id']}", headers=headers)

    assert consultada.status_code == 200
    # A referência permanece, mas o nome não afirma um marco que não existe mais.
    assert consultada.get_json()["marco"] == {"id": str(cenario.marco), "nome": None}


def test_ct68_reinicio_mantem_estado_vinculos_e_midia(
    client, headers, database, cenario, provedor, conteudos
):
    minima = client.post(cenario.registrar, headers=headers, json=MINIMA).get_json()
    completa = client.post(cenario.registrar, headers=headers, **formulario(
        conteudos["png"],
        marco_id=str(cenario.marco),
        responsavel_id=str(cenario.responsavel),
    )).get_json()

    # Processo novo lendo o mesmo banco: nada depende do estado em memória.
    with isolated_app(database) as nova_app:
        novo_client = nova_app.test_client()
        lista = novo_client.get(cenario.listar, headers=headers)
        assert lista.status_code == 200
        assert lista.get_json() == {"ocorrencias": [minima, completa]}
        for ocorrencia in (minima, completa):
            detalhe = novo_client.get(f"/ocorrencias/{ocorrencia['id']}", headers=headers)
            assert detalhe.status_code == 200 and detalhe.get_json() == ocorrencia
        midia = novo_client.get(completa["midias"][0]["conteudo"], headers=headers)
        assert midia.status_code == 200 and midia.data == conteudos["png"]


@pytest.mark.parametrize("metodo,recurso", [
    ("post", "registrar"), ("get", "listar"), ("get", "detalhe"),
])
@pytest.mark.parametrize("sessao", ["ausente", "expirada", "revogada", "inativa"])
def test_ct03_rotas_exigem_sessao(
    app, client, headers, emitir_headers, account, database, cenario, provedor,
    metodo, recurso, sessao
):
    criada = client.post(cenario.registrar, headers=headers, json=MINIMA).get_json()
    caminhos = {"registrar": cenario.registrar, "listar": cenario.listar,
                "detalhe": f"/ocorrencias/{criada['id']}"}
    autenticar = headers
    if sessao == "ausente":
        autenticar = {}
    elif sessao == "expirada":
        autenticar = emitir_headers(expirado=True)
    elif sessao == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    else:
        with app.app_context():
            claims = decode_token(headers["Authorization"].split()[1])
        database.tbl_sessoes_revogadas.insert_one({"_id": claims["sessao_id"]})
    antes = snapshot(database)
    opcoes = {"json": COMPLETA} if metodo == "post" else {}

    resposta = getattr(client, metodo)(caminhos[recurso], headers=autenticar, **opcoes)

    assert resposta.status_code == 401
    # Nenhum dado devolvido e nenhum dado alterado.
    assert MINIMA["titulo"] not in resposta.get_data(as_text=True)
    assert snapshot(database) == antes
    provedor.upload.assert_not_called()


@pytest.mark.atlas
def test_ct68_ocorrencia_persiste_em_processo_novo(client, headers, database, cenario):
    """Atlas real e processo independente; confirma persistência além do Flask em memória."""
    criada = client.post(cenario.registrar, headers=headers,
                         json={**MINIMA, "marco_id": str(cenario.marco)})
    assert criada.status_code == 201
    ambiente = dict(
        os.environ,
        TEST_COLLECTION_PREFIX=database.prefixo,
        TEST_RESOURCE_PATH=f"/ocorrencias/{criada.get_json()['id']}",
    )

    resultado = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("restart_probe.py"))],
        env=ambiente, capture_output=True, text=True, timeout=30,
    )

    assert resultado.returncode == 0, "Falha ao consultar a ocorrência em processo novo"
    assert json.loads(resultado.stdout) == {"status": 200, "body": criada.get_json()}
