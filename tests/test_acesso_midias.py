"""Integração UC-08: envio Cloudinary, referência persistida e leitura protegida."""

import os
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from bson import ObjectId
from cloudinary.exceptions import NotFound
from flask_jwt_extended import decode_token
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot
from support_midias import arquivo, config, conteudos

AVANCO_ID = "507f1f77bcf86cd799439011"
MIDIA_ID = "507f1f77bcf86cd799439012"
LISTA = "/avancos/{}/midias"
DETALHE = "/midias/{}"
CONTEUDO = "/midias/{}/conteudo"


@pytest.fixture
def avanco(database, obra, account):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    marco_id = database.tbl_marcos.insert_one({"obra_id": obra_id, "nome": "Fundação"}).inserted_id
    documento = {"_id": ObjectId(AVANCO_ID), "marco_id": marco_id,
                 "descricao": "Concretagem", "estado": "rascunho", "autor": str(account["_id"])}
    database.tbl_avancos.insert_one(documento)
    return documento


@pytest.fixture
def backend(monkeypatch, config):
    # Simula somente a fronteira externa: os serviços e o MongoDB em memória são reais.
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": config.cloud_name,
                         "CLOUDINARY_API_KEY": config.api_key,
                         "CLOUDINARY_API_SECRET": config.api_secret,
                         "CLOUDINARY_FOLDER": config.pasta}.items():
        monkeypatch.setenv(chave, valor)
    objetos = {}
    def enviar(stream, **opcoes):
        conteudo = stream.getvalue()
        objetos[opcoes["public_id"]] = conteudo
        return {"public_id": opcoes["public_id"], "bytes": len(conteudo),
                "resource_type": opcoes["resource_type"], "type": opcoes["type"]}
    def consultar(**opcoes):
        if opcoes["public_id"] not in objetos:
            raise NotFound("objeto ausente")
        return {"public_id": opcoes["public_id"]}
    def remover(**opcoes):
        objetos.pop(opcoes["public_id"], None)
        return {"result": "ok"}
    def baixar(url, timeout):
        public_id = parse_qs(urlparse(url).query)["public_id"][0]
        return BytesIO(objetos[public_id])
    upload, resource, destroy, download = [Mock(side_effect=f) for f in (enviar, consultar, remover, baixar)]
    monkeypatch.setattr("cloudinary.uploader.upload", upload)
    monkeypatch.setattr("cloudinary.api.resource", resource)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", download)
    # Uma nova instância Flask reimporta o adaptador; a fronteira HTTP continua simulada.
    monkeypatch.setattr("urllib.request.urlopen", download)
    return SimpleNamespace(objetos=objetos, upload=upload, resource=resource, destroy=destroy, download=download)


@pytest.fixture
def enviar_midia(app, database, avanco, backend, conteudos, config):
    from app.avancos.midias import ServicoMidias
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    def enviar(extensao="png", avanco_id=None):
        def salvar(metadados):
            documento = {**metadados[0], "_id": ObjectId(),
                         "avanco_id": avanco["_id"] if avanco_id is None else avanco_id,
                         "data_envio": datetime.now(timezone.utc)}
            database.tbl_midias.insert_one(documento)
            return documento
        servico = ServicoMidias(ArmazenamentoCloudinary(config))
        return servico.executar_com_midias([arquivo(conteudos[extensao], "evidencia." + extensao)], salvar)
    return enviar


@pytest.mark.parametrize("extensao,mime", [("jpg", "image/jpeg"), ("png", "image/png"), ("mp4", "video/mp4"), ("pdf", "application/pdf")])
def test_ct31_ct32_envio_persistencia_e_acesso_protegido(client, headers, database, avanco, enviar_midia, conteudos, extensao, mime):
    # Preparação: o documento contém exatamente a referência gerada pelo upload.
    midia = enviar_midia(extensao)
    before = snapshot(database)
    # Execução
    lista = client.get(LISTA.format(avanco["_id"]), headers=headers)
    detalhe = client.get(DETALHE.format(midia["_id"]), headers=headers)
    conteudo = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    # Verificação
    assert lista.status_code == detalhe.status_code == conteudo.status_code == 200
    assert lista.get_json()["midias"] == [detalhe.get_json()]
    assert detalhe.get_json()["mime"] == detalhe.get_json()["formato"] == mime
    assert detalhe.get_json()["conteudo"] == CONTEUDO.format(midia["_id"])
    assert conteudo.data == conteudos[extensao]
    assert conteudo.headers["Content-Type"].startswith(mime)
    assert "Location" not in conteudo.headers
    assert conteudo.headers["Cache-Control"] == "private, no-store"
    assert conteudo.headers["X-Content-Type-Options"] == "nosniff"
    assert snapshot(database) == before


@pytest.mark.parametrize("caminho", [LISTA, DETALHE, CONTEUDO])
@pytest.mark.parametrize("sessao", ["ausente", "expirada", "revogada", "inativa"])
def test_ct03_sessao_invalida_nao_chega_ao_provedor(app, client, headers, emitir_headers, account, database, avanco, enviar_midia, backend, caminho, sessao):
    # Preparação
    midia = enviar_midia()
    autenticar = headers
    if sessao == "ausente":
        autenticar = {}
    elif sessao == "expirada":
        autenticar = emitir_headers(expirado=True)
    elif sessao == "revogada":
        with app.app_context():
            claims = decode_token(headers["Authorization"].split()[1])
        database.tbl_sessoes_revogadas.insert_one({"_id": claims["sessao_id"]})
    else:
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    before = snapshot(database)
    alvo = avanco["_id"] if caminho == LISTA else midia["_id"]
    # Execução
    response = client.get(caminho.format(alvo), headers=autenticar)
    # Verificação
    assert response.status_code == 401
    backend.resource.assert_not_called()
    backend.download.assert_not_called()
    assert "referencia_externa" not in response.get_data(as_text=True)
    assert snapshot(database) == before


def test_ct31_metadados_nao_expoem_provedor(client, headers, enviar_midia, database, config):
    # Preparação
    midia = enviar_midia()
    database.tbl_midias.update_one({"_id": midia["_id"]}, {"$set": {"api_secret": config.api_secret, "url": "https://provedor.example/objeto"}})
    # Execução
    response = client.get(DETALHE.format(midia["_id"]), headers=headers)
    # Verificação
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for proibido in ("referencia_externa", "public_id", "provedor", config.api_secret, "://"):
        assert proibido not in body


def test_ct31_lista_respeita_vinculo_e_recusa_orfa(client, headers, database, avanco, enviar_midia, backend):
    # Preparação
    midia = enviar_midia()
    outro = database.tbl_avancos.insert_one({"estado": "rascunho"}).inserted_id
    orfa = enviar_midia(avanco_id=ObjectId())
    # Execução
    vizinho = client.get(LISTA.format(outro), headers=headers)
    detalhe = client.get(DETALHE.format(orfa["_id"]), headers=headers)
    conteudo = client.get(CONTEUDO.format(orfa["_id"]), headers=headers)
    # Verificação
    assert vizinho.status_code == 200 and vizinho.get_json() == {"midias": []}
    assert detalhe.status_code == conteudo.status_code == 404
    assert str(midia["_id"]) not in vizinho.get_data(as_text=True)
    backend.download.assert_not_called()


@pytest.mark.parametrize("caminho", [LISTA, DETALHE, CONTEUDO])
@pytest.mark.parametrize("identificador,status", [("invalido", 400), (MIDIA_ID, 404)])
def test_ct31_id_invalido_ou_registro_ausente(client, headers, caminho, identificador, status):
    # Preparação: nenhum avanço nem mídia com o ID pedido.
    # Execução
    response = client.get(caminho.format(identificador), headers=headers)
    # Verificação
    assert response.status_code == status
    assert response.get_json()["codigo"] in {"ID_INVALIDO", "MIDIA_NAO_ENCONTRADA", "AVANCO_NAO_ENCONTRADO"}


@pytest.mark.parametrize("falha,codigo", [("ausente", "CONTEUDO_AUSENTE_NO_PROVEDOR"), ("rede", "PROVEDOR_INDISPONIVEL"), ("truncado", "PROVEDOR_INDISPONIVEL")])
def test_ct110_falha_cloudinary_diferente_de_midia_inexistente(client, headers, enviar_midia, backend, falha, codigo):
    # Preparação
    midia = enviar_midia()
    if falha == "ausente":
        backend.objetos.clear()
    elif falha == "rede":
        backend.resource.side_effect = OSError("detalhe privado do provedor")
    else:
        backend.objetos[midia["referencia_externa"]["public_id"]] = b"curto"
    # Execução
    response = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    metadata = client.get(DETALHE.format(midia["_id"]), headers=headers)
    # Verificação
    assert response.status_code == 502
    assert response.get_json()["codigo"] == codigo
    assert metadata.status_code == 200
    assert "privado" not in response.get_data(as_text=True)


@pytest.mark.parametrize("metodo,caminho", [("consultar_midias", LISTA), ("buscar_midia_por_id", DETALHE)])
def test_ct31_falha_banco_sem_expor_conexao(client, headers, database, avanco, metodo, caminho):
    # Preparação
    with patch("app.avancos.repository." + metodo, side_effect=PyMongoError("conexão privada")):
        # Execução
        response = client.get(caminho.format(avanco["_id"]), headers=headers)
    # Verificação
    assert response.status_code == 500
    assert response.get_json()["codigo"] == "FALHA_NO_BANCO"
    assert "privada" not in response.get_data(as_text=True)


@pytest.mark.parametrize("referencia", [None, "referencia-local-antiga", {"provedor": "local"}, {"provedor": "cloudinary", "public_id": "outro-projeto/arquivo"}])
def test_ct31_referencia_incompativel_nao_acessa_provedor(client, headers, database, enviar_midia, backend, referencia):
    # Preparação
    midia = enviar_midia()
    database.tbl_midias.update_one({"_id": midia["_id"]}, {"$set": {"referencia_externa": referencia}})
    # Execução
    response = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    # Verificação
    assert response.status_code == 502
    assert response.get_json()["codigo"] == "REFERENCIA_INVALIDA"
    backend.resource.assert_not_called()
    backend.download.assert_not_called()


def test_ct45_nova_aplicacao_recupera_referencia_cloudinary(client, headers, database, enviar_midia, conteudos):
    # Preparação
    midia = enviar_midia()
    # Execução: recarrega Flask; o banco e o provedor externo simulado permanecem.
    with isolated_app(database) as nova_app:
        response = nova_app.test_client().get(CONTEUDO.format(midia["_id"]), headers=headers)
    # Verificação
    assert response.status_code == 200
    assert response.data == conteudos["png"]


def test_ct03_head_do_arquivo_tambem_exige_sessao(client, enviar_midia, backend):
    # Preparação
    midia = enviar_midia()
    # Execução
    response = client.head(CONTEUDO.format(midia["_id"]))
    # Verificação
    assert response.status_code == 401
    backend.download.assert_not_called()


def test_ct32_video_suporta_range_autenticado(client, headers, enviar_midia, conteudos):
    # Preparação
    midia = enviar_midia("mp4")
    # Execução
    response = client.get(CONTEUDO.format(midia["_id"]), headers={**headers, "Range": "bytes=0-9"})
    # Verificação
    assert response.status_code == 206
    assert response.data == conteudos["mp4"][:10]


def test_ct35_falha_ao_salvar_nao_deixa_midia_acessivel(app, database, backend, conteudos, config):
    # Preparação
    from app.avancos.midias import ServicoMidias
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    salvar = Mock(side_effect=PyMongoError("falha fictícia do banco"))
    servico = ServicoMidias(ArmazenamentoCloudinary(config))
    # Execução
    with pytest.raises(PyMongoError):
        servico.executar_com_midias([arquivo(conteudos["png"])], salvar)
    # Verificação
    assert backend.objetos == {}
    assert database.tbl_midias.count_documents({}) == 0
    backend.destroy.assert_called_once()


@pytest.mark.cloudinary
@pytest.mark.skipif(os.getenv("RUN_CLOUDINARY_TESTS") != "1", reason="Exige Cloudinary exclusivo de teste e RUN_CLOUDINARY_TESTS=1")
@pytest.mark.parametrize("extensao", ["png", "mp4", "pdf"])
def test_ct109_envio_cloudinary_real_e_rota_protegida(app, account, avanco, database, conteudos, monkeypatch, extensao):
    # Sem a fixture client/clock: o timestamp deve ser o relógio real do provedor.
    from app.config import ConfiguracaoArmazenamento
    from app.avancos.midias import ServicoMidias
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    from construtora import gerar_tokens_construtora
    cfg = ConfiguracaoArmazenamento.do_ambiente(prefixo="TEST_")
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": cfg.cloud_name, "CLOUDINARY_API_KEY": cfg.api_key,
                         "CLOUDINARY_API_SECRET": cfg.api_secret, "CLOUDINARY_FOLDER": cfg.pasta}.items():
        monkeypatch.setenv(chave, valor)
    storage = ArmazenamentoCloudinary(cfg)
    enviados = []
    def salvar(metadata):
        enviados.extend(metadata)
        doc = {**metadata[0], "avanco_id": avanco["_id"]}
        doc["_id"] = database.tbl_midias.insert_one(doc).inserted_id
        return doc
    try:
        # Execução
        midia = ServicoMidias(storage).executar_com_midias([arquivo(conteudos[extensao])], salvar)
        with app.app_context():
            token, _ = gerar_tokens_construtora(account["_id"])
        client = app.test_client()
        response = client.get(CONTEUDO.format(midia["_id"]), headers={"Authorization": "Bearer " + token})
        denied = client.get(CONTEUDO.format(midia["_id"]))
        # Verificação
        assert response.status_code == 200
        assert response.data == conteudos[extensao]
        assert denied.status_code == 401
    finally:
        for metadata in enviados:
            storage.remover(metadata["referencia_externa"])
