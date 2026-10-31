"""Cadastro de avanços: cenários separados por responsabilidade."""
from io import BytesIO
from unittest.mock import Mock

import pytest
from pymongo.errors import OperationFailure, PyMongoError

from support import isolated_app, snapshot
from support_midias import config, conteudos


from support_avancos import backend, transacao_local, marco, dados

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
    assert response.status_code == 503
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
