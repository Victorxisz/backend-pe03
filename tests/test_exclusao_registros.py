"""UC-18 / CT-86–89. CT-39 continua compartilhado em avancos/."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from bson import ObjectId
from pymongo.errors import AutoReconnect

from support import isolated_app, snapshot
from support_exclusoes import cenario, provedor, chave  # noqa: F401
from support_avancos import transacao_local  # noqa: F401
from support_midias import config  # noqa: F401


def caminho(cenario, tipo):
    return (f"/avancos/{cenario.publicado}" if tipo == "avanco"
            else f"/ocorrencias/{cenario.ocorrencia}")


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_ct86_previa_e_cancelamento_sem_mutacao(client, headers, database, cenario, tipo):
    antes = snapshot(database)
    path = caminho(cenario, tipo)
    previa = client.get(path + "/exclusao", headers=headers)
    assert previa.status_code == 200
    assert previa.json["alvo"]["tipo"] == tipo
    assert previa.json["perda"]["midias"] > 0
    for corpo in (None, {}, {"confirmar": False}, {"confirmar": "true"},
                  {"confirmar": True, "forcar": True}):
        resposta = client.delete(path, headers=headers, **({"json": corpo} if corpo is not None else {}))
        assert resposta.status_code == 422
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_ct87_88_remove_so_registro_e_dependentes(client, headers, database, cenario, tipo, transacao_local):
    path = caminho(cenario, tipo)
    # Vizinho da mesma obra e todos os registros da outra obra permanecem.
    outra = deepcopy(database.tbl_ocorrencias.find_one({"_id": cenario.ocorrencia}))
    outra.update(_id=ObjectId(), midias=[], aceitacoes=[])
    database.tbl_ocorrencias.insert_one(outra)
    database.tbl_ocorrencias.update_one({"_id": cenario.ocorrencia},
                                      {"$set": {"historico_estados": [{"motivo": "Transição"}]}})
    antes = snapshot(database)
    assert client.delete(path, json={"confirmar": True}, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.delete(path, json={"confirmar": True}, headers=headers).status_code == 404
    depois = snapshot(database)
    for nome in ("tbl_obras", "tbl_marcos", "tbl_trabalhadores"):
        assert depois[nome] == antes[nome]
    assert database.tbl_ocorrencias.find_one({"_id": outra["_id"]}) == outra
    assert database.tbl_avancos.find_one({"_id": cenario.avanco_b})
    assert database.tbl_avancos.find_one({"_id": cenario.rascunho})
    if tipo == "avanco":
        for sufixo in ("/versoes", "/publicacoes", "/midias"):
            assert client.get(path + sufixo, headers=headers).status_code == 404
        previa = client.get(f"/obras/{cenario.obra}/previa", headers=headers)
        assert str(cenario.publicado) not in previa.get_data(as_text=True)
        assert database.tbl_limpezas_midias.count_documents({"avanco_id": cenario.publicado}) == 0
        assert chave(cenario.midia_publicada["referencia_externa"]) not in cenario.objetos
        assert chave(cenario.midia_retirada["referencia_externa"]) not in cenario.objetos
        assert database.tbl_ocorrencias.find_one({"_id": cenario.ocorrencia})
    else:
        assert client.get(path + "/aceitacoes", headers=headers).status_code == 404
        assert chave(cenario.evidencia["referencia_externa"]) not in cenario.objetos
        assert database.tbl_avancos.find_one({"_id": cenario.publicado})
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 0
    # Recria a aplicação: nenhuma exclusão depende da memória do serviço.
    with isolated_app(database) as reiniciada:
        with reiniciada.test_client() as novo:
            assert novo.get(path, headers=headers).status_code == 404


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
@pytest.mark.parametrize("campo", ["obra_id", "marco_id"])
@pytest.mark.parametrize("origem", ["json", "query"])
def test_ct89_contexto_manipulado(client, headers, database, cenario, tipo, campo, origem):
    antes = snapshot(database)
    valor = str(cenario.obra_b if campo == "obra_id" else cenario.marco_b)
    path = caminho(cenario, tipo)
    corpo = {"confirmar": True}
    if origem == "json":
        corpo[campo] = valor
    else:
        path += f"?{campo}={valor}"
    assert client.delete(path, json=corpo, headers=headers).status_code == 409
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_ct89_cadeia_real_e_autoria(client, headers, database, cenario, tipo):
    path = caminho(cenario, tipo)
    database.tbl_marcos.update_one({"_id": cenario.marco}, {"$set": {"obra_id": ObjectId()}})
    antes = snapshot(database)
    assert client.delete(path, json={"confirmar": True}, headers=headers).status_code == 404
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_ct84_falha_duravel_retomada_validada(client, headers, emitir_headers, database, cenario, tipo, transacao_local):
    path = caminho(cenario, tipo)
    midia = cenario.midia_publicada if tipo == "avanco" else cenario.evidencia
    cenario.falhas.add(chave(midia["referencia_externa"]))
    resposta = client.delete(path, json={"confirmar": True}, headers=headers)
    assert resposta.status_code == 503 and resposta.json["codigo"] == "LIMPEZA_PENDENTE"
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 1
    assert client.get(path, headers=headers).status_code == 404
    antes = snapshot(database)
    assert client.delete(path, headers=headers).status_code == 422
    assert client.delete(path, json={"confirmar": True},
                         headers=emitir_headers(identidade=str(ObjectId()))).status_code in (401, 404)
    assert client.delete(path, json={"confirmar": True, "obra_id": str(cenario.obra_b)},
                         headers=headers).status_code == 409
    assert snapshot(database) == antes
    cenario.falhas.clear()
    with isolated_app(database) as reiniciada:
        with reiniciada.test_client() as novo:
            assert novo.delete(path, json={"confirmar": True}, headers=headers).status_code == 204
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 0
    assert chave(midia["referencia_externa"]) not in cenario.objetos


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_preserva_arquivo_compartilhado(client, headers, database, cenario, tipo, transacao_local):
    midia = cenario.midia_publicada if tipo == "avanco" else cenario.evidencia
    compartilhada = cenario.midia(cenario.avanco_b, referencia=midia["referencia_externa"])
    database.tbl_midias.insert_one(compartilhada)
    antes = database.tbl_midias.find_one({"_id": compartilhada["_id"]})
    assert client.delete(caminho(cenario, tipo), json={"confirmar": True}, headers=headers).status_code == 204
    assert chave(midia["referencia_externa"]) in cenario.objetos
    assert database.tbl_midias.find_one({"_id": compartilhada["_id"]}) == antes


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_referencia_externa_por_id_impede_orfao(client, headers, database, cenario, tipo, transacao_local):
    midia = cenario.midia_publicada if tipo == "avanco" else cenario.evidencia
    database.tbl_historico.insert_one({"midia": str(midia["_id"])})
    antes = snapshot(database)
    assert client.delete(caminho(cenario, tipo), json={"confirmar": True}, headers=headers).status_code == 409
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_falha_banco_sem_sucesso_falso(client, headers, database, cenario, tipo, monkeypatch, transacao_local):
    colecao = database.tbl_avancos if tipo == "avanco" else database.tbl_ocorrencias
    antes = snapshot(database)
    monkeypatch.setattr(colecao, "delete_many", lambda *a, **k: (_ for _ in ()).throw(AutoReconnect()))
    assert client.delete(caminho(cenario, tipo), json={"confirmar": True}, headers=headers).status_code == 503
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("prefixo", ["/avancos/", "/ocorrencias/"])
def test_ids_e_sessao(client, headers, prefixo):
    assert client.delete(prefixo + "invalido", json={"confirmar": True}, headers=headers).status_code == 400
    assert client.delete(prefixo + str(ObjectId()), json={"confirmar": True}, headers=headers).status_code == 404
    assert client.delete(prefixo + str(ObjectId()), json={"confirmar": True}).status_code == 401


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_upload_pendente_preserva_diario(client, headers, database, cenario, tipo, transacao_local):
    campo, valor = (("avanco_id", cenario.publicado) if tipo == "avanco"
                    else ("ocorrencia_id", cenario.ocorrencia))
    database.tbl_uploads_pendentes.insert_one({campo: valor, "estado": "pendente", "referencias": []})
    antes = snapshot(database)
    assert client.delete(caminho(cenario, tipo), json={"confirmar": True}, headers=headers).status_code == 409
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_alteracao_concorrente_nao_e_apagada(client, headers, database, cenario, tipo, monkeypatch, transacao_local):
    from app import exclusoes
    aplicar = exclusoes.aplicar
    colecao = database.tbl_avancos if tipo == "avanco" else database.tbl_ocorrencias
    identificador = cenario.publicado if tipo == "avanco" else cenario.ocorrencia

    def alterar_antes_da_transacao(conjunto):
        colecao.update_one({"_id": identificador}, {"$set": {"descricao": "Correção concorrente"}})
        return aplicar(conjunto)

    monkeypatch.setattr(exclusoes, "aplicar", alterar_antes_da_transacao)
    assert client.delete(caminho(cenario, tipo), json={"confirmar": True}, headers=headers).status_code == 409
    assert colecao.find_one({"_id": identificador})["descricao"] == "Correção concorrente"
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 0
    cenario.destroy.assert_not_called()


def test_rascunho_valida_contexto_sem_quebrar_uc09(client, headers, database, cenario):
    path = f"/avancos/{cenario.rascunho}"
    antes = snapshot(database)
    assert client.delete(path, json={"confirmar": True, "obra_id": str(cenario.obra_b)}, headers=headers).status_code == 409
    assert snapshot(database) == antes
    assert client.delete(path, headers=headers).status_code == 204


@pytest.mark.atlas
@pytest.mark.parametrize("tipo", ["avanco", "ocorrencia"])
def test_ct89_persistencia_em_processo_independente(client, headers, database, cenario, tipo):
    path = caminho(cenario, tipo)
    assert client.delete(path, json={"confirmar": True}, headers=headers).status_code == 204
    resultado = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("restart_probe.py"))],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo, TEST_RESOURCE_PATH=path),
        capture_output=True, text=True, timeout=60,
    )
    assert resultado.returncode == 0, "Falha no processo independente; credenciais omitidas"
    assert json.loads(resultado.stdout)["status"] == 404
    assert database.tbl_obras.find_one({"_id": cenario.obra})
    assert database.tbl_avancos.find_one({"_id": cenario.avanco_b})

