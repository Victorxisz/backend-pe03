"""Conclusão e reabertura preservam histórico e usam o relógio do servidor."""

from unittest.mock import patch

import pytest
from freezegun import freeze_time
from pymongo.errors import PyMongoError

from support import snapshot
from support_obras import ID, seed

PATH = f"/obras/{ID}/estado"


def test_concluir_reabrir_e_concluir_novamente(client, headers, emitir_headers, database, obra, account):
    seed(database, obra)
    with freeze_time("2030-10-18 12:00:00"):
        concluida = client.patch(PATH, json={"estado": "concluída", "motivo": "Entrega"}, headers=emitir_headers())
    assert concluida.status_code == 200, concluida.get_json()
    assert concluida.get_json()["data_conclusao"] == "2030-10-18"
    with freeze_time("2030-10-21 12:00:00"):
        acesso = emitir_headers()
        reaberta = client.patch(PATH, json={"estado": "em andamento", "motivo": "Retrabalho"}, headers=acesso)
        novamente = client.patch(PATH, json={"estado": "concluída", "motivo": "Correções concluídas"}, headers=acesso)
    assert reaberta.status_code == novamente.status_code == 200
    assert reaberta.get_json()["data_conclusao"] is None
    assert novamente.get_json()["data_conclusao"] == "2030-10-21"
    historico = novamente.get_json()["historico_estados"]
    assert len(historico) == 3
    assert historico[0]["valor_novo"]["data_conclusao"] == "2030-10-18"
    assert all(evento["autor"] == str(account["_id"]) for evento in historico)
    assert client.get(f"/obras/{ID}", headers=headers).get_json() == novamente.get_json()


@pytest.mark.parametrize("dados", [None, {}, {"estado": "concluída"},
    {"estado": "concluída", "motivo": ""}, {"estado": "inválido", "motivo": "Teste"},
    {"estado": "concluída", "motivo": "Teste", "data_conclusao": "2000-01-01"}])
def test_dados_invalidos_preservam_obra_e_historico(client, headers, database, obra, dados):
    seed(database, obra)
    antes = snapshot(database)
    resposta = client.patch(PATH, json=dados, headers=headers)
    assert resposta.status_code == 422
    assert snapshot(database) == antes


def test_repetir_conclusao_nao_altera_data_nem_duplica_evento(client, headers, database, obra):
    seed(database, obra)
    dados = {"estado": "concluída", "motivo": "Entrega"}
    primeira = client.patch(PATH, json=dados, headers=headers)
    antes = snapshot(database)
    segunda = client.patch(PATH, json=dados, headers=headers)
    assert primeira.get_json() == segunda.get_json()
    assert snapshot(database) == antes


def test_falha_na_escrita_nao_deixa_estado_sem_historico(client, headers, database, obra):
    seed(database, obra)
    antes = snapshot(database)
    with patch.object(database.tbl_obras, "find_one_and_update", side_effect=PyMongoError("falha interna")):
        resposta = client.patch(PATH, json={"estado": "concluída", "motivo": "Entrega"}, headers=headers)
    assert resposta.status_code == 500
    assert snapshot(database) == antes


def test_conclusao_exige_sessao(client, database, obra):
    seed(database, obra)
    antes = snapshot(database)
    assert client.patch(PATH, json={"estado": "concluída", "motivo": "Entrega"}).status_code == 401
    assert snapshot(database) == antes


def test_estado_alterado_concorrentemente_nao_recebe_evento_antigo(client, headers, database, obra):
    from app.obras import repository

    seed(database, obra)
    original = repository.salvar_estado_com_historico

    def gravar_apos_concorrencia(documento, evento):
        database.tbl_obras.update_one({"_id": documento["_id"]},
                                     {"$set": {"estado": "suspensa"}, "$inc": {"revisao_estado": 1}})
        return original(documento, evento)

    with patch.object(repository, "salvar_estado_com_historico", side_effect=gravar_apos_concorrencia):
        resposta = client.patch(PATH, json={"estado": "concluída", "motivo": "Entrega"}, headers=headers)
    assert resposta.status_code == 409
    salvo = database.tbl_obras.find_one()
    assert salvo["estado"] == "suspensa" and "historico_estados" not in salvo


def test_servico_usa_repositorio_e_relogio_recebidos(app, database, obra):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from app.obras.repository import RepositorioObras
    from app.obras.service import ServicoObras

    instante = datetime(2031, 2, 3, 12, tzinfo=timezone.utc)
    colecao = database["tbl_obras_injetadas"]
    repositorio = RepositorioObras({"tbl_obras": colecao})
    servico = ServicoObras(repositorio, SimpleNamespace(agora=lambda: instante))
    criada = servico.criar_obra(obra, "conta")
    concluida = servico.alterar_estado(criada["id"], {"estado": "concluída", "motivo": "Entrega"}, "conta")
    assert concluida["data_conclusao"] == "2031-02-03"
    assert colecao.count_documents({}) == 1
    assert database.tbl_obras.count_documents({}) == 0
