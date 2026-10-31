"""Fixtures e formulários compartilhados; não contém casos de teste."""
from contextlib import nullcontext
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from cloudinary.exceptions import NotFound
from werkzeug.datastructures import MultiDict

from support import isolated_app, snapshot
from support_midias import config, conteudos


from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

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


@pytest.fixture
def camadas(app):
    # Imports após isolated_app: usa os módulos ligados ao banco desta execução.
    from app.avancos import repository, service, validacoes
    from app.avancos.midias import ErroMidia, ServicoMidias
    from app.avancos.revisoes import ConflitoRascunho
    from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
    from app.mudanças.ocorrencias.historico.service import consultar_previa

    return SimpleNamespace(
        repo=repository, service=service, validacoes=validacoes,
        ErroMidia=ErroMidia, ServicoMidias=ServicoMidias,
        ConflitoRascunho=ConflitoRascunho,
        ErroArmazenamento=ErroArmazenamento, ErroLimpeza=ErroLimpeza,
        consultar_previa=consultar_previa,
    )


@pytest.fixture
def transacao_local(app, database, monkeypatch, request):
    if request.config.getoption("--atlas"):
        return

    import db
    from mongomock.collection import Collection

    # Guarda as operações originais para restaurar o banco mesmo quando um
    # teste injeta uma falha de escrita na coleção.
    apagar = Collection.delete_many
    inserir = Collection.insert_many

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

    monkeypatch.setattr(
        db.cliente_mongo, "start_session", lambda: nullcontext(Sessao())
    )

    def sem_sessao(original):
        @wraps(original)
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return original(*args, **kwargs)
        return executar

    for nome in (
        "find", "find_one", "update_one", "insert_one", "insert_many",
        "delete_many", "delete_one", "find_one_and_update",
    ):
        monkeypatch.setattr(Collection, nome, sem_sessao(getattr(Collection, nome)))
