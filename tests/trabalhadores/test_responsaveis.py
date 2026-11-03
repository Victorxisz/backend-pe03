"""UC-20: vínculos e atribuições são atualizados atomicamente."""

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_avancos import transacao_local


@pytest.fixture
def cenario(client, headers, database, pessoa, obra_existente, transacao_local):
    """Duas obras com uma ocorrência cada, ambas sob a mesma responsável."""
    outra = {**obra_existente, "_id": ObjectId()}
    database.tbl_obras.insert_one(outra)
    database.tbl_trabalhadores.update_one(
        {"_id": pessoa["_id"]}, {"$set": {"obras": [str(obra_existente["_id"]), str(outra["_id"])]}})
    ocorrencias = []
    for obra in (obra_existente, outra):
        resposta = client.post(f"/obras/{obra['_id']}/ocorrencias", headers=headers, json={
            "titulo": "Infiltração", "descricao": "Inspecionar fachada", "estado": "sem solução",
            "responsavel_id": str(pessoa["_id"]),
        })
        assert resposta.status_code == 201
        identificador = ObjectId(resposta.json["id"])
        assert client.post(f"/ocorrencias/{identificador}/aceitacoes", headers=headers,
                           json={"justificativa": "Decisão anterior"}).status_code == 201
        ocorrencias.append(database.tbl_ocorrencias.find_one({"_id": identificador}))
    return outra, ocorrencias


def test_exclusao_desatribui_as_duas_obras_e_preserva_as_decisoes(
    client, headers, database, pessoa, cenario, transacao_local,
):
    """Remover o cadastro alcança toda ocorrência da pessoa, em qualquer obra."""
    _, ocorrencias = cenario
    resposta = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json["ocorrencias_sem_responsavel"] == len(ocorrencias)
    for anterior in ocorrencias:
        salva = database.tbl_ocorrencias.find_one({"_id": anterior["_id"]})
        assert salva["responsavel_id"] is None
        assert salva["responsavel_anterior"]["id"] == str(pessoa["_id"])
        # Só a atribuição viva muda: autoria, aceitações e histórico ficam.
        assert {campo: valor for campo, valor in salva.items()
                if campo not in ("responsavel_id", "responsavel_anterior", "versao")} == {
            campo: valor for campo, valor in anterior.items() if campo not in ("responsavel_id", "versao")}
        assert salva["versao"] == anterior.get("versao", 0) + 1
        consulta = client.get(f"/ocorrencias/{anterior['_id']}", headers=headers)
        assert consulta.status_code == 200
        assert consulta.json["aceitacoes"]
        atrasada = client.patch(f"/ocorrencias/{anterior['_id']}", headers=headers,
                                json={"versao": anterior.get("versao", 0), "alteracoes": {"descricao": "antiga"}})
        assert atrasada.status_code == 409


def test_edicao_descritiva_nao_muda_atribuicoes(client, headers, database, pessoa, cenario):
    _, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"nome": "Nome corrigido"})
    assert resposta.status_code == 200
    for anterior in ocorrencias:
        assert database.tbl_ocorrencias.find_one({"_id": anterior["_id"]}) == anterior


def test_retirar_uma_obra_limpa_somente_as_atribuicoes_daquela_obra(client, headers, database, pessoa, cenario):
    outra, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 200
    removida = database.tbl_ocorrencias.find_one({"_id": ocorrencias[0]["_id"]})
    mantida = database.tbl_ocorrencias.find_one({"_id": ocorrencias[1]["_id"]})
    assert removida["responsavel_id"] is None
    assert removida["responsavel_anterior"]["id"] == str(pessoa["_id"])
    assert removida["versao"] == ocorrencias[0].get("versao", 0) + 1
    assert removida["aceitacoes"] == ocorrencias[0]["aceitacoes"]
    assert mantida == ocorrencias[1]
    antiga = client.patch(f"/ocorrencias/{removida['_id']}", headers=headers,
                          json={"versao": 0, "alteracoes": {"descricao": "desatualizada"}})
    assert antiga.status_code == 409


def test_lista_vazia_limpa_as_duas_obras_sem_excluir_pessoa(client, headers, database, pessoa, cenario):
    _, ocorrencias = cenario
    assert client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": []}).status_code == 200
    assert database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]})["obras"] == []
    for anterior in ocorrencias:
        salva = database.tbl_ocorrencias.find_one({"_id": anterior["_id"]})
        assert salva["responsavel_id"] is None and salva["responsavel_anterior"]["id"] == str(pessoa["_id"])
        assert salva["versao"] == anterior.get("versao", 0) + 1
        assert salva["aceitacoes"] == anterior["aceitacoes"]


def test_falha_no_desvinculo_reverte_cadastro_e_ocorrencias(client, headers, database, pessoa, cenario, monkeypatch):
    outra, _ = cenario
    antes = snapshot(database)
    import trabalhadores
    def falhar(*args, **kwargs):
        raise PyMongoError("falha de limpeza simulada")
    monkeypatch.setattr(trabalhadores.servico.repositorio.ocorrencias, "update_many", falhar)
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 503
    assert snapshot(database) == antes


def test_falha_de_limpeza_reverte_toda_a_exclusao(
    client, headers, database, pessoa, cenario, transacao_local, monkeypatch,
):
    """Sem conseguir desatribuir, o cadastro também não sai."""
    antes = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("falha de limpeza simulada")

    with monkeypatch.context() as contexto:
        import trabalhadores
        contexto.setattr(trabalhadores.servico.repositorio.ocorrencias, "update_many", falhar)
        resposta = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)
    assert resposta.status_code == 503
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_consistencia_em_transacao_real(client, headers, database, pessoa, cenario):
    outra, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers,
                            json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 200
    primeira = database.tbl_ocorrencias.find_one({"_id": ocorrencias[0]["_id"]})
    segunda = database.tbl_ocorrencias.find_one({"_id": ocorrencias[1]["_id"]})
    assert primeira["responsavel_id"] is None and primeira["versao"] == 1
    assert segunda["responsavel_id"] == pessoa["_id"]
    assert client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers).status_code == 200
    for anterior in ocorrencias:
        salva = database.tbl_ocorrencias.find_one({"_id": anterior["_id"]})
        assert salva["responsavel_id"] is None
        assert salva["responsavel_anterior"]["id"] == str(pessoa["_id"])

@pytest.mark.atlas
@pytest.mark.parametrize("operacao", ["desvincular", "excluir"])
def test_atribuicao_concorrente_nao_sobrevive_a_remocao(app, headers, database, pessoa, cenario, operacao):
    """Replica set real: atribuição e remoção disputam a mesma escrita do trabalhador."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    outra, ocorrencias = cenario
    obra_id = ocorrencias[0]["obra_id"]
    barreira = Barrier(2)
    def atribuir():
        with app.test_client() as client:
            barreira.wait(timeout=10)
            return client.post(f"/obras/{obra_id}/ocorrencias", headers=headers, json={
                "titulo": "Concorrente", "descricao": "Teste", "estado": "aberta",
                "responsavel_id": str(pessoa["_id"])}).status_code
    def remover():
        with app.test_client() as client:
            barreira.wait(timeout=10)
            if operacao == "excluir":
                return client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers).status_code
            return client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers,
                                json={"obras": [str(outra["_id"])]}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        atrib, rem = executor.submit(atribuir), executor.submit(remover)
        status_atrib, status_rem = atrib.result(timeout=30), rem.result(timeout=30)
    assert status_atrib in (201, 404)
    assert status_rem in (200, 409)
    if status_rem == 409:
        with app.test_client() as client:
            if operacao == "excluir":
                resposta = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)
            else:
                resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers,
                                        json={"obras": [str(outra["_id"])]})
            assert resposta.status_code == 200
    filtro = {"responsavel_id": {"$in": [pessoa["_id"], str(pessoa["_id"])]}}
    if operacao == "desvincular":
        filtro["obra_id"] = obra_id
    assert database.tbl_ocorrencias.count_documents(filtro) == 0

def test_revalida_vinculo_na_transacao_antes_de_criar(client, headers, database, pessoa, cenario, monkeypatch):
    """Se o vínculo mudou entre a validação inicial e a reserva, não grava ocorrência."""
    from app.ocorrencias.repository import RepositorioOcorrencias
    original = RepositorioOcorrencias._reservar_responsavel
    obra_id = cenario[1][0]["obra_id"]
    antes = database.tbl_ocorrencias.count_documents({})
    def intercalar(repo, trabalhador_id, obra, autor, sessao):
        database.tbl_trabalhadores.update_one({"_id": trabalhador_id}, {"$set": {"obras": []}}, session=sessao)
        return original(repo, trabalhador_id, obra, autor, sessao)
    monkeypatch.setattr(RepositorioOcorrencias, "_reservar_responsavel", intercalar)
    resposta = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers, json={
        "titulo": "Teste", "descricao": "Teste de concorrência", "estado": "aberta", "responsavel_id": str(pessoa["_id"])})
    assert resposta.status_code == 404
    assert database.tbl_ocorrencias.count_documents({}) == antes

def test_revalida_vinculo_na_transacao_antes_de_reatribuir(client, headers, database, pessoa, cenario, monkeypatch):
    from app.ocorrencias.repository import RepositorioOcorrencias
    original = RepositorioOcorrencias._reservar_responsavel
    obra_id = cenario[1][0]["obra_id"]
    criada = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers, json={
        "titulo": "Sem responsável", "descricao": "Teste", "estado": "aberta"})
    assert criada.status_code == 201
    antes = snapshot(database)
    def intercalar(repo, trabalhador_id, obra, autor, sessao):
        database.tbl_trabalhadores.update_one({"_id": trabalhador_id}, {"$set": {"obras": []}}, session=sessao)
        return original(repo, trabalhador_id, obra, autor, sessao)
    monkeypatch.setattr(RepositorioOcorrencias, "_reservar_responsavel", intercalar)
    resposta = client.patch(criada.headers["Location"], headers=headers, json={
        "versao": 0, "alteracoes": {"responsavel_id": str(pessoa["_id"])}})
    assert resposta.status_code == 404
    assert snapshot(database) == antes


def test_retirada_reconhece_vinculos_legados_bson_e_texto(client, headers, database, pessoa, cenario):
    outra, ocorrencias = cenario
    primeiro = ocorrencias[0]["obra_id"]
    database.tbl_trabalhadores.update_one({"_id": pessoa["_id"]}, {"$set": {"obras": [primeiro, outra["_id"]]}})
    database.tbl_ocorrencias.update_one({"_id": ocorrencias[0]["_id"]}, {"$set": {"obra_id": str(primeiro)}})
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 200
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencias[0]["_id"]})["responsavel_id"] is None
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencias[1]["_id"]})["responsavel_id"] == pessoa["_id"]
