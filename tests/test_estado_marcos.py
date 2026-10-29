"""CT-26 a CT-30: estado de marco, dependências e histórico."""

from bson import ObjectId
import pytest
from datetime import datetime
from unittest.mock import Mock

from support import snapshot


PATH = "/marcos/{}"


def criar_marco(database, estado="a iniciar", dependencias=None, nome="Estrutura", obra_id=None):
    if obra_id is None:
        if dependencias:
            obra_id = database.tbl_marcos.find_one({"_id": dependencias[0]})["obra_id"]
        else:
            obra_id = database.tbl_obras.insert_one({"nome": "Obra teste"}).inserted_id
    documento = {
        "obra_id": obra_id,
        "nome": nome,
        "descricao": "Execução da estrutura",
        "estado": estado,
        "dependencias": dependencias or [],
    }
    return database.tbl_marcos.insert_one(documento).inserted_id


def payload(estado="em andamento", **extra):
    return {"estado": estado, "motivo": "Atualização informada pela construtora", **extra}


@pytest.mark.atlas
def test_ct26_altera_estado_e_registra_autor_instante_e_motivo(client, headers, database, account):
    marco_id = criar_marco(database)

    response = client.patch(PATH.format(marco_id), json=payload(), headers=headers)

    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "em andamento"
    evento = database.tbl_historico.find_one({"alvo.id": marco_id})
    assert evento["estado_anterior"] == "a iniciar"
    assert evento["estado_novo"] == "em andamento"
    assert evento["motivo"] == payload()["motivo"]
    assert evento["autor"] == str(account["_id"])
    assert evento["instante"] == datetime(2030, 10, 20, 12)


def test_ct27_aviso_permite_cancelar_sem_alterar_estado(client, headers, database):
    pre_requisito = criar_marco(database, nome="Fundação")
    marco_id = criar_marco(database, dependencias=[pre_requisito])
    before = snapshot(database)

    response = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)

    assert response.status_code == 409
    assert response.get_json()["codigo"] == "DEPENDENCIAS_PENDENTES"
    assert response.get_json()["dependencias"][0]["nome"] == "Fundação"
    assert snapshot(database) == before


@pytest.mark.atlas
def test_ct28_confirmacao_revalida_dependencias_e_registra_decisao(client, headers, database):
    pre_requisito = criar_marco(database, estado="em andamento")
    marco_id = criar_marco(database, dependencias=[pre_requisito])
    dados = payload("concluído", confirmar_dependencias=True)

    aviso = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)
    assert aviso.status_code == 409
    response = client.patch(PATH.format(marco_id), json=dados, headers=headers)
    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "concluído"
    evento = database.tbl_historico.find_one({"alvo.id": marco_id})
    assert evento["confirmou_dependencias_pendentes"] is True
    assert evento["dependencias_pendentes"][0]["id"] == str(pre_requisito)

    # A revalidação na requisição confirmada permite concluir se já foi resolvida.
    segundo = criar_marco(database, dependencias=[pre_requisito])
    aviso = client.patch(PATH.format(segundo), json=payload("concluído"), headers=headers)
    assert aviso.status_code == 409
    database.tbl_marcos.update_one({"_id": pre_requisito}, {"$set": {"estado": "concluído"}})
    response = client.patch(PATH.format(segundo), json=dados, headers=headers)
    assert response.status_code == 200
    evento = database.tbl_historico.find_one({"alvo.id": segundo})
    assert evento["confirmou_dependencias_pendentes"] is False
    assert evento["dependencias_pendentes"] == []


@pytest.mark.atlas
@pytest.mark.parametrize("estado_reaberto", ["a iniciar", "em andamento"])
def test_ct29_reabertura_preserva_os_dois_eventos(client, headers, database, estado_reaberto):
    marco_id = criar_marco(database)

    response = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)
    assert response.status_code == 200

    response = client.patch(PATH.format(marco_id), json=payload(estado_reaberto), headers=headers)

    assert response.status_code == 200
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == estado_reaberto
    eventos = list(database.tbl_historico.find({"alvo.id": marco_id}))
    assert len(eventos) == 2
    transicoes = {(e["estado_anterior"], e["estado_novo"]) for e in eventos}
    assert transicoes == {("a iniciar", "concluído"), ("concluído", estado_reaberto)}


@pytest.mark.atlas
def test_ct30_falha_ao_gravar_historico_nao_altera_estado(client, headers, database, monkeypatch):
    marco_id = criar_marco(database)

    chamadas = []

    def falhar(_evento, *, session=None):
        # Comprova que o UPDATE aconteceu antes da falha, dentro da transação.
        import db
        assert session is not None
        marco = db.colecao_marcos.find_one({"_id": marco_id}, session=session)
        assert marco["estado"] == "em andamento"
        chamadas.append(True)
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("app.historico.repository.inserir_evento", falhar)
    response = client.patch(PATH.format(marco_id), json=payload(), headers=headers)

    assert response.status_code == 500
    assert chamadas == [True]
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "a iniciar"
    assert database.tbl_historico.count_documents({}) == 0


@pytest.mark.parametrize("dados", [
    {}, [], None,
    {"estado": "em andamento"},
    {"motivo": "Teste"},
    payload("invalido"), payload(None), payload(1), payload([]),
    payload(motivo=""), payload(motivo="   "), payload(motivo=None),
    payload(confirmar_dependencias="true"),
    payload(confirmar_dependencias=1),
    payload(confirmar_dependencias=None),
    payload(autor="outro"),
])
def test_dados_invalidos_nao_alteram_estado_ou_historico(client, headers, database, dados):
    marco_id = criar_marco(database)
    antes = snapshot(database)
    resposta = client.patch(PATH.format(marco_id), json=dados, headers=headers)
    assert resposta.status_code == 422
    assert snapshot(database) == antes


def test_dependencia_criada_pela_api_aparece_no_aviso(client, headers, database):
    dependencia_id = criar_marco(database, nome="Fundação")
    obra_id = database.tbl_marcos.find_one({"_id": dependencia_id})["obra_id"]
    marco_id = criar_marco(database, obra_id=obra_id)
    cadastro = client.post(
        f"/marcos/{marco_id}/dependencias",
        json={"depende_de_id": str(dependencia_id)}, headers=headers,
    )
    assert cadastro.status_code == 201
    antes = snapshot(database)
    resposta = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "DEPENDENCIAS_PENDENTES"
    assert resposta.get_json()["dependencias"] == [{
        "id": str(dependencia_id), "nome": "Fundação", "estado": "a iniciar",
    }]
    assert snapshot(database) == antes


@pytest.mark.parametrize("caso", ["id_invalido", "inexistente", "outra_obra"])
def test_dependencia_inconsistente_impede_conclusao(client, headers, database, caso):
    marco_id = criar_marco(database)
    dependencia_id = {
        "id_invalido": "invalido",
        "inexistente": ObjectId(),
        "outra_obra": criar_marco(database),
    }[caso]
    database.tbl_marcos.update_one(
        {"_id": marco_id}, {"$set": {"dependencias": [dependencia_id]}},
    )
    antes = snapshot(database)
    resposta = client.patch(
        PATH.format(marco_id),
        json=payload("concluído", confirmar_dependencias=True), headers=headers,
    )
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "DEPENDENCIA_INCONSISTENTE"
    assert snapshot(database) == antes


def test_dependencia_repetida_nao_duplica_aviso(client, headers, database):
    dependencia_id = criar_marco(database)
    marco_id = criar_marco(database, dependencias=[dependencia_id, str(dependencia_id)])
    resposta = client.patch(PATH.format(marco_id), json=payload("concluído"), headers=headers)
    assert resposta.status_code == 409
    assert len(resposta.get_json()["dependencias"]) == 1


def test_patch_exige_autenticacao(client, database):
    marco_id = criar_marco(database)
    antes = snapshot(database)
    resposta = client.patch(PATH.format(marco_id), json=payload())
    assert resposta.status_code == 401
    assert snapshot(database) == antes


@pytest.mark.parametrize("identificador,status", [("invalido", 400), (str(ObjectId()), 404)])
def test_marco_invalido_ou_inexistente(client, headers, database, identificador, status):
    antes = snapshot(database)
    resposta = client.patch(PATH.format(identificador), json=payload(), headers=headers)
    assert resposta.status_code == status
    assert snapshot(database) == antes


def test_conflito_concorrente_retorna_codigo_especifico(client, headers, database, monkeypatch):
    from app.marcos import repository
    marco_id = criar_marco(database)
    antes = snapshot(database)
    salvar = Mock(side_effect=repository.EstadoMarcoAlterado())
    monkeypatch.setattr(repository, "salvar_estado_com_historico", salvar)
    resposta = client.patch(PATH.format(marco_id), json=payload(), headers=headers)
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "MARCO_ALTERADO_CONCORRENTEMENTE"
    salvar.assert_called_once()
    assert snapshot(database) == antes


@pytest.mark.atlas
def test_historico_inserido_tambem_e_revertido_em_falha(client, headers, database, monkeypatch):
    from app.historico import repository
    marco_id = criar_marco(database)
    inserir = repository.inserir_evento
    chamadas = []

    def falhar_apos_inserir(evento, *, session=None):
        inserir(evento, session=session)
        chamadas.append(True)
        raise RuntimeError("falha após inserir histórico")

    monkeypatch.setattr(repository, "inserir_evento", falhar_apos_inserir)
    resposta = client.patch(PATH.format(marco_id), json=payload(), headers=headers)
    assert resposta.status_code == 500
    assert chamadas == [True]
    assert database.tbl_marcos.find_one({"_id": marco_id})["estado"] == "a iniciar"
    assert database.tbl_historico.count_documents({}) == 0
