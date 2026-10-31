"""UC-13 ponta a ponta: eventos produzidos pelas rotas de origem."""


from support import isolated_app, snapshot
from support_publicacoes import cenario
from support_avancos import transacao_local


def test_uc13_reune_decisoes_e_correcoes_reais(client, headers, database, obra, cenario, account):
    # Preparação: cenario usa mídia fictícia e armazenamento simulado.
    database.tbl_obras.update_one({"_id": cenario["obra"]}, {"$set": {
        **obra, "estado": "em andamento", "versao": 0,
    }})
    database.tbl_marcos.update_one({"_id": cenario["marco"]}, {"$set": {"estado": "a iniciar"}})
    decisao = {"alvo": {"tipo": "obra", "id": str(cenario["obra"])},
               "campo": "entrega", "novo_valor": {
                   "modalidade": "data_exata", "data": "2031-01-01"},
               "motivo": "Prazo aprovado", "versao": 0}

    # Execução: UC-12, UC-07 e UC-11 usam suas rotas reais.
    prazo = client.post(f"/obras/{cenario['obra']}/mudancas", headers=headers, json=decisao)
    marco = client.patch(f"/marcos/{cenario['marco']}", headers=headers,
                         json={"estado": "em andamento", "motivo": "Etapa iniciada"})
    publicada = client.post(cenario["publicar"], headers=headers)
    primeira = client.patch(f"/avancos/{cenario['avanco']}", headers=headers,
                            json={"descricao": "Fundação concretada e revisada", "motivo": "Texto corrigido"})
    segunda = client.patch(f"/avancos/{cenario['avanco']}", headers=headers,
                           json={"descricao": "Fundação concluída", "motivo": "Nova vistoria"})
    antes = snapshot(database)
    lista = client.get(f"/obras/{cenario['obra']}/mudancas", headers=headers)

    # Verificação: duas correções persistem, cada consulta abre a mesma decisão.
    for resposta in (prazo, marco, publicada, primeira, segunda, lista):
        assert resposta.status_code in (200, 201), resposta.get_data(as_text=True)
    eventos = lista.json["mudancas"]
    assert len(eventos) == 4
    assert sorted(item["tipo"] for item in eventos) == sorted([
        "entrega_obra", "estado_marco", "correcao_publicacao", "correcao_publicacao"
    ])
    correcoes = [item for item in eventos if item["tipo"] == "correcao_publicacao"]
    assert {item["motivo"] for item in correcoes} == {"Texto corrigido", "Nova vistoria"}
    for evento in eventos:
        assert client.get(evento["consulta"], headers=headers).json == evento
    versoes = client.get(correcoes[0]["comparacao"], headers=headers).json["versoes"]
    assert len(versoes) == 3
    assert [item["conteudo"]["descricao"] for item in versoes] == [
        "Fundação concretada", "Fundação concretada e revisada", "Fundação concluída"
    ]
    assert snapshot(database) == antes
    with isolated_app(database) as nova_app:
        nova_app.config["CONSTRUTORA_ID"] = str(account["_id"])
        novo_client = nova_app.test_client()
        assert novo_client.get(
            f"/obras/{cenario['obra']}/mudancas", headers=headers
        ).json == lista.json
        assert novo_client.get(
            correcoes[0]["comparacao"], headers=headers
        ).json["versoes"] == versoes


def test_uc13_duas_decisoes_reais_no_mesmo_campo(client, headers, database, obra):
    from support_obras import ID, seed
    seed(database, obra)
    original = obra["entrega"]
    alterado = {"modalidade": "data_exata", "data": "2031-01-01"}

    def decidir(valor, versao, motivo):
        return client.post(f"/obras/{ID}/mudancas", headers=headers, json={
            "alvo": {"tipo": "obra", "id": ID}, "campo": "entrega",
            "novo_valor": valor, "motivo": motivo, "versao": versao,
        })

    primeira = decidir(alterado, 0, "Primeira decisão")
    segunda = decidir(original, 1, "Retorno ao prazo original")
    lista = client.get(f"/obras/{ID}/mudancas", headers=headers)

    assert primeira.status_code == segunda.status_code == lista.status_code == 200
    eventos = lista.json["mudancas"]
    assert len(eventos) == 2
    assert {evento["motivo"] for evento in eventos} == {
        "Primeira decisão", "Retorno ao prazo original"
    }
    assert eventos[0]["id"] != eventos[1]["id"]
    for evento in eventos:
        assert client.get(evento["consulta"], headers=headers).json == evento
