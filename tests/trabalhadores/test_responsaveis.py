"""UC-20/RN-08: manutenção de equipe não deixa responsáveis órfãos."""

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_avancos import transacao_local


@pytest.fixture
def cenario(client, headers, database, pessoa, obra_existente):
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


@pytest.mark.parametrize("acao", ["excluir", "desvincular", "dados"])
def test_manutencao_preserva_ocorrencias_e_historico(
    client, headers, database, pessoa, cenario, transacao_local, acao,
):
    outra, ocorrencias = cenario
    caminho = f"/trabalhadores/{pessoa['_id']}/"
    if acao == "excluir":
        resposta = client.delete(caminho, headers=headers)
    else:
        dados = {"obras": [str(outra["_id"])]} if acao == "desvincular" else {"nome": "Nome corrigido"}
        resposta = client.patch(caminho, headers=headers, json=dados)
    assert resposta.status_code == 200
    for indice, anterior in enumerate(ocorrencias):
        remove = acao == "excluir" or acao == "desvincular" and indice == 0
        esperado = {**anterior, "responsavel_id": None, "versao": anterior.get("versao", 0) + 1} if remove else anterior
        assert database.tbl_ocorrencias.find_one({"_id": anterior["_id"]}) == esperado
        consulta = client.get(f"/ocorrencias/{anterior['_id']}", headers=headers)
        assert consulta.status_code == 200
        assert consulta.json["aceitacoes"]
        if remove:
            # Um formulário aberto antes da retirada precisa recarregar a versão.
            conflito = client.patch(f"/ocorrencias/{anterior['_id']}", headers=headers, json={
                "versao": anterior.get("versao", 0), "alteracoes": {"titulo": "Formulário antigo"}})
            assert conflito.status_code == 409


@pytest.mark.parametrize("acao", ["excluir", "desvincular"])
def test_falha_de_limpeza_reverte_toda_manutencao(
    client, headers, database, pessoa, cenario, transacao_local, monkeypatch, acao,
):
    antes = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("falha de limpeza simulada")

    with monkeypatch.context() as contexto:
        import trabalhadores
        contexto.setattr(trabalhadores.servico.repositorio.ocorrencias, "update_many", falhar)
        caminho = f"/trabalhadores/{pessoa['_id']}/"
        resposta = (client.delete(caminho, headers=headers) if acao == "excluir"
                    else client.patch(caminho, headers=headers, json={"obras": []}))
    assert resposta.status_code == 503
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_consistencia_em_transacao_real(client, headers, database, pessoa, cenario):
    outra, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers,
                           json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 200
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencias[0]["_id"]})["responsavel_id"] is None
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencias[1]["_id"]})["responsavel_id"] == pessoa["_id"]
    assert client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers).status_code == 200
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencias[1]["_id"]})["responsavel_id"] is None
