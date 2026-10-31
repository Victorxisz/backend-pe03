"""Consulta de versões publicadas por HTTP; banco em memória."""
from datetime import datetime

from bson import ObjectId

from support import snapshot


def test_publicacao_sem_correcoes_retorna_snapshot_original(client, headers, database):
    # Preparação
    avanco = ObjectId()
    marco = ObjectId()
    documento = {"_id": avanco, "estado": "publicado", "autor": "autor-original",
                 "descricao": "Texto original", "data": "2030-01-01",
                 "publicacao": {"autor": "publicador", "instante": datetime(2030, 1, 2),
                                "descricao": "Texto original", "data": "2030-01-01",
                                "marco": {"id": marco, "nome": "Marco"}, "midias": []}}
    database.tbl_avancos.insert_one(documento)
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 200
    versao = resposta.json["versoes"][0]
    assert versao["numero"] == 1 and versao["atual"] is True
    assert versao["conteudo"]["descricao"] == "Texto original"
    assert versao["autor_original"] == "autor-original"
    assert versao["correcao"] is None
    assert snapshot(database) == antes


def test_avanco_inexistente_e_rascunho_sao_diferentes(client, headers, database):
    # Preparação
    avanco = database.tbl_avancos.insert_one({"estado": "rascunho"}).inserted_id

    # Execução
    inexistente = client.get(f"/avancos/{ObjectId()}/versoes", headers=headers)
    rascunho = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert inexistente.status_code == 404
    assert rascunho.status_code == 200 and rascunho.json["versoes"] == []


def test_publicacao_alterada_sem_historico_nao_inventa_versoes(client, headers, database):
    # Preparação
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "descricao": "alterado", "data": "2030-01-01",
        "publicacao": {"descricao": "original", "data": "2030-01-01", "midias": []},
    }).inserted_id
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 409
    assert resposta.json["codigo"] == "HISTORICO_INDISPONIVEL"
    assert snapshot(database) == antes


def test_consulta_exige_sessao(client):
    # Preparação e execução
    resposta = client.get(f"/avancos/{ObjectId()}/versoes")

    # Verificação
    assert resposta.status_code == 401


def test_ct46_ct47_ct50_ct51_cadeia_preexistente_continua_consultavel(client, headers, database):
    # Preparação: verifica a leitura de versões já persistidas.
    avanco = ObjectId()
    primeira = {"data": "2030-01-01", "descricao": "Parede branca", "midias": [{"id": "foto-1", "nome": "antes.png"}]}
    segunda = {"data": "2030-01-01", "descricao": "Parede azul", "midias": [{"id": "foto-1", "nome": "antes.png"}]}
    terceira = {"data": "2030-01-02", "descricao": "Parede azul", "midias": [{"id": "foto-2", "nome": "depois.png"}]}
    database.tbl_avancos.insert_one({"_id": avanco, "estado": "publicado", "autor": "autor inicial",
        "origem_simulada": True, **terceira,
        "publicacao": {**primeira, "autor": "publicador", "instante": datetime(2030, 1, 1)},
        "correcoes": [{"antes": primeira, "depois": segunda, "autor": "corretor 1", "motivo": "Cor", "instante": datetime(2030, 1, 2)},
                      {"antes": segunda, "depois": terceira, "autor": "corretor 2", "motivo": "Foto", "instante": datetime(2030, 1, 3)}]})
    antes = snapshot(database)

    # Execução
    resposta = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    # Verificação
    assert resposta.status_code == 200
    versoes = resposta.json["versoes"]
    assert [v["numero"] for v in versoes] == [1, 2, 3]
    assert [v["atual"] for v in versoes] == [False, False, True]
    assert [v["conteudo"] for v in versoes] == [primeira, segunda, terceira]
    assert versoes[1]["correcao"]["autor"] == "corretor 1"
    assert versoes[2]["correcao"]["campos"] == ["data", "midias"]
    assert versoes[0]["origem_simulada"] is True
    trechos = versoes[1]["correcao"]["diferencas_texto"]
    assert "".join(t["antes"] for t in trechos) == primeira["descricao"]
    assert "".join(t["depois"] for t in trechos) == segunda["descricao"]
    assert snapshot(database) == antes
