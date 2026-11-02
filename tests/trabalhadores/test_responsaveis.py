"""UC-20/RN-08: manutenção de equipe não deixa responsáveis órfãos.

A política é P-10 (`docs/07-plano-e-decisoes.md`): remover o cadastro zera
`responsavel_id` e guarda `responsavel_anterior` na mesma transação; retirar só
o vínculo de obra não mexe na atribuição, porque a ausência pode ser temporária.
Em nenhum dos dois casos a ocorrência, suas aceitações ou seu histórico saem.
"""

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_avancos import transacao_local


@pytest.fixture
def cenario(client, headers, database, pessoa, obra_existente):
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
                if campo not in ("responsavel_id", "responsavel_anterior")} == {
            campo: valor for campo, valor in anterior.items() if campo != "responsavel_id"}
        consulta = client.get(f"/ocorrencias/{anterior['_id']}", headers=headers)
        assert consulta.status_code == 200
        assert consulta.json["aceitacoes"]


@pytest.mark.parametrize("dados,caso", [
    ({"obras": []}, "sem nenhuma obra"),
    ({"nome": "Nome corrigido"}, "corrigindo só os dados"),
])
def test_edicao_nao_mexe_na_atribuicao(
    client, headers, database, pessoa, cenario, dados, caso,
):
    """P-10: ausência da obra é temporária; apagar quem responde seria perda."""
    _, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers, json=dados)
    assert resposta.status_code == 200, caso
    for anterior in ocorrencias:
        assert database.tbl_ocorrencias.find_one({"_id": anterior["_id"]}) == anterior, caso
        consulta = client.get(f"/ocorrencias/{anterior['_id']}", headers=headers)
        assert consulta.status_code == 200
        assert consulta.json["aceitacoes"]


def test_edicao_mantendo_uma_obra_preserva_as_duas_ocorrencias(
    client, headers, database, pessoa, cenario,
):
    """Trocar a lista de obras não é desatribuir: nenhuma ocorrência muda."""
    outra, ocorrencias = cenario
    resposta = client.patch(f"/trabalhadores/{pessoa['_id']}/", headers=headers,
                            json={"obras": [str(outra["_id"])]})
    assert resposta.status_code == 200
    for anterior in ocorrencias:
        assert database.tbl_ocorrencias.find_one({"_id": anterior["_id"]}) == anterior


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
    # Editar não desatribui, nem na obra que saiu da lista.
    for anterior in ocorrencias:
        assert database.tbl_ocorrencias.find_one(
            {"_id": anterior["_id"]})["responsavel_id"] == pessoa["_id"]
    assert client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers).status_code == 200
    for anterior in ocorrencias:
        salva = database.tbl_ocorrencias.find_one({"_id": anterior["_id"]})
        assert salva["responsavel_id"] is None
        assert salva["responsavel_anterior"]["id"] == str(pessoa["_id"])
