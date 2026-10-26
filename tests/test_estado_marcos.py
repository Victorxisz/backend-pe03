"""CT-26 a CT-30: estado de marco, dependências e histórico."""

from bson import ObjectId

from support import snapshot


PATH = "/api/v1/marcos/{}"


def criar_marco(database, estado="a iniciar", dependencias=None, nome="Estrutura"):
    documento = {
        "obra_id": ObjectId(),
        "nome": nome,
        "descricao": "Execução da estrutura",
        "estado": estado,
        "dependencias": dependencias or [],
    }
    return database.tbl_marcos.insert_one(documento).inserted_id


def payload(estado="em andamento", **extra):
    return {"estado": estado, "motivo": "Atualização informada pela construtora", **extra}


def test_ct26_altera_estado_e_registra_autor_instante_e_motivo(client, headers, database):
    marco_id = criar_marco(database)

    response = client.patch(PATH.format(marco_id), json=payload(), headers=headers)

    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "em andamento"
    evento = database.tbl_historico.find_one({"alvo.id": marco_id})
    assert evento["estado_anterior"] == "a iniciar"
    assert evento["estado_novo"] == "em andamento"
    assert evento["motivo"] == payload()["motivo"]
    assert evento["autor"]
    assert evento["instante"]


def test_ct27_aviso_permite_cancelar_sem_alterar_estado(client, headers, database):
    pre_requisito = criar_marco(database, nome="Fundação")
    marco_id = criar_marco(database, dependencias=[pre_requisito])
    before = snapshot(database)

    response = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)

    assert response.status_code == 409
    assert response.get_json()["codigo"] == "DEPENDENCIAS_PENDENTES"
    assert response.get_json()["dependencias"][0]["nome"] == "Fundação"
    assert snapshot(database) == before


def test_ct28_confirmacao_revalida_dependencias_e_registra_decisao(client, headers, database):
    pre_requisito = criar_marco(database, estado="em andamento")
    marco_id = criar_marco(database, dependencias=[pre_requisito])
    dados = payload("concluído", confirmar_dependencias=True)

    response = client.patch(PATH.format(marco_id), json=dados, headers=headers)
    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "concluído"
    evento = database.tbl_historico.find_one({"alvo.id": marco_id})
    assert evento["confirmou_dependencias_pendentes"] is True
    assert evento["dependencias_pendentes"][0]["id"] == str(pre_requisito)

    # A revalidação na requisição confirmada permite concluir se já foi resolvida.
    segundo = criar_marco(database, dependencias=[pre_requisito])
    database.tbl_marcos.update_one({"_id": pre_requisito}, {"$set": {"estado": "concluído"}})
    response = client.patch(PATH.format(segundo), json=dados, headers=headers)
    assert response.status_code == 200
    evento = database.tbl_historico.find_one({"alvo.id": segundo})
    assert evento["confirmou_dependencias_pendentes"] is False
    assert evento["dependencias_pendentes"] == []


def test_ct29_reabertura_preserva_os_dois_eventos(client, headers, database):
    marco_id = criar_marco(database)

    response = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)
    assert response.status_code == 200

    response = client.patch(PATH.format(marco_id), json=payload("em andamento"), headers=headers)

    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "em andamento"
    eventos = list(database.tbl_historico.find({"alvo.id": marco_id}))
    assert len(eventos) == 2
    transicoes = {(e["estado_anterior"], e["estado_novo"]) for e in eventos}
    assert transicoes == {("a iniciar", "concluído"), ("concluído", "em andamento")}


def test_ct30_falha_ao_gravar_historico_nao_altera_estado(client, headers, database, monkeypatch):
    marco_id = criar_marco(database)

    def falhar(_evento):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("app.historico.repository.inserir_evento", falhar)
    response = client.patch(PATH.format(marco_id), json=payload(), headers=headers)

    assert response.status_code == 500
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "a iniciar"
    assert database.tbl_historico.count_documents({}) == 0
