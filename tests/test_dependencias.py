"""CT-22 a CT-25: contrato HTTP e integridade das dependências."""

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot


def caminho(marco_id, dependencia_id=None):
    base = f"/marcos/{marco_id}/dependencias"
    return base if dependencia_id is None else f"{base}/{dependencia_id}"


@pytest.fixture
def marcos(database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    return tuple(
        database.tbl_marcos.insert_one({
            "obra_id": obra_id,
            "nome": nome,
            "descricao": f"Entrega {nome}",
            "inicio_previsto": "2030-02-01",
            "fim_previsto": "2030-02-15",
            "estado": "a iniciar",
        }).inserted_id
        for nome in ("Alvenaria", "Estrutura", "Fundação", "Cobertura")
    )


def adicionar(client, headers, origem, destino):
    resposta = client.post(
        caminho(origem), json={"depende_de_id": str(destino)}, headers=headers
    )
    assert resposta.status_code == 201, resposta.get_json()
    return resposta.get_json()


def conferir_rejeicao(resposta, status, database, antes):
    assert resposta.status_code == status
    assert resposta.get_json()["mensagem"]
    assert snapshot(database) == antes


def test_ct22_cria_consulta_e_persiste_vinculo(client, headers, database, marcos):
    a, b, c, _ = marcos
    marcos_antes = list(database.tbl_marcos.find())

    vinculo = adicionar(client, headers, a, b)

    assert ObjectId.is_valid(vinculo["id"])
    assert vinculo["marco_id"] == str(a)
    assert vinculo["depende_de_id"] == str(b)
    resposta = client.get(caminho(a), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json() == [{
        **vinculo,
        "marco_nome": "Alvenaria",
        "depende_de_nome": "Estrutura",
    }]
    for outro in (b, c):
        resposta = client.get(caminho(outro), headers=headers)
        assert resposta.status_code == 200
        assert resposta.get_json() == []

    obra_id = database.tbl_marcos.find_one({"_id": a})["obra_id"]
    assert database.tbl_obras.find_one({"_id": obra_id})["dependencias_marcos"] == [{
        "_id": ObjectId(vinculo["id"]), "marco_id": a, "depende_de_id": b,
    }]
    assert list(database.tbl_marcos.find()) == marcos_antes


def test_ct22_criacao_informa_location(client, headers, marcos):
    a, b, _, _ = marcos
    resposta = client.post(
        caminho(a), json={"depende_de_id": str(b)}, headers=headers
    )
    assert resposta.status_code == 201
    assert resposta.headers["Location"] == caminho(a, resposta.get_json()["id"])


def test_consulta_exibe_nomes_atualizados_sem_modificar_vinculo(
    client, headers, database, marcos
):
    a, b, _, _ = marcos
    vinculo = adicionar(client, headers, a, b)
    database.tbl_marcos.update_one({"_id": a}, {"$set": {"nome": "Alvenaria externa"}})
    database.tbl_marcos.update_one({"_id": b}, {"$set": {"nome": "Estrutura revisada"}})
    antes = snapshot(database)

    resposta = client.get(caminho(a), headers=headers)

    assert resposta.status_code == 200
    assert resposta.get_json() == [{
        **vinculo,
        "marco_nome": "Alvenaria externa",
        "depende_de_nome": "Estrutura revisada",
    }]
    assert snapshot(database) == antes


@pytest.mark.parametrize("cenario", ["autorreferencia", "outra_obra", "duplicada"])
def test_ct23_rejeita_relacao_invalida_sem_alterar_grafo(
    client, headers, database, marcos, cenario
):
    a, b, c, _ = marcos
    adicionar(client, headers, a, b)
    destino = a if cenario == "autorreferencia" else b
    if cenario == "outra_obra":
        outra_obra = database.tbl_obras.insert_one({"nome": "Outra obra"}).inserted_id
        database.tbl_marcos.update_one({"_id": c}, {"$set": {"obra_id": outra_obra}})
        destino = c
    antes = snapshot(database)

    resposta = client.post(
        caminho(a), json={"depende_de_id": str(destino)}, headers=headers
    )

    conferir_rejeicao(resposta, 409, database, antes)
    assert resposta.get_json()["campos"] == ["depende_de_id"]


@pytest.mark.parametrize("indireto", [False, True], ids=["direto", "indireto"])
def test_ct24_rejeita_ciclo_preservando_vinculos(
    client, headers, database, marcos, indireto
):
    a, b, c, _ = marcos
    adicionar(client, headers, a, b)
    origem = b
    if indireto:
        adicionar(client, headers, b, c)
        origem = c
    antes = snapshot(database)

    resposta = client.post(
        caminho(origem), json={"depende_de_id": str(a)}, headers=headers
    )

    conferir_rejeicao(resposta, 409, database, antes)
    assert "ciclo" in resposta.get_json()["mensagem"].lower()


def test_ct24_aceita_caminhos_convergentes_sem_ciclo(client, headers, marcos):
    a, b, c, d = marcos
    adicionar(client, headers, a, b)
    adicionar(client, headers, a, c)
    adicionar(client, headers, b, d)
    vinculo = adicionar(client, headers, c, d)
    resposta = client.get(caminho(c), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json() == [{
        **vinculo,
        "marco_nome": "Fundação",
        "depende_de_nome": "Cobertura",
    }]


def test_ct25_remove_apenas_vinculo_solicitado(client, headers, database, marcos):
    a, b, c, _ = marcos
    remover = adicionar(client, headers, a, b)
    manter = adicionar(client, headers, a, c)
    outro = adicionar(client, headers, b, c)
    marcos_antes = list(database.tbl_marcos.find())

    resposta = client.delete(caminho(a, remover["id"]), headers=headers)

    assert resposta.status_code == 204
    assert resposta.data == b""
    assert client.get(caminho(a), headers=headers).get_json() == [{
        **manter,
        "marco_nome": "Alvenaria",
        "depende_de_nome": "Fundação",
    }]
    assert client.get(caminho(b), headers=headers).get_json() == [{
        **outro,
        "marco_nome": "Estrutura",
        "depende_de_nome": "Fundação",
    }]
    assert list(database.tbl_marcos.find()) == marcos_antes
    obra_id = database.tbl_marcos.find_one({"_id": a})["obra_id"]
    salvos = database.tbl_obras.find_one({"_id": obra_id})["dependencias_marcos"]
    assert {str(item["_id"]) for item in salvos} == {manter["id"], outro["id"]}


def test_ct25_remove_ultimo_vinculo_e_permite_recriar(client, headers, marcos):
    a, b, _, _ = marcos
    vinculo = adicionar(client, headers, a, b)
    assert client.delete(caminho(a, vinculo["id"]), headers=headers).status_code == 204
    resposta = client.get(caminho(a), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json() == []
    adicionar(client, headers, a, b)


@pytest.mark.parametrize("cenario", ["inexistente", "outro_marco", "ja_removido"])
def test_ct25_rejeita_exclusao_invalida_sem_alterar_relacoes(
    client, headers, database, marcos, cenario
):
    a, b, c, _ = marcos
    vinculo = adicionar(client, headers, a, b)
    origem = c if cenario == "outro_marco" else a
    identificador = str(ObjectId()) if cenario == "inexistente" else vinculo["id"]
    if cenario == "ja_removido":
        assert client.delete(caminho(a, identificador), headers=headers).status_code == 204
    antes = snapshot(database)

    resposta = client.delete(caminho(origem, identificador), headers=headers)

    conferir_rejeicao(resposta, 404, database, antes)


@pytest.mark.parametrize("dados", [None, [], "texto", {}, {"depende_de_id": " "},
                                    {"depende_de_id": 123}])
def test_corpo_invalido_nao_altera_relacoes(client, headers, database, marcos, dados):
    a, b, _, _ = marcos
    adicionar(client, headers, a, b)
    antes = snapshot(database)
    resposta = client.post(caminho(a), json=dados, headers=headers)
    conferir_rejeicao(resposta, 422, database, antes)


@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
@pytest.mark.parametrize("invalido", [False, True], ids=["inexistente", "malformado"])
def test_marco_invalido_ou_inexistente(
    client, headers, database, marcos, metodo, invalido
):
    _, b, _, _ = marcos
    origem = "id-invalido" if invalido else str(ObjectId())
    url = caminho(origem, ObjectId()) if metodo == "DELETE" else caminho(origem)
    antes = snapshot(database)
    resposta = client.open(
        url, method=metodo, json={"depende_de_id": str(b)}, headers=headers
    )
    conferir_rejeicao(resposta, 400 if invalido else 404, database, antes)


@pytest.mark.parametrize("invalido", [False, True], ids=["inexistente", "malformado"])
def test_destino_invalido_ou_inexistente(client, headers, database, marcos, invalido):
    a, _, _, _ = marcos
    antes = snapshot(database)
    resposta = client.post(
        caminho(a), headers=headers,
        json={"depende_de_id": "id-invalido" if invalido else str(ObjectId())},
    )
    conferir_rejeicao(resposta, 400 if invalido else 404, database, antes)


def test_identificador_de_dependencia_malformado(client, headers, database, marcos):
    a, _, _, _ = marcos
    antes = snapshot(database)
    resposta = client.delete(caminho(a, "id-invalido"), headers=headers)
    conferir_rejeicao(resposta, 400, database, antes)


@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
def test_obra_inexistente_nao_altera_relacoes(
    client, headers, database, marcos, metodo
):
    a, b, _, _ = marcos
    vinculo = adicionar(client, headers, a, b)
    obra_id = database.tbl_marcos.find_one({"_id": a})["obra_id"]
    database.tbl_obras.delete_one({"_id": obra_id})
    antes = snapshot(database)
    url = caminho(a, vinculo["id"]) if metodo == "DELETE" else caminho(a)
    resposta = client.open(
        url, method=metodo, json={"depende_de_id": str(b)}, headers=headers
    )
    conferir_rejeicao(resposta, 404, database, antes)
    assert resposta.get_json()["campos"] == ["obra_id"]


def test_ct24_revalida_ciclo_apos_gravacao_concorrente(
    client, headers, database, marcos, monkeypatch
):
    from app.marcos import repository

    a, b, _, _ = marcos
    salvar = repository.substituir_dependencias
    concorrente = {"_id": ObjectId(), "marco_id": b, "depende_de_id": a}
    intercalou = False

    def intercalar(obra, novos_vinculos):
        nonlocal intercalou
        if not intercalou:
            intercalou = True
            # Outra requisição grava B -> A entre a leitura e a escrita de A -> B.
            assert salvar(obra, [concorrente])
        return salvar(obra, novos_vinculos)

    monkeypatch.setattr(repository, "substituir_dependencias", intercalar)
    marcos_antes = list(database.tbl_marcos.find())
    resposta = client.post(
        caminho(a), json={"depende_de_id": str(b)}, headers=headers
    )

    assert resposta.status_code == 409
    assert "ciclo" in resposta.get_json()["mensagem"].lower()
    obra_id = database.tbl_marcos.find_one({"_id": a})["obra_id"]
    assert database.tbl_obras.find_one({"_id": obra_id})["dependencias_marcos"] == [concorrente]
    assert list(database.tbl_marcos.find()) == marcos_antes


@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
def test_rotas_exigem_autenticacao(client, database, marcos, metodo):
    a, b, _, _ = marcos
    antes = snapshot(database)
    url = caminho(a, ObjectId()) if metodo == "DELETE" else caminho(a)
    resposta = client.open(url, method=metodo, json={"depende_de_id": str(b)})
    assert resposta.status_code == 401
    assert snapshot(database) == antes


@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
def test_falha_de_banco_retorna_500_sem_expor_detalhes(
    client, headers, database, marcos, monkeypatch, metodo
):
    from app.marcos import repository

    a, b, _, _ = marcos
    antes = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    monkeypatch.setattr(repository, "buscar_marco_por_id", falhar)
    url = caminho(a, ObjectId()) if metodo == "DELETE" else caminho(a)
    resposta = client.open(
        url, method=metodo, json={"depende_de_id": str(b)}, headers=headers
    )
    conferir_rejeicao(resposta, 500, database, antes)
    assert "detalhe interno simulado" not in resposta.get_data(as_text=True)
