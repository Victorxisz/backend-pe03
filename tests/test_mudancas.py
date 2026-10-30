"""CT-52 a CT-59: decisões aplicadas, versões e trilha indivisível do UC-12."""

from datetime import datetime
from unittest.mock import patch

from bson import ObjectId
from pymongo.errors import PyMongoError
import pytest

from support import snapshot
from support_obras import ID, seed

PATH = f"/obras/{ID}/mudancas"


def decisao(campo="entrega", novo_valor=None, **campos):
    return {
        "alvo": {"tipo": "obra", "id": ID}, "campo": campo,
        "novo_valor": novo_valor if novo_valor is not None else {
            "modalidade": "intervalo_estimado", "inicio": "2031-01-01", "fim": "2031-02-01"
        },
        "motivo": "Replanejamento aprovado", "versao": 0, **campos,
    }


def preparar_marco(database, obra):
    seed(database, obra)
    marco_id = database.tbl_marcos.insert_one({
        "obra_id": ObjectId(ID), "nome": "Estrutura", "descricao": "Estrutura da casa",
        "estado": "a iniciar", "inicio_previsto": "2030-10-01", "fim_previsto": "2030-11-01",
    }).inserted_id
    return marco_id, {"tipo": "marco", "id": str(marco_id)}


def test_ct52_ct53_troca_modalidade_e_preserva_valor_real(client, headers, database, obra, account):
    seed(database, obra)
    resposta = client.post(PATH, json=decisao(), headers=headers)
    assert resposta.status_code == 200
    atual = resposta.get_json()
    assert atual["entrega"] == decisao()["novo_valor"]
    assert "data" not in atual["entrega"]
    evento = atual["historico_mudancas"][0]
    assert evento["valor_anterior"] == obra["entrega"]
    assert evento["valor_novo"] == atual["entrega"]
    assert evento["autor"] == str(account["_id"])
    assert evento["instante"] == "2030-10-20T12:00:00+00:00"
    assert evento["motivo"] == decisao()["motivo"]
    volta = client.post(PATH, json=decisao(novo_valor=obra["entrega"], versao=1), headers=headers)
    assert volta.status_code == 200
    assert volta.get_json()["entrega"] == obra["entrega"]
    assert len(volta.get_json()["historico_mudancas"]) == 2
    assert client.get(f"/obras/{ID}", headers=headers).get_json() == volta.get_json()


def test_ct55_concluir_reabrir_e_preservar_data_efetiva(client, headers, database, obra):
    seed(database, obra)
    concluida = client.post(PATH, json=decisao("estado", "concluída"), headers=headers)
    assert concluida.status_code == 200
    assert concluida.get_json()["data_conclusao"] == "2030-10-20"
    repetida = client.post(PATH, json=decisao("estado", "concluída", versao=1), headers=headers)
    assert repetida.get_json() == concluida.get_json()
    reaberta = client.post(PATH, json=decisao("estado", "em andamento", versao=1), headers=headers)
    assert reaberta.status_code == 200
    assert reaberta.get_json()["data_conclusao"] is None
    assert len(reaberta.get_json()["historico_estados"]) == 2
    assert reaberta.get_json()["historico_estados"][1]["valor_anterior"]["data_conclusao"] == "2030-10-20"


def test_ct59_alerta_segue_planejamento_vigente(client, headers, database, obra):
    seed(database, obra, entrega={"modalidade": "data_exata", "data": "2030-10-19"})
    assert client.get(f"/obras/{ID}", headers=headers).get_json()["alertas"] == ["atrasada"]
    resposta = client.post(PATH, json=decisao(), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json()["alertas"] == []


def test_prazo_da_concluida_reavalia_alerta_sem_mudar_conclusao(client, headers, database, obra):
    seed(database, obra, estado="concluída", data_conclusao="2030-10-18")
    resposta = client.post(PATH, json=decisao(novo_valor={
        "modalidade": "data_exata", "data": "2030-10-17"
    }), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json()["alertas"] == ["atrasada"]
    assert resposta.get_json()["data_conclusao"] == "2030-10-18"


@pytest.mark.parametrize("estado", ["planejada", "em andamento", "concluída", "suspensa"])
def test_estados_confirmados_da_obra(client, headers, database, obra, estado):
    seed(database, obra, estado="planejada")
    resposta = client.post(PATH, json=decisao("estado", estado), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json()["estado"] == estado


@pytest.mark.parametrize("prazo,atrasada", [("2030-10-19", True), ("2030-10-20", False), ("2030-10-21", False)])
def test_ct14_concluida_usa_data_efetiva(client, headers, emitir_headers, database, obra, prazo, atrasada):
    seed(database, obra, entrega={"modalidade": "data_exata", "data": prazo},
         estado="concluída", data_conclusao="2030-10-20")
    from freezegun import freeze_time
    with freeze_time("2030-10-25 12:00:00"):
        resposta = client.get(f"/obras/{ID}", headers=emitir_headers())
    assert resposta.status_code == 200
    assert resposta.get_json()["alertas"] == (["atrasada"] if atrasada else [])


@pytest.mark.parametrize("alteracoes", [
    {"motivo": " "}, {"motivo": None}, {"versao": True}, {"versao": -1}, {"versao": "0"},
    {"campo": "data_conclusao"}, {"campo": "estado", "novo_valor": "atrasada"},
    {"campo": "estado", "novo_valor": {}}, {"campo": "estado", "novo_valor": None},
    {"valor_anterior": "forjado"}, {"autor": "outro"}, {"instante": "2000-01-01"},
    {"novo_valor": {"modalidade": "data_exata", "data": "2030-02-30"}},
    {"novo_valor": {"modalidade": "data_exata", "data": "2030-12-01", "fim": "2030-12-02"}},
    {"novo_valor": {"modalidade": "intervalo_estimado", "inicio": "2030-12-02", "fim": "2030-12-01"}},
    {"confirmar_dependencias": True}, {"alvo": {"tipo": "outro", "id": ID}},
])
def test_ct56_ct57_rejeita_entrada_sem_gravar(client, headers, database, obra, alteracoes):
    seed(database, obra)
    antes = snapshot(database)
    dados = decisao()
    dados.update(alteracoes)
    resposta = client.post(PATH, json=dados, headers=headers)
    assert resposta.status_code == 422, resposta.get_json()
    assert snapshot(database) == antes


@pytest.mark.parametrize("dados", [None, [], {}, {"alvo": []}])
def test_corpo_incompleto(client, headers, dados):
    assert client.post(PATH, json=dados, headers=headers).status_code == 422


def test_versao_obsoleta_inclusive_entre_rotas(client, headers, database, obra):
    seed(database, obra)
    assert client.post(PATH, json=decisao(), headers=headers).status_code == 200
    antes = snapshot(database)
    assert client.post(PATH, json=decisao("estado", "concluída"), headers=headers).status_code == 409
    assert snapshot(database) == antes
    assert client.patch(f"/obras/{ID}/estado", json={"estado": "suspensa", "motivo": "Chuva"}, headers=headers).status_code == 200
    assert client.post(PATH, json=decisao("estado", "concluída", versao=1), headers=headers).status_code == 409


def test_corrida_entre_leitura_e_escrita(client, headers, database, obra, monkeypatch):
    from app.mudanças.routes import servico
    seed(database, obra)
    aplicar = servico.repositorio.aplicar

    def concorrente(tipo, documento, campos, evento):
        database.tbl_obras.update_one({"_id": ObjectId(ID)}, {"$inc": {"versao": 1}})
        return aplicar(tipo, documento, campos, evento)

    monkeypatch.setattr(servico.repositorio, "aplicar", concorrente)
    assert client.post(PATH, json=decisao(), headers=headers).status_code == 409
    salvo = database.tbl_obras.find_one()
    assert salvo["entrega"] == obra["entrega"]
    assert "historico_mudancas" not in salvo


def test_ct58_falha_atomica_da_obra(client, headers, database, obra):
    seed(database, obra)
    antes = snapshot(database)
    with patch.object(database.tbl_obras, "find_one_and_update", side_effect=PyMongoError("falha")):
        resposta = client.post(PATH, json=decisao(), headers=headers)
    assert resposta.status_code == 500
    assert snapshot(database) == antes


def test_ct63_sem_exclusao_isolada_e_exige_sessao(client, headers, database, obra):
    seed(database, obra)
    antes = snapshot(database)
    assert client.post(PATH, json=decisao()).status_code == 401
    assert client.delete(PATH, headers=headers).status_code == 405
    assert snapshot(database) == antes


def test_alvo_de_outra_obra_e_id_invalido(client, headers, database, obra):
    marco_id, alvo = preparar_marco(database, obra)
    database.tbl_marcos.update_one({"_id": marco_id}, {"$set": {"obra_id": ObjectId()}})
    antes = snapshot(database)
    assert client.post(PATH, json=decisao("estado", "concluído", alvo=alvo), headers=headers).status_code == 404
    assert client.post(PATH, json=decisao(alvo={"tipo": "obra", "id": "inválido"}), headers=headers).status_code == 400
    assert client.post(PATH, json=decisao(alvo={"tipo": "obra", "id": str(ObjectId())}), headers=headers).status_code == 404
    assert snapshot(database) == antes


def test_ct27_dependencias_tambem_impedem_atalho(client, headers, database, obra):
    marco_id, alvo = preparar_marco(database, obra)
    dependencia = database.tbl_marcos.insert_one({"obra_id": ObjectId(ID), "estado": "a iniciar", "nome": "Fundação"}).inserted_id
    database.tbl_marcos.update_one({"_id": marco_id}, {"$set": {"dependencias": [dependencia]}})
    antes = snapshot(database)
    resposta = client.post(PATH, json=decisao("estado", "concluído", alvo=alvo), headers=headers)
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "DEPENDENCIAS_PENDENTES"
    assert snapshot(database) == antes


@pytest.mark.parametrize("periodo", [None, {}, {"inicio_previsto": "2030-12-01"},
    {"inicio_previsto": "2030-12-02", "fim_previsto": "2030-12-01"},
    {"inicio_previsto": "2030-02-30", "fim_previsto": "2030-12-01"}])
def test_ct54_periodo_invalido(client, headers, database, obra, periodo):
    _, alvo = preparar_marco(database, obra)
    dados = decisao("periodo_previsto", alvo=alvo)
    dados["novo_valor"] = periodo
    antes = snapshot(database)
    assert client.post(PATH, json=dados, headers=headers).status_code == 422
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_ct54_persiste_periodo_e_trilha(client, headers, database, obra, account):
    marco_id, alvo = preparar_marco(database, obra)
    periodo = {"inicio_previsto": "2030-11-01", "fim_previsto": "2030-12-01"}
    resposta = client.post(PATH, json=decisao("periodo_previsto", periodo, alvo=alvo), headers=headers)
    assert resposta.status_code == 200
    salvo = database.tbl_marcos.find_one({"_id": marco_id})
    assert {campo: salvo[campo] for campo in periodo} == periodo
    evento = database.tbl_historico.find_one({"alvo.id": marco_id})
    assert evento["valor_anterior"] == {"inicio_previsto": "2030-10-01", "fim_previsto": "2030-11-01"}
    assert evento["valor_novo"] == periodo
    assert evento["autor"] == str(account["_id"])
    assert evento["instante"] == datetime(2030, 10, 20, 12)


@pytest.mark.atlas
@pytest.mark.parametrize("apos_inserir", [False, True])
def test_ct58_rollback_marco_e_evento(client, headers, database, obra, monkeypatch, apos_inserir):
    from app.historico import repository
    marco_id, alvo = preparar_marco(database, obra)
    antes = snapshot(database)
    inserir = repository.inserir_evento
    chamadas = []

    def falhar(evento, *, session=None):
        assert session is not None
        assert database.tbl_marcos.find_one({"_id": marco_id}, session=session)["fim_previsto"] == "2030-12-01"
        if apos_inserir:
            inserir(evento, session=session)
        chamadas.append(True)
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(repository, "inserir_evento", falhar)
    periodo = {"inicio_previsto": "2030-11-01", "fim_previsto": "2030-12-01"}
    resposta = client.post(PATH, json=decisao("periodo_previsto", periodo, alvo=alvo), headers=headers)
    assert resposta.status_code == 500
    assert chamadas == [True]
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_ct28_ct29_confirmar_e_reabrir_marco(client, headers, database, obra):
    marco_id, alvo = preparar_marco(database, obra)
    dependencia = database.tbl_marcos.insert_one({"obra_id": ObjectId(ID), "estado": "a iniciar", "nome": "Fundação"}).inserted_id
    database.tbl_marcos.update_one({"_id": marco_id}, {"$set": {"dependencias": [dependencia]}})
    concluida = client.post(PATH, json=decisao("estado", "concluído", alvo=alvo, confirmar_dependencias=True), headers=headers)
    assert concluida.status_code == 200
    assert concluida.get_json()["estado"] == "concluído"
    assert database.tbl_historico.find_one({"alvo.id": marco_id})["confirmou_dependencias_pendentes"] is True
    reaberta = client.post(PATH, json=decisao("estado", "em andamento", alvo=alvo, versao=1), headers=headers)
    assert reaberta.status_code == 200
    assert database.tbl_historico.count_documents({"alvo.id": marco_id}) == 2


@pytest.mark.atlas
def test_estado_e_periodo_compartilham_versao(client, headers, database, obra):
    _, alvo = preparar_marco(database, obra)
    periodo = {"inicio_previsto": "2030-11-01", "fim_previsto": "2030-12-01"}
    assert client.post(PATH, json=decisao("periodo_previsto", periodo, alvo=alvo), headers=headers).status_code == 200
    antes = snapshot(database)
    resposta = client.post(PATH, json=decisao("estado", "concluído", alvo=alvo), headers=headers)
    assert resposta.status_code == 409
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_valor_e_trilha_persistem_em_outro_processo(client, headers, database, obra):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    marco_id, alvo = preparar_marco(database, obra)
    assert client.post(PATH, json=decisao(), headers=headers).status_code == 200
    assert client.post(PATH, json=decisao("estado", "concluída", versao=1), headers=headers).status_code == 200
    periodo = {"inicio_previsto": "2030-11-01", "fim_previsto": "2030-12-01"}
    assert client.post(PATH, json=decisao("periodo_previsto", periodo, alvo=alvo), headers=headers).status_code == 200
    consulta = '''
import json, os
from bson import ObjectId
from mongo_support import conectar_mongo, recuperar_banco_da_execucao
from support import isolated_app
with conectar_mongo() as cliente:
    banco = recuperar_banco_da_execucao(cliente)
    with isolated_app(banco):
        from app.serializacao import serializar
        obra = banco.tbl_obras.find_one({"_id": ObjectId(os.environ["TEST_OBRA_ID"])})
        marco = banco.tbl_marcos.find_one({"_id": ObjectId(os.environ["TEST_MARCO_ID"])})
        eventos = list(banco.tbl_historico.find({"alvo.id": marco["_id"]}))
        print(json.dumps(serializar({"obra": obra, "marco": marco, "eventos": eventos})))
'''
    ambiente = dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo,
                    TEST_OBRA_ID=ID, TEST_MARCO_ID=str(marco_id),
                    PYTHONPATH=str(Path(__file__).parent))
    processo = subprocess.run([sys.executable, "-B", "-c", consulta], env=ambiente,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert processo.returncode == 0, "Falha na releitura em processo novo; credenciais omitidas"
    persistido = json.loads(processo.stdout)
    assert persistido["obra"]["entrega"] == decisao()["novo_valor"]
    assert persistido["obra"]["historico_mudancas"][0]["valor_anterior"] == obra["entrega"]
    assert persistido["obra"]["data_conclusao"] == "2030-10-20"
    assert persistido["obra"]["historico_estados"][0]["valor_novo"]["estado"] == "concluída"
    assert persistido["marco"]["fim_previsto"] == periodo["fim_previsto"]
    assert persistido["eventos"][0]["valor_novo"] == periodo
