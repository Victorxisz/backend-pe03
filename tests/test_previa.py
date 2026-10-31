"""Consulta da linha do tempo publicada por obra."""

from datetime import datetime, timezone

from bson import ObjectId


def _publicacao(avanco, instante, descricao, marker, autor="autor"):
    midia_id = str(ObjectId())
    return {
        "_id": avanco,
        "marco_id": marker,
        "data": "2030-10-19",
        "descricao": descricao,
        "estado": "publicado",
        "publicacao": {
            "autor": autor,
            "instante": instante,
            "data": "2030-10-19",
            "descricao": descricao,
            "marco": {"id": marker, "nome": "Fundação"},
            "midias": [{"id": midia_id, "tipo": "foto", "conteudo": f"/midias/{midia_id}/conteudo"}],
        },
    }


def test_previa_apenas_publicados_da_obra_com_mais_recente_primeiro(client, headers, database):
    obra, outra_obra = ObjectId(), ObjectId()
    marco, outro_marco = ObjectId(), ObjectId()
    database.tbl_obras.insert_many([{"_id": obra}, {"_id": outra_obra}])
    database.tbl_marcos.insert_many([
        {"_id": marco, "obra_id": obra}, {"_id": outro_marco, "obra_id": outra_obra},
    ])
    antigo, recente, rascunho = ObjectId(), ObjectId(), ObjectId()
    instante_antigo = datetime(2030, 10, 19, tzinfo=timezone.utc)
    instante_recente = datetime(2030, 10, 20, tzinfo=timezone.utc)
    database.tbl_avancos.insert_many([
        _publicacao(antigo, instante_antigo, "Antigo", marco),
        _publicacao(recente, instante_recente, "Atual", marco),
        {**_publicacao(rascunho, instante_recente, "Rascunho", marco), "estado": "rascunho"},
        _publicacao(ObjectId(), instante_recente, "Outra obra", outro_marco),
    ])

    resposta = client.get(f"/obras/{obra}/previa", headers=headers)

    assert resposta.status_code == 200
    assert [item["id"] for item in resposta.json["atualizacoes"]] == [str(recente), str(antigo)]
    assert resposta.json["atualizacoes"][0]["marco"]["nome"] == "Fundação"
    midia = resposta.json["atualizacoes"][0]["midias"][0]
    assert midia["conteudo"] == f"/midias/{midia['id']}/conteudo"


def test_previa_indica_descricao_corrigida_e_obra_sem_publicacoes(client, headers, database):
    obra, marco, avanco = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_one({"_id": obra})
    database.tbl_marcos.insert_one({"_id": marco, "obra_id": obra})
    registro = _publicacao(avanco, datetime(2030, 10, 20, tzinfo=timezone.utc), "Original", marco)
    registro["descricao"] = "Corrigida"
    database.tbl_avancos.insert_one(registro)

    resposta = client.get(f"/obras/{obra}/previa", headers=headers)
    assert resposta.json["atualizacoes"][0]["descricao"] == "Corrigida"
    assert resposta.json["atualizacoes"][0]["editado"] is True

    sem_publicacoes = ObjectId()
    database.tbl_obras.insert_one({"_id": sem_publicacoes})
    vazia = client.get(f"/obras/{sem_publicacoes}/previa", headers=headers)
    assert vazia.status_code == 200 and vazia.json == {"atualizacoes": []}

    ausente = client.get(f"/obras/{ObjectId()}/previa", headers=headers)
    assert ausente.status_code == 404


def test_previa_obra_existente_sem_publicacoes_retorna_lista_vazia(client, headers, database):
    obra = ObjectId()
    database.tbl_obras.insert_one({"_id": obra})
    resposta = client.get(f"/obras/{obra}/previa", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json == {"atualizacoes": []}
