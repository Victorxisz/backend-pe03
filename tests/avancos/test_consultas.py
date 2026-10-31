"""Cadastro de avanços: cenários separados por responsabilidade."""

import pytest
from bson import ObjectId

from support import isolated_app, snapshot
from support_midias import config, conteudos


from support_avancos import backend, transacao_local, marco, dados

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


def test_consulta_preserva_composicao_atual_no_formato_publico(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    documento = criado.json
    database.tbl_avancos.update_one({"_id": ObjectId(documento["id"])}, {
        "$set": {"midias": documento["midias"]},
    })
    antes = snapshot(database)

    resposta = client.get(criado.headers["Location"], headers=headers)

    assert resposta.status_code == 200
    assert resposta.json == documento
    assert snapshot(database) == antes
