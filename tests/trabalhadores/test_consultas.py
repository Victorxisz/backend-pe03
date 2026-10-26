"""Filtros de trabalhadores, serialização e erros de leitura."""

from datetime import datetime

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot


@pytest.mark.parametrize("rota,campo,busca", [
    ("nome", "nome", "  FICTÍCIO  "), ("cargo", "cargo", "  PEDRE  "),
])
def test_busca_parcial_normaliza_termo_e_ignora_maiusculas(
    client, headers, database, pessoa, rota, campo, busca
):
    database.tbl_trabalhadores.insert_one({
        **pessoa, "_id": ObjectId(), campo: "Sem correspondência", "email": "outra@example.com"
    })
    before = snapshot(database)

    response = client.get(f"/trabalhadores/{rota}/{busca}/", headers=headers)

    assert response.status_code == 200
    assert response.get_json() == [{
        "id": str(pessoa["_id"]), "nome": pessoa["nome"], "email": pessoa["email"],
        "telefone": pessoa["telefone"], "cargo": pessoa["cargo"],
        "obras": pessoa["obras"], "ativo": True, "data_cadastro": None,
    }]
    assert snapshot(database) == before


@pytest.mark.parametrize("rota", ["nome", "cargo"])
def test_busca_escapa_regex(client, headers, database, pessoa, rota):
    database.tbl_trabalhadores.update_one({"_id": pessoa["_id"]}, {"$set": {rota: "A.B"}})
    database.tbl_trabalhadores.insert_one({
        **pessoa, "_id": ObjectId(), rota: "AxB", "email": "outra@example.com"
    })

    response = client.get(f"/trabalhadores/{rota}/A.B/", headers=headers)

    assert response.status_code == 200
    assert [d["id"] for d in response.get_json()] == [str(pessoa["_id"])]


@pytest.mark.parametrize("rota", ["nome", "cargo"])
@pytest.mark.parametrize("termo,status,esperado", [
    ("%20", 422, None), ("inexistente", 200, []),
])
def test_busca_vazia_ou_sem_resultados(
    client, headers, database, pessoa, rota, termo, status, esperado
):
    before = snapshot(database)
    response = client.get(f"/trabalhadores/{rota}/{termo}/", headers=headers)
    assert response.status_code == status
    if esperado is None:
        assert "erro" in response.get_json()
    else:
        assert response.get_json() == esperado
    assert snapshot(database) == before


def test_busca_obra_retorna_apenas_trabalhadores_vinculados(
    client, headers, database, pessoa, obra_existente
):
    database.tbl_trabalhadores.insert_one({
        **pessoa, "_id": ObjectId(), "email": "outra@example.com", "obras": []
    })
    before = snapshot(database)

    response = client.get(f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers)

    assert response.status_code == 200
    assert [d["id"] for d in response.get_json()] == [str(pessoa["_id"])]
    assert snapshot(database) == before


@pytest.mark.parametrize("estado,status,esperado", [
    ("id-invalido", 400, {"erro": "ID da obra inválido"}),
    ("inexistente", 404, {"erro": "Nenhuma obra encontrada"}),
    ("sem-lista", 200, {"mensagem": "Nenhum usuário encontrado"}),
    ("lista-vazia", 200, {"mensagem": "Nenhum usuário encontrado"}),
    ("email-sem-cadastro", 200, []),
])
def test_consulta_obra_sem_resultado(
    client, headers, database, obra_existente, estado, status, esperado
):
    identificador = str(obra_existente["_id"])
    if estado == "id-invalido":
        identificador = "invalido"
    elif estado == "inexistente":
        identificador = str(ObjectId())
    elif estado in ("lista-vazia", "email-sem-cadastro"):
        emails = [] if estado == "lista-vazia" else ["ausente@example.com"]
        database.tbl_obras.update_one(
            {"_id": obra_existente["_id"]}, {"$set": {"trabalhadores": emails}}
        )
    before = snapshot(database)

    response = client.get(f"/trabalhadores/obra/{identificador}/", headers=headers)

    assert response.status_code == status
    assert response.get_json() == esperado
    assert snapshot(database) == before


@pytest.mark.parametrize("path,collection,durante_iteracao", [
    ("/trabalhadores/nome/João/", "colecao_trabalhadores", False),
    ("/trabalhadores/nome/João/", "colecao_trabalhadores", True),
    ("/trabalhadores/cargo/pedreiro/", "colecao_trabalhadores", False),
    ("/trabalhadores/cargo/pedreiro/", "colecao_trabalhadores", True),
    ("/trabalhadores/obra/{obra}/", "colecao_trabalhadores", False),
    ("/trabalhadores/obra/{obra}/", "colecao_trabalhadores", True),
    ("/trabalhadores/obra/{obra}/", "colecao_obras", False),
])
def test_falha_de_leitura_retorna_500_sem_expor_detalhes(
    client, headers, database, pessoa, obra_existente, modulo_trabalhadores,
    monkeypatch, path, collection, durante_iteracao
):
    operation = "find_one" if collection == "colecao_obras" else "find"
    before = snapshot(database)

    def cursor_com_erro():
        yield pessoa
        raise PyMongoError("detalhe interno simulado")

    def falhar(*args, **kwargs):
        if durante_iteracao:
            return cursor_com_erro()
        raise PyMongoError("detalhe interno simulado")

    with monkeypatch.context() as context:
        context.setattr(getattr(modulo_trabalhadores, collection), operation, falhar)
        response = client.get(path.format(obra=obra_existente["_id"]), headers=headers)

    # Inclui a busca por cargo: uma falha do servidor não deve ser 422.
    assert response.status_code == 500
    assert "erro" in response.get_json()
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert snapshot(database) == before


def test_serializacao_documento_ausente(modulo_trabalhadores):
    assert modulo_trabalhadores.trabalhador_para_dict(None) is None


@pytest.mark.parametrize("documento", [
    {}, {"criado_em": datetime(2020, 1, 1)},
    {"criado_em": datetime(2020, 1, 1), "data_cadastro": datetime(2021, 1, 1)},
])
def test_serializacao_campos_opcionais_e_data_legada(modulo_trabalhadores, documento):
    identificador = ObjectId()
    original = {"_id": identificador, "interno": "não publicar", **documento}
    before = original.copy()

    resultado = modulo_trabalhadores.trabalhador_para_dict(original)

    assert resultado == {
        "id": str(identificador), "nome": "", "email": None, "telefone": None,
        "cargo": None, "obras": [], "ativo": None,
        "data_cadastro": documento.get("data_cadastro", documento.get("criado_em")),
    }
    assert original == before
