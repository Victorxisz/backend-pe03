"""CT-31..36 por HTTP; MongoDB em memória e fronteira Cloudinary simulada."""

from contextlib import nullcontext
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bson import ObjectId
from cloudinary.exceptions import NotFound
from pymongo.errors import OperationFailure, PyMongoError
from werkzeug.datastructures import MultiDict

from support import isolated_app, snapshot
from support_midias import config, conteudos


@pytest.fixture
def backend(monkeypatch, config):
    for key, value in {
        "CLOUDINARY_CLOUD_NAME": config.cloud_name,
        "CLOUDINARY_API_KEY": config.api_key,
        "CLOUDINARY_API_SECRET": config.api_secret,
        "CLOUDINARY_FOLDER": config.pasta,
    }.items():
        monkeypatch.setenv(key, value)
    objects = {}

    def upload(stream, **options):
        data = stream.getvalue()
        objects[options["public_id"]] = data
        return {
            "public_id": options["public_id"],
            "bytes": len(data),
            "resource_type": options["resource_type"],
            "type": options["type"],
        }

    def destroy(**options):
        objects.pop(options["public_id"], None)
        return {"result": "ok"}

    def resource(**options):
        if options["public_id"] not in objects:
            raise NotFound("não encontrado")
        return {"public_id": options["public_id"]}

    upload_mock, destroy_mock = Mock(side_effect=upload), Mock(side_effect=destroy)
    monkeypatch.setattr("cloudinary.uploader.upload", upload_mock)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy_mock)
    monkeypatch.setattr("cloudinary.api.resource", resource)

    def baixar(url, timeout):
        public_id = parse_qs(urlparse(url).query)["public_id"][0]
        return BytesIO(objects[public_id])

    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", baixar)
    monkeypatch.setattr("urllib.request.urlopen", baixar)
    return objects, upload_mock, destroy_mock


@pytest.fixture
def transacao_local(app, database, monkeypatch):
    """Simulação de rollback: não comprova a atomicidade de um MongoDB real."""
    import db
    from mongomock.collection import Collection

    class Sessao:
        def with_transaction(self, callback):
            antes = snapshot(database)
            try:
                return callback(self)
            except Exception:
                for name in database.list_collection_names():
                    database[name].delete_many({})
                for name, documents in antes.items():
                    database[name].insert_many(documents)
                raise

    monkeypatch.setattr(
        db.cliente_mongo, "start_session", lambda: nullcontext(Sessao())
    )

    def sem_sessao(original):
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return original(*args, **kwargs)

        return executar

    for name in ("update_one", "insert_one", "insert_many"):
        monkeypatch.setattr(Collection, name, sem_sessao(getattr(Collection, name)))


@pytest.fixture
def marco(database):
    obra = database.tbl_obras.insert_one({"nome": "Casa fictícia"}).inserted_id
    return database.tbl_marcos.insert_one(
        {"obra_id": obra, "nome": "Fundação"}
    ).inserted_id


def dados(
    conteudo=None, extensao="png", data="2030-10-01", descricao="Trabalho realizado"
):
    form = [("data", data), ("descricao", descricao)]
    if conteudo is not None:
        form.append(("midias", (BytesIO(conteudo), "evidencia." + extensao)))
    return MultiDict(form)


@pytest.mark.parametrize(
    "extensao,tipo",
    [("png", "foto"), ("jpg", "foto"), ("mp4", "video"), ("pdf", "documento")],
)
def test_ct31_ct32_criar_e_consultar(
    client,
    headers,
    account,
    database,
    marco,
    backend,
    conteudos,
    transacao_local,
    extensao,
    tipo,
):
    # Preparação (fixtures e dados do cenário)
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos",
        headers=headers,
        data=dados(conteudos[extensao], extensao),
    )
    # Verificação
    assert response.status_code == 201
    assert "referencia_externa" not in response.get_data(as_text=True)
    resultado = response.get_json()
    assert response.headers["Location"] == f"/avancos/{resultado['id']}"
    assert resultado["estado"] == "rascunho" and resultado["autor"] == str(
        account["_id"]
    )
    assert (
        resultado["data"] == "2030-10-01"
        and resultado["descricao"] == "Trabalho realizado"
    )
    assert resultado["marco_id"] == str(marco)
    assert resultado["instante_registro"] == "2030-10-20T12:00:00+00:00"
    assert len(resultado["midias"]) == 1 and resultado["midias"][0]["tipo"] == tipo
    assert (
        database.tbl_avancos.count_documents({})
        == database.tbl_midias.count_documents({})
        == 1
    )
    assert (
        client.get(response.headers["Location"], headers=headers).get_json()
        == resultado
    )
    assert client.get(f"/marcos/{marco}/avancos", headers=headers).get_json() == {
        "avancos": [resultado]
    }


@pytest.mark.parametrize(
    "data,descricao,arquivo,campo",
    [
        ("", "Descrição", True, "data"),
        ("2030-02-30", "Descrição", True, "data"),
        ("10/10/2030", "Descrição", True, "data"),
        ("2030-10-01", " ", True, "descricao"),
        ("2030-10-01", "Descrição", False, "midias"),
    ],
)
def test_ct33_rejeita_rascunho_incompleto(
    client,
    headers,
    database,
    marco,
    backend,
    conteudos,
    transacao_local,
    data,
    descricao,
    arquivo,
    campo,
):
    # Preparação (fixtures e dados do cenário)
    antes = snapshot(database)
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos",
        headers=headers,
        data=dados(
            conteudos["png"] if arquivo else None, data=data, descricao=descricao
        ),
        content_type="multipart/form-data",
    )
    # Verificação
    assert response.status_code == 422 and response.get_json()["campos"] == [campo]
    assert snapshot(database) == antes
    backend[1].assert_not_called()


def test_ct34_arquivo_invalido_ou_excedido(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação (fixtures e dados do cenário)
    antes = snapshot(database)
    # Execução
    invalido = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(b"arquivo falso")
    )
    monkeypatch.setenv("MIDIA_FOTO_MAX_BYTES", "10")
    grande = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert invalido.status_code == 422 and grande.status_code == 413
    assert snapshot(database) == antes
    backend[1].assert_not_called()


def test_ct35_falha_upload_sem_registro(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação (fixtures e dados do cenário)
    antes = snapshot(database)
    backend[1].side_effect = OSError("falha fictícia")
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 503
    assert snapshot(database) == antes
    assert not backend[0]
    backend[2].assert_called_once()


def test_ct35_falha_gravacao_desfaz_lote(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação (fixtures e dados do cenário)
    from mongomock.collection import Collection

    antes = snapshot(database)
    original = Collection.insert_many

    def falhar_midias(colecao, documentos, *args, **kwargs):
        if colecao.name.endswith("tbl_midias"):
            raise PyMongoError("falha de teste")
        return original(colecao, documentos, *args, **kwargs)

    monkeypatch.setattr(Collection, "insert_many", falhar_midias)
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 500
    assert snapshot(database) == antes
    assert not backend[0]
    backend[2].assert_called_once()


def test_ct35_commit_indeterminado_preserva_midia(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação (fixtures e dados do cenário)
    from app.avancos import repository

    erro = OperationFailure(
        "resposta perdida", details={"errorLabels": ["UnknownTransactionCommitResult"]}
    )
    monkeypatch.setattr(repository, "salvar_com_midias", Mock(side_effect=erro))
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 503
    assert "verificação" in response.get_json()["mensagem"]
    assert len(backend[0]) == 1
    backend[2].assert_not_called()


def test_ct36_datas_nao_consecutivas(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação (fixtures e dados do cenário)
    # Execução
    for data in ("2030-01-01", "2030-01-12"):
        response = client.post(
            f"/marcos/{marco}/avancos",
            headers=headers,
            data=dados(conteudos["png"], data=data),
        )
        assert response.status_code == 201
    # Verificação
    assert {doc["data"] for doc in database.tbl_avancos.find()} == {
        "2030-01-01",
        "2030-01-12",
    }


def test_marco_inexistente_nao_faz_upload(
    client, headers, database, backend, conteudos, transacao_local
):
    # Preparação (fixtures e dados do cenário)
    antes = snapshot(database)
    # Execução
    response = client.post(
        f"/marcos/{ObjectId()}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 404
    assert response.get_json()["campos"] == ["marco_id"]
    backend[1].assert_not_called()
    assert snapshot(database) == antes


def test_nova_instancia_consulta_rascunho(
    client, headers, account, database, marco, backend, conteudos, transacao_local
):
    # Preparação (fixtures e dados do cenário)
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 201
    with isolated_app(database) as app:
        app.config["CONSTRUTORA_ID"] = str(account["_id"])
        novo_cliente = app.test_client()
        recuperado = novo_cliente.get(response.headers["Location"], headers=headers)
        arquivo = novo_cliente.get(
            recuperado.get_json()["midias"][0]["conteudo"], headers=headers
        )
    assert recuperado.status_code == 200
    assert recuperado.get_json() == response.get_json()
    assert arquivo.status_code == 200 and arquivo.data == conteudos["png"]


def test_ct35_limpeza_falha_sinaliza_pendencia(
    client,
    headers,
    database,
    marco,
    backend,
    conteudos,
    transacao_local,
    monkeypatch,
    caplog,
):
    # Preparação (fixtures e dados do cenário)
    from app.avancos import repository

    antes = snapshot(database)
    backend[2].side_effect = OSError("falha fictícia de remoção")
    monkeypatch.setattr(
        repository,
        "salvar_com_midias",
        Mock(side_effect=PyMongoError("falha de banco")),
    )
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 503
    assert "pendentes" in response.get_json()["mensagem"]
    assert "referências pendentes" in caplog.text
    assert len(backend[0]) == 1
    depois = snapshot(database)
    pendentes = depois.pop("tbl_uploads_pendentes")
    assert len(pendentes) == 1 and pendentes[0]["estado"] == "pendente"
    assert len(pendentes[0]["referencias"]) == 1
    assert depois == antes


def test_marco_excluido_durante_gravacao_compensa_upload(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação (fixtures e dados do cenário)
    from app.avancos import repository

    antes = snapshot(database)
    monkeypatch.setattr(
        repository, "salvar_com_midias", Mock(side_effect=repository.MarcoRemovido())
    )
    # Execução
    response = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )
    # Verificação
    assert response.status_code == 404
    assert not backend[0]
    assert snapshot(database) == antes


@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("post", "/marcos/{}/avancos"),
        ("get", "/marcos/{}/avancos"),
        ("get", "/avancos/{}"),
    ],
)
def test_acesso_sem_sessao(
    client, database, marco, backend, conteudos, transacao_local, metodo, caminho
):
    # Preparação (fixtures e dados do cenário)
    antes = snapshot(database)
    kwargs = {"data": dados(conteudos["png"])} if metodo == "post" else {}
    # Execução
    response = getattr(client, metodo)(caminho.format(marco), **kwargs)
    # Verificação
    assert response.status_code == 401
    backend[1].assert_not_called()
    assert snapshot(database) == antes


def test_lotes_com_multiplas_midias(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação (fixtures e dados do cenário)
    form = dados(conteudos["png"])
    form.add("midias", (BytesIO(conteudos["pdf"]), "planta.pdf"))
    # Execução
    response = client.post(f"/marcos/{marco}/avancos", headers=headers, data=form)
    # Verificação
    assert response.status_code == 201
    assert {m["tipo"] for m in response.get_json()["midias"]} == {"foto", "documento"}
    assert database.tbl_midias.count_documents({}) == 2


@pytest.mark.parametrize("campo", ["data", "descricao"])
def test_ct33_campo_ausente(
    client, headers, database, marco, backend, conteudos, transacao_local, campo
):
    # Preparação
    antes = snapshot(database)
    form = dados(conteudos["png"])
    form.pop(campo)

    # Execução
    resposta = client.post(f"/marcos/{marco}/avancos", headers=headers, data=form)

    # Verificação
    assert resposta.status_code == 422
    assert resposta.get_json()["campos"] == [campo]
    backend[1].assert_not_called()
    assert snapshot(database) == antes


@pytest.mark.parametrize(
    "identifier,status", [("invalido", 400), ("507f1f77bcf86cd799439099", 404)]
)
def test_consulta_avanco_invalido_ou_inexistente(
    client, headers, database, identifier, status
):
    # Preparação
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{identifier}", headers=headers)

    # Verificação
    assert resposta.status_code == status
    assert resposta.get_json()["campos"] == ["avanco_id"]
    assert snapshot(database) == antes


def test_ct35_segundo_upload_falha_compensa_primeiro(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    antes = snapshot(database)
    enviar = backend[1].side_effect
    contador = 0

    def falhar_segundo(stream, **opcoes):
        nonlocal contador
        contador += 1
        if contador == 2:
            raise TimeoutError("falha fictícia")
        return enviar(stream, **opcoes)

    backend[1].side_effect = falhar_segundo
    form = dados(conteudos["png"])
    form.add("midias", (BytesIO(conteudos["pdf"]), "planta.pdf"))

    # Execução
    resposta = client.post(f"/marcos/{marco}/avancos", headers=headers, data=form)

    # Verificação
    assert resposta.status_code == 503
    assert backend[2].call_count == 2  # Segundo envio incerto e primeiro confirmado.
    assert not backend[0]
    assert snapshot(database) == antes


def test_ct35_configuracao_invalida_nao_grava(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação
    antes = snapshot(database)
    monkeypatch.setenv("MIDIA_FOTO_MAX_BYTES", "-1")

    # Execução
    resposta = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )

    # Verificação
    assert resposta.status_code == 503
    assert "configurado" in resposta.get_json()["mensagem"]
    backend[1].assert_not_called()
    assert snapshot(database) == antes


def test_ct35_processo_interrompido_preserva_intencao_e_permite_reconciliacao(
    app, client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação: o provedor grava e o processo termina antes de receber a resposta.
    from app.avancos.reconciliacao import reconciliar
    from app.integracoes.armazenamento import ArmazenamentoCloudinary

    enviar = backend[1].side_effect

    def interromper(stream, **opcoes):
        enviar(stream, **opcoes)
        raise SystemExit("interrupção simulada")

    backend[1].side_effect = interromper

    # Execução
    with pytest.raises(SystemExit):
        client.post(
            f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
        )
    operacao = database.tbl_uploads_pendentes.find_one()

    # Verificação
    assert operacao["estado"] == "pendente"
    assert len(operacao["referencias"]) == len(backend[0]) == 1
    assert database.tbl_avancos.count_documents({}) == 0
    with pytest.raises(ValueError, match="Pare a aplicação"):
        reconciliar(operacao["_id"], ArmazenamentoCloudinary())
    assert (
        reconciliar(operacao["_id"], ArmazenamentoCloudinary(), aplicacao_parada=True)
        == "limpa"
    )
    assert not backend[0]
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "limpa"
    assert (
        reconciliar(operacao["_id"], ArmazenamentoCloudinary(), aplicacao_parada=True)
        == "limpa"
    )


def test_ct31_nao_reconsulta_banco_apos_confirmar_criacao(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação
    from app.avancos import repository

    consulta = Mock(side_effect=PyMongoError("leitura indisponível"))
    monkeypatch.setattr(repository, "consultar_midias", consulta)

    # Execução
    resposta = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )

    # Verificação
    assert resposta.status_code == 201
    assert len(resposta.get_json()["midias"]) == 1
    consulta.assert_not_called()
    assert (
        database.tbl_avancos.count_documents({})
        == database.tbl_midias.count_documents({})
        == 1
    )


def test_ct31_repeticao_idempotente_e_chave_com_outros_dados(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    auth = {**headers, "Idempotency-Key": "cadastro-ficticio-001"}
    path = f"/marcos/{marco}/avancos"

    # Execução
    primeira = client.post(path, headers=auth, data=dados(conteudos["png"]))
    repetida = client.post(path, headers=auth, data=dados(conteudos["png"]))
    diferente = client.post(
        path, headers=auth, data=dados(conteudos["png"], descricao="Outra")
    )

    # Verificação
    assert primeira.status_code == repetida.status_code == 201
    assert primeira.get_json() == repetida.get_json()
    assert diferente.status_code == 409
    assert diferente.get_json()["campos"] == ["Idempotency-Key"]
    assert (
        database.tbl_avancos.count_documents({})
        == database.tbl_midias.count_documents({})
        == 1
    )
    assert backend[1].call_count == 1
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "concluida"


def test_ct35_nao_repete_operacao_de_resultado_desconhecido(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação
    from app.avancos import repository

    monkeypatch.setattr(
        repository,
        "salvar_com_midias",
        Mock(
            side_effect=OperationFailure(
                "falha fictícia",
                details={"errorLabels": ["UnknownTransactionCommitResult"]},
            )
        ),
    )
    auth = {**headers, "Idempotency-Key": "operacao-desconhecida"}
    path = f"/marcos/{marco}/avancos"

    # Execução
    primeira = client.post(path, headers=auth, data=dados(conteudos["png"]))
    repetida = client.post(path, headers=auth, data=dados(conteudos["png"]))

    # Verificação
    assert primeira.status_code == 503 and repetida.status_code == 409
    assert backend[1].call_count == 1
    assert len(database.tbl_uploads_pendentes.find_one()["referencias"]) == 1
    backend[2].assert_not_called()


def test_ct34_limite_quantidade_e_tamanho_total(
    client, headers, app, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    antes = snapshot(database)
    form = dados(conteudos["png"])
    for numero in range(5):
        form.add("midias", (BytesIO(conteudos["png"]), f"foto{numero}.png"))

    # Execução
    muitos = client.post(f"/marcos/{marco}/avancos", headers=headers, data=form)
    app.config["UC09_MAX_REQUEST_BYTES"] = 100
    grande = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )

    # Verificação
    assert muitos.status_code == grande.status_code == 413
    assert muitos.get_json()["campos"] == grande.get_json()["campos"] == ["midias"]
    assert snapshot(database) == antes
    backend[1].assert_not_called()


def test_ct31_repeticao_apos_interrupcao_depois_do_commit(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação
    from app.avancos import repository

    salvar = repository.salvar_com_midias

    def interromper_apos_commit(*args):
        salvar(*args)
        raise SystemExit("resposta perdida")

    monkeypatch.setattr(repository, "salvar_com_midias", interromper_apos_commit)
    path = f"/marcos/{marco}/avancos"
    auth = {**headers, "Idempotency-Key": "resposta-perdida"}

    # Execução
    with pytest.raises(SystemExit):
        client.post(path, headers=auth, data=dados(conteudos["png"]))
    resposta = client.post(path, headers=auth, data=dados(conteudos["png"]))

    # Verificação
    assert resposta.status_code == 201
    assert database.tbl_avancos.count_documents({}) == 1
    assert database.tbl_midias.count_documents({}) == 1
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "concluida"
    assert backend[1].call_count == 1
    backend[2].assert_not_called()


def test_reconciliacao_nao_remove_midia_de_avanco_existente(
    app, database, backend, marco
):
    # Preparação
    from app.avancos.reconciliacao import reconciliar
    from app.integracoes.armazenamento import ArmazenamentoCloudinary

    avanco_id = database.tbl_avancos.insert_one({"marco_id": marco}).inserted_id
    operacao_id = "a" * 64
    database.tbl_uploads_pendentes.insert_one(
        {
            "_id": operacao_id,
            "estado": "pendente",
            "avanco_id": avanco_id,
            "referencias": [{}],
        }
    )

    # Execução e verificação
    with pytest.raises(ValueError, match="Avanço encontrado"):
        reconciliar(operacao_id, ArmazenamentoCloudinary(), aplicacao_parada=True)
    backend[2].assert_not_called()
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "pendente"


def test_ct35_falha_ao_fechar_sessao_apos_commit_nao_apaga_midia(
    client, headers, database, marco, backend, conteudos, transacao_local, monkeypatch
):
    # Preparação
    import db

    iniciar = db.cliente_mongo.start_session

    class SessaoComErroAoFechar:
        def __enter__(self):
            self.contexto = iniciar()
            return self.contexto.__enter__()

        def __exit__(self, tipo, valor, traceback):
            self.contexto.__exit__(tipo, valor, traceback)
            raise PyMongoError("falha fictícia ao encerrar sessão")

    monkeypatch.setattr(db.cliente_mongo, "start_session", SessaoComErroAoFechar)

    # Execução
    resposta = client.post(
        f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"])
    )

    # Verificação
    assert resposta.status_code == 201
    assert (
        database.tbl_avancos.count_documents({})
        == database.tbl_midias.count_documents({})
        == 1
    )
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "concluida"
    assert len(backend[0]) == 1
    backend[2].assert_not_called()


def test_integracao_criacao_exclusao_remove_midia_apesar_do_diario(client, headers, database, marco, backend, conteudos, transacao_local):
    # Preparação e execução
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    resposta = client.delete(criado.headers["Location"], headers=headers)

    # Verificação
    assert resposta.status_code == 204
    assert database.tbl_avancos.count_documents({}) == 0
    assert database.tbl_midias.count_documents({}) == 0
    assert not backend[0]
    backend[2].assert_called_once()


def test_avanco_com_exclusao_pendente_nao_aparece_nas_consultas(client, headers, database, marco, backend, conteudos, transacao_local):
    # Preparação
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    database.tbl_avancos.update_one({"_id": ObjectId(criado.get_json()["id"])}, {"$set": {"estado": "exclusao_pendente"}})

    # Execução
    detalhe = client.get(criado.headers["Location"], headers=headers)
    lista = client.get(f"/marcos/{marco}/avancos", headers=headers)

    # Verificação
    assert detalhe.status_code == 404
    assert lista.status_code == 200 and lista.get_json()["avancos"] == []


def test_exclusao_preserva_arquivo_referenciado_por_upload_pendente(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    referencia = database.tbl_midias.find_one()["referencia_externa"]
    database.tbl_uploads_pendentes.insert_one({
        "_id": "b" * 64, "avanco_id": ObjectId(), "estado": "pendente", "referencias": [referencia]
    })

    # Execução
    resposta = client.delete(criado.headers["Location"], headers=headers)

    # Verificação
    assert resposta.status_code == 204
    assert referencia["public_id"] in backend[0]
    backend[2].assert_not_called()


def test_limpeza_considera_historico_mas_ignora_diario_concluido(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    from app.avancos import repository

    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    midia = database.tbl_midias.find_one()
    referencia = midia["referencia_externa"]
    database.tbl_midias.delete_one({"_id": midia["_id"]})
    historico = database.tbl_versoes.insert_one({"anterior": {"referencia_externa": referencia}})

    # Execução e verificação
    assert repository.referencia_em_uso(referencia)
    database.tbl_versoes.delete_one({"_id": historico.inserted_id})
    assert not repository.referencia_em_uso(referencia)
