"""Cadastro de avanços: cenários separados por responsabilidade."""
from io import BytesIO
from unittest.mock import Mock

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot
from support_midias import config, conteudos


from support_avancos import backend, transacao_local, marco, dados

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
    assert client.get(f"/marcos/{marco}/avancos", headers=headers).get_json() == [resultado]


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
