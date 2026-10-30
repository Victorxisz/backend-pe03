"""Consulta individual e listagem de marcos, sem banco externo."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import JWTManager
from pymongo.errors import ServerSelectionTimeoutError

from support import snapshot


def caminho(obra_id, marco_id=None):
    base = f"/obras/{obra_id}/marcos"
    return base if marco_id is None else f"{base}/{marco_id}"


@pytest.fixture
def marco(database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    documento = {
        "_id": ObjectId(),
        "obra_id": obra_id,
        "nome": "Fundação",
        "descricao": "Fundação conferida",
        "inicio_previsto": "2030-02-01",
        "fim_previsto": "2030-02-15",
        "estado": "a iniciar",
    }
    database.tbl_marcos.insert_one(documento)
    return documento


def test_consulta_individual_sem_corpo(client, headers, database, marco):
    antes = snapshot(database)

    resposta = client.get(caminho(marco["obra_id"], marco["_id"]), headers=headers)

    assert resposta.status_code == 200
    assert resposta.is_json
    assert resposta.get_json() == {
        **{chave: valor for chave, valor in marco.items() if chave != "_id"},
        "id": str(marco["_id"]),
        "obra_id": str(marco["obra_id"]),
    }
    assert "Location" not in resposta.headers
    assert snapshot(database) == antes


def test_listagem_preserva_campos_ordem_e_isolamento(client, headers, database, marco):
    primeiro = {**marco, "_id": ObjectId("000000000000000000000001"), "nome": "Primeiro"}
    database.tbl_marcos.insert_one(primeiro)
    outra_obra = database.tbl_obras.insert_one({"nome": "Outra obra"}).inserted_id
    database.tbl_marcos.insert_one({**marco, "_id": ObjectId(), "obra_id": outra_obra})
    antes = snapshot(database)

    resposta = client.get(caminho(marco["obra_id"]), headers=headers)

    assert resposta.status_code == 200
    assert resposta.get_json() == [
        {"id": str(documento["_id"]), **{
            chave: valor for chave, valor in documento.items()
            if chave not in {"_id", "obra_id"}
        }}
        for documento in (primeiro, marco)
    ]
    assert "Location" not in resposta.headers
    assert snapshot(database) == antes


def test_obra_existente_sem_marcos(client, headers, database, obra):
    obra_id = database.tbl_obras.insert_one(obra).inserted_id
    resposta = client.get(caminho(obra_id), headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json() == []


@pytest.mark.parametrize("individual", [False, True])
def test_consultas_ignoram_corpo_json(client, headers, marco, individual):
    url = caminho(marco["obra_id"], marco["_id"] if individual else None)
    resposta = client.get(url, headers=headers, data="{", content_type="application/json")
    assert resposta.status_code == 200


@pytest.mark.parametrize("individual", [False, True])
@pytest.mark.parametrize("invalido", [None, "", " ", "invalido", 123, [], {}])
def test_servicos_rejeitam_id_de_obra_antes_do_banco(app, individual, invalido):
    from app.marcos import service

    with patch.object(service.repository, "obra_existe") as consultar:
        with pytest.raises(service.ErroMarco) as capturado:
            if individual:
                service.buscar_marco(invalido, str(ObjectId()))
            else:
                service.listar_marcos(invalido)
    assert capturado.value.status == 400
    assert capturado.value.campos == (["obra_id"] if individual else ["id"])
    consultar.assert_not_called()


@pytest.mark.parametrize("invalido", [None, "", " ", "invalido", 123, [], {}])
def test_servico_rejeita_id_de_marco_antes_do_banco(app, invalido):
    from app.marcos import service

    with patch.object(service.repository, "obra_existe") as consultar:
        with pytest.raises(service.ErroMarco) as capturado:
            service.buscar_marco(str(ObjectId()), invalido)
    assert capturado.value.status == 400
    assert capturado.value.campos == ["marco_id"]
    consultar.assert_not_called()


@pytest.mark.parametrize(
    "cenario,status,mensagem,campos",
    [
        ("obra-invalida-lista", 400, "ID da obra inválido", ["id"]),
        ("obra-ausente-lista", 404, "Obra não encontrada", ["id"]),
        ("obra-invalida-detalhe", 400, "ID inválido: obra_id", ["obra_id"]),
        ("marco-invalido", 400, "ID inválido: marco_id", ["marco_id"]),
        ("obra-ausente-detalhe", 404, "Obra não encontrada", ["obra_id"]),
        ("marco-ausente", 404, "Marco não encontrado", ["marco_id"]),
        ("outra-obra", 404, "Marco não encontrado", ["marco_id"]),
    ],
)
def test_erros_das_consultas(
    client, headers, database, marco, cenario, status, mensagem, campos
):
    obra_id, marco_id = marco["obra_id"], marco["_id"]
    if cenario.startswith("obra-invalida"):
        obra_id = "invalido"
    elif cenario.startswith("obra-ausente"):
        # O marco continua existindo, mas a obra foi removida.
        database.tbl_obras.delete_one({"_id": obra_id})
    elif cenario == "marco-invalido":
        marco_id = "invalido"
    elif cenario == "marco-ausente":
        marco_id = ObjectId()
    elif cenario == "outra-obra":
        obra_id = database.tbl_obras.insert_one({"nome": "Outra obra"}).inserted_id
    antes = snapshot(database)

    url = caminho(obra_id, None if cenario.endswith("lista") else marco_id)
    resposta = client.get(url, headers=headers)

    assert resposta.status_code == status
    assert resposta.get_json() == {"mensagem": mensagem, "campos": campos}
    assert snapshot(database) == antes


@pytest.mark.parametrize("individual", [False, True])
def test_serializa_object_ids_aninhados_sem_alterar_documento(
    client, headers, database, marco, individual
):
    from app.marcos import service

    referencia = ObjectId()
    marco.update(
        responsavel=referencia,
        dependencias=[referencia, {"origem": [referencia, {"_id": referencia}]}],
        metadados={"destino": referencia, "itens": [[referencia]], "nota": None},
    )
    original = deepcopy(marco)
    antes = snapshot(database)
    alvo = ("app.marcos.repository.buscar_marco_por_id" if individual
            else "app.obras.repository.consultar_marcos")
    with patch(alvo, return_value=marco if individual else [marco]):
        resposta = client.get(
            caminho(marco["obra_id"], marco["_id"] if individual else None),
            headers=headers,
        )
        resultado = (service.buscar_marco(marco["obra_id"], marco["_id"])
                     if individual else service.listar_marcos(marco["obra_id"])[0])

    assert resposta.status_code == 200
    corpo = resposta.get_json() if individual else resposta.get_json()[0]
    assert corpo == resultado
    assert corpo["id"] == str(marco["_id"])
    assert "_id" not in corpo
    assert corpo["responsavel"] == str(referencia)
    assert corpo["dependencias"] == [
        str(referencia), {"origem": [str(referencia), {"_id": str(referencia)}]}
    ]
    assert corpo["metadados"] == {
        "destino": str(referencia), "itens": [[str(referencia)]], "nota": None,
    }
    assert ("obra_id" in corpo) is individual
    assert marco == original
    resultado["metadados"]["itens"][0].append("novo")
    resultado["dependencias"][1]["origem"].clear()
    assert marco == original
    assert snapshot(database) == antes


@pytest.mark.parametrize("individual", [False, True])
@pytest.mark.parametrize(
    "situacao,status",
    [("ausente", 401), ("expirado", 401), ("revogado", 401),
     ("refresh", 422), ("tipo-incorreto", 403), ("inativa", 401)],
)
def test_autenticacao_das_consultas(
    client, emitir_headers, database, account, marco, individual, situacao, status
):
    opcoes = {}
    if situacao == "expirado":
        opcoes["expirado"] = True
    elif situacao == "refresh":
        opcoes["tipo_token"] = "refresh"
    elif situacao == "revogado":
        opcoes["claims"] = {"sessao_id": "encerrada"}
        database.tbl_sessoes_revogadas.insert_one({"_id": "encerrada"})
    elif situacao == "tipo-incorreto":
        opcoes["claims"] = {"tipo": "trabalhador"}
    elif situacao == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    auth = {} if situacao == "ausente" else emitir_headers(**opcoes)
    antes = snapshot(database)

    resposta = client.get(
        caminho(marco["obra_id"], marco["_id"] if individual else None), headers=auth
    )

    assert resposta.status_code == status
    assert snapshot(database) == antes


@pytest.mark.parametrize(
    "individual,alvo,mensagem",
    [
        (False, "app.marcos.repository.buscar_obra_por_id",
         "Não foi possível consultar os marcos da obra"),
        (False, "app.obras.repository.consultar_marcos",
         "Não foi possível consultar os marcos da obra"),
        (True, "app.marcos.repository.buscar_obra_por_id", "Não foi possível buscar o marco"),
        (True, "app.marcos.repository.buscar_marco_por_id", "Não foi possível buscar o marco"),
    ],
)
def test_falha_de_banco_sem_expor_detalhes(
    client, headers, database, marco, individual, alvo, mensagem
):
    antes = snapshot(database)
    with patch(alvo, side_effect=ServerSelectionTimeoutError("detalhe privado")):
        resposta = client.get(
            caminho(marco["obra_id"], marco["_id"] if individual else None), headers=headers
        )
    assert resposta.status_code == 500
    assert resposta.get_json() == {"mensagem": mensagem}
    assert "detalhe privado" not in resposta.get_data(as_text=True)
    assert "Location" not in resposta.headers
    assert snapshot(database) == antes


@pytest.mark.parametrize("inverter", [False, True])
def test_um_handler_por_get_independente_da_ordem_dos_blueprints(
    app, headers, marco, inverter
):
    from app.marcos.routes import marcos_bp
    from app.obras.routes import obras_bp

    application = Flask(__name__)
    application.config.update(app.config)
    JWTManager(application)
    blueprints = (marcos_bp, obras_bp) if inverter else (obras_bp, marcos_bp)
    for blueprint in blueprints:
        application.register_blueprint(blueprint)
    for individual in (False, True):
        regra = "/obras/<string:obra_id>/marcos"
        if individual:
            regra += "/<string:marco_id>"
        for instancia in (app, application):
            handlers = [r for r in instancia.url_map.iter_rules()
                        if r.rule == regra and "GET" in r.methods]
            assert len(handlers) == 1
            assert handlers[0].endpoint == (
                "marcos.consultar_marco" if individual else "marcos.consultar_marcos"
            )
        resposta = application.test_client().get(
            caminho(marco["obra_id"], marco["_id"] if individual else None), headers=headers
        )
        assert resposta.status_code == 200


def test_servico_anterior_de_obras_mantem_contrato(app, marco):
    from app.marcos import service as marcos_service
    from app.obras import service as obras_service

    assert obras_service.listar_marcos(str(marco["obra_id"])) == (
        marcos_service.listar_marcos(str(marco["obra_id"]))
    )
    with pytest.raises(obras_service.ErroObra) as capturado:
        obras_service.listar_marcos("invalido")
    assert capturado.value.status == 400
    assert capturado.value.campos == ["id"]
