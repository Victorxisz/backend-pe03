"""Cadastro de avanços: cenários separados por responsabilidade."""
from unittest.mock import Mock

import pytest
from pymongo.errors import OperationFailure

from support import isolated_app, snapshot
from support_midias import config, conteudos


from support_avancos import backend, transacao_local, marco, dados

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
