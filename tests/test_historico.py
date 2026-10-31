"""CT-60..63: leitura unificada, sequência, vazio e trilha imutável."""

from datetime import datetime, timezone

from bson import ObjectId
import pytest

from support import snapshot
from support_obras import ID, seed


def _evento(alvo_tipo, alvo_id, campo, antes, depois, instante, motivo):
    return {"tipo": f"{campo}_{alvo_tipo}", "alvo": {"tipo": alvo_tipo, "id": alvo_id},
            "campo": campo, "valor_anterior": antes, "valor_novo": depois,
            "motivo": motivo, "autor": "autor fictício", "instante": instante}


def test_ct60_unifica_prazo_marco_e_correcao_com_links(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    oid = ObjectId(ID)
    marco = database.tbl_marcos.insert_one({"obra_id": oid, "nome": "Estrutura"}).inserted_id
    primeiro = datetime(2030, 10, 18, tzinfo=timezone.utc)
    segundo = datetime(2030, 10, 19, tzinfo=timezone.utc)
    terceiro = datetime(2030, 10, 20, tzinfo=timezone.utc)
    evento_obra = _evento("obra", oid, "entrega", obra["entrega"],
                          {"modalidade": "data_exata", "data": "2031-01-01"}, primeiro, "Novo prazo")
    database.tbl_obras.update_one({"_id": oid}, {"$push": {"historico_mudancas": evento_obra}})
    evento_marco = _evento("marco", marco, "estado", "a iniciar", "em andamento", segundo, "Início")
    database.tbl_historico.insert_one(evento_marco)
    antes_pub = {"data": "2030-10-01", "descricao": "Texto antigo", "midias": []}
    depois_pub = {"data": "2030-10-01", "descricao": "Texto corrigido", "midias": []}
    avanco = database.tbl_avancos.insert_one({"marco_id": marco, "estado": "publicado",
        "data": depois_pub["data"], "descricao": depois_pub["descricao"], "midias": [],
        "publicacao": {**antes_pub, "autor": "original", "instante": primeiro},
        "correcoes": [{"antes": antes_pub, "depois": depois_pub, "motivo": "Ortografia",
                      "autor": "corretor", "instante": terceiro}]}).inserted_id
    banco_antes = snapshot(database)

    # Execução
    resposta = client.get(f"/obras/{ID}/mudancas", headers=headers)

    # Verificação
    assert resposta.status_code == 200
    eventos = resposta.json["mudancas"]
    assert [item["tipo"] for item in eventos] == ["entrega_obra", "estado_marco", "correcao_publicacao"]
    assert eventos[0]["antes"] == obra["entrega"]
    assert eventos[1]["depois"] == "em andamento"
    assert eventos[2]["comparacao"] == f"/avancos/{avanco}/versoes"
    for evento in eventos:
        assert client.get(evento["consulta"], headers=headers).json == evento
    assert client.get(eventos[2]["comparacao"], headers=headers).status_code == 200
    assert snapshot(database) == banco_antes


def test_ct61_duas_mudancas_no_mesmo_campo_permanecem(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    oid = ObjectId(ID)
    instante = datetime(2030, 10, 20, tzinfo=timezone.utc)
    for indice in range(2):
        evento = _evento("obra", oid, "entrega", str(indice), str(indice + 1), instante, f"Decisão {indice}")
        database.tbl_obras.update_one({"_id": oid}, {"$push": {"historico_mudancas": evento}})

    # Execução
    resposta = client.get(f"/obras/{ID}/mudancas", headers=headers)

    # Verificação
    eventos = resposta.json["mudancas"]
    assert len(eventos) == 2
    assert [item["motivo"] for item in eventos] == ["Decisão 0", "Decisão 1"]
    assert eventos[0]["id"] != eventos[1]["id"]


def test_ct62_obra_existente_sem_eventos_e_obra_inexistente(client, headers, database, obra):
    # Preparação
    seed(database, obra)

    # Execução
    vazio = client.get(f"/obras/{ID}/mudancas", headers=headers)
    ausente = client.get(f"/obras/{ObjectId()}/mudancas", headers=headers)

    # Verificação
    assert vazio.status_code == 200 and vazio.json == {"mudancas": []}
    assert ausente.status_code == 404


def test_ct63_nao_exclui_nem_edita_evento_isolado(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    oid = ObjectId(ID)
    evento = _evento("obra", oid, "entrega", "antes", "depois",
                     datetime(2030, 10, 20, tzinfo=timezone.utc), "Motivo")
    database.tbl_obras.update_one({"_id": oid}, {"$push": {"historico_mudancas": evento}})
    identificador = client.get(f"/obras/{ID}/mudancas", headers=headers).json["mudancas"][0]["id"]
    antes = snapshot(database)

    # Execução
    excluir = client.delete(f"/mudancas/{identificador}", headers=headers)
    editar = client.patch(f"/mudancas/{identificador}", json={"motivo": "Outro"}, headers=headers)

    # Verificação
    assert excluir.status_code == editar.status_code == 405
    assert snapshot(database) == antes


def test_historico_consulta_decisao_gerada_pelo_uc12(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    decisao = {"alvo": {"tipo": "obra", "id": ID}, "campo": "entrega",
               "novo_valor": {"modalidade": "data_exata", "data": "2031-01-01"},
               "motivo": "Replanejamento", "versao": 0}

    # Execução
    aplicada = client.post(f"/obras/{ID}/mudancas", json=decisao, headers=headers)
    lista = client.get(f"/obras/{ID}/mudancas", headers=headers)

    # Verificação
    assert aplicada.status_code == 200
    assert lista.status_code == 200
    evento = lista.json["mudancas"][0]
    assert evento["antes"] == obra["entrega"]
    assert evento["depois"] == decisao["novo_valor"]
    assert evento["motivo"] == "Replanejamento"
    assert client.get(evento["consulta"], headers=headers).json == evento


def test_evento_de_outra_obra_nao_aparece(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    alheia = ObjectId()
    evento = _evento("obra", alheia, "entrega", "antes", "depois",
                     datetime(2030, 10, 20, tzinfo=timezone.utc), "Alheio")
    database.tbl_obras.update_one({"_id": ObjectId(ID)}, {"$push": {"historico_mudancas": evento}})

    # Execução
    resposta = client.get(f"/obras/{ID}/mudancas", headers=headers)

    # Verificação
    assert resposta.status_code == 200 and resposta.json == {"mudancas": []}


def test_consultas_exigem_sessao_e_rejeitam_identificadores_invalidos(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    antes = snapshot(database)

    # Execução
    sem_sessao = client.get(f"/obras/{ID}/mudancas")
    detalhe_sem_sessao = client.get(f"/mudancas/{ObjectId()}")
    obra_invalida = client.get("/obras/invalido/mudancas", headers=headers)
    mudanca_invalida = client.get("/mudancas/invalido", headers=headers)

    # Verificação
    assert sem_sessao.status_code == detalhe_sem_sessao.status_code == 401
    assert obra_invalida.status_code == mudanca_invalida.status_code == 400
    assert snapshot(database) == antes


def test_evento_de_marco_alheio_nao_pertence_ao_historico(client, headers, database, obra):
    # Preparação
    seed(database, obra)
    alheia = database.tbl_obras.insert_one({"nome": "Outra obra"}).inserted_id
    marco = database.tbl_marcos.insert_one({"obra_id": alheia, "estado": "em andamento"}).inserted_id
    evento = _evento("marco", marco, "estado", "a iniciar", "em andamento",
                     datetime(2030, 10, 20, tzinfo=timezone.utc), "Decisão alheia")
    evento_id = database.tbl_historico.insert_one(evento).inserted_id

    # Execução
    nossa = client.get(f"/obras/{ID}/mudancas", headers=headers)
    outra = client.get(f"/obras/{alheia}/mudancas", headers=headers)
    detalhe = client.get(f"/mudancas/{evento_id}", headers=headers)

    # Verificação
    assert nossa.json == {"mudancas": []}
    assert len(outra.json["mudancas"]) == 1
    assert detalhe.json["obra_id"] == str(alheia)


def test_empate_preserva_ordem_numerica_de_doze_decisoes(client, headers, database, obra):
    seed(database, obra)
    oid = ObjectId(ID)
    eventos = [_evento("obra", oid, "entrega", str(i), str(i + 1),
                        datetime(2030, 10, 20), f"Decisão {i}") for i in range(12)]
    database.tbl_obras.update_one({"_id": oid}, {"$set": {"historico_mudancas": eventos}})
    antes = snapshot(database)

    lista = client.get(f"/obras/{ID}/mudancas", headers=headers)

    assert lista.status_code == 200
    assert [item["motivo"] for item in lista.json["mudancas"]] == [e["motivo"] for e in eventos]
    for evento in lista.json["mudancas"]:
        assert client.get(evento["consulta"], headers=headers).json == evento
    assert snapshot(database) == antes


def _publicacao_com_correcoes(database, obra, quantidade=11):
    seed(database, obra)
    marco = database.tbl_marcos.insert_one({"obra_id": ObjectId(ID)}).inserted_id
    original = {"data": "2030-10-01", "descricao": "Original", "midias": []}
    anterior = original
    correcoes = []
    for numero in range(2, quantidade + 2):
        depois = {**original, "descricao": f"Versão {numero}"}
        correcoes.append({"antes": anterior, "depois": depois, "motivo": f"Correção {numero}",
                          "autor": "corretor", "instante": datetime(2030, 10, 20)})
        anterior = depois
    return database.tbl_avancos.insert_one({
        "marco_id": marco, "estado": "publicado", **anterior,
        "publicacao": {**original, "autor": "original", "instante": datetime(2030, 10, 1)},
        "correcoes": correcoes,
    }).inserted_id


def test_empate_das_correcoes_segue_a_cadeia_das_versoes(client, headers, database, obra):
    avanco = _publicacao_com_correcoes(database, obra)
    antes = snapshot(database)

    lista = client.get(f"/obras/{ID}/mudancas", headers=headers)
    versoes = client.get(f"/avancos/{avanco}/versoes", headers=headers)

    assert lista.status_code == versoes.status_code == 200
    eventos = lista.json["mudancas"]
    assert len(eventos) == 11
    assert [e["motivo"] for e in eventos] == [f"Correção {n}" for n in range(2, 13)]
    for evento, versao in zip(eventos, versoes.json["versoes"][1:]):
        for campo in ("antes", "depois", "motivo", "autor", "instante", "campos"):
            assert evento[campo] == versao["correcao"][campo]
        assert client.get(evento["consulta"], headers=headers).json == evento
        assert evento["comparacao"] == f"/avancos/{avanco}/versoes"
    assert snapshot(database) == antes


@pytest.mark.parametrize("operacao,campo,valor", [
    ("$set", "correcoes.0.antes.descricao", "Cadeia divergente"),
    ("$set", "descricao", "Atual divergente"),
    ("$unset", "correcoes.0.motivo", ""),
    ("$set", "correcoes.0.autor", None),
    ("$set", "correcoes", [False]),
    ("$set", "publicacao", None),
    ("$set", "publicacao", {}),
])
def test_historia_inconsistente_retorna_conflito_na_lista_e_detalhe(
    client, headers, database, obra, operacao, campo, valor
):
    avanco = _publicacao_com_correcoes(database, obra, quantidade=1)
    consulta = f"/mudancas/publicacao:{avanco}:2"
    database.tbl_avancos.update_one({"_id": avanco}, {operacao: {campo: valor}})
    antes = snapshot(database)

    for caminho in (f"/obras/{ID}/mudancas", consulta, f"/avancos/{avanco}/versoes"):
        resposta = client.get(caminho, headers=headers)
        assert resposta.status_code == 409
        assert resposta.json["codigo"] == "HISTORICO_INDISPONIVEL"
    assert snapshot(database) == antes


def test_ordena_instantes_pelo_tempo_real_com_fusos_diferentes(client, headers, database, obra):
    seed(database, obra)
    oid = ObjectId(ID)
    eventos = [
        _evento("obra", oid, "entrega", "1", "2", "2030-10-20T10:00:00-03:00", "Segunda"),
        _evento("obra", oid, "entrega", "0", "1", "2030-10-20T12:00:00Z", "Primeira"),
    ]
    database.tbl_obras.update_one({"_id": oid}, {"$set": {"historico_mudancas": eventos}})
    antes = snapshot(database)

    lista = client.get(f"/obras/{ID}/mudancas", headers=headers)

    assert lista.status_code == 200
    assert [e["motivo"] for e in lista.json["mudancas"]] == ["Primeira", "Segunda"]
    assert snapshot(database) == antes


@pytest.mark.parametrize("campo,valor", [
    ("tipo", None), ("motivo", None), ("autor", None), ("instante", "data inválida"),
])
def test_decisao_incompleta_retorna_conflito_sem_alterar_a_trilha(
    client, headers, database, obra, campo, valor
):
    seed(database, obra)
    evento = _evento("obra", ObjectId(ID), "entrega", "antes", "depois",
                     datetime(2030, 10, 20), "Decisão")
    evento[campo] = valor
    database.tbl_obras.update_one({"_id": ObjectId(ID)}, {"$set": {"historico_mudancas": [evento]}})
    antes = snapshot(database)
    for caminho in (f"/obras/{ID}/mudancas", f"/mudancas/obra:{ID}:historico_mudancas:0"):
        resposta = client.get(caminho, headers=headers)
        assert resposta.status_code == 409
        assert resposta.json["codigo"] == "HISTORICO_INDISPONIVEL"
    assert snapshot(database) == antes
