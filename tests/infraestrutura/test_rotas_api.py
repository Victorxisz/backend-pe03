"""Contratos transversais das rotas realmente registradas na aplicação."""

import pytest

from support import snapshot


def rotas_registradas(app):
    return [regra for regra in app.url_map.iter_rules() if regra.endpoint != "static"]


def test_inventario_obrigatorio_uc01_a_uc21(app):
    """Ausência de uma rota destes UCs falha, sem depender de marker opcional."""
    operacoes = [
        (("POST",), "/construtora/"),
        (("POST",), "/construtora/login/"),
        (("POST",), "/construtora/refresh/"),
        (("POST",), "/construtora/logout/"),
        (("PATCH", "DELETE"), "/construtora/{id}"),
        (("POST",), "/sessoes"),
        (("GET", "DELETE"), "/sessoes/atual"),
        (("GET", "POST"), "/obras"),
        (("GET", "PATCH", "DELETE"), "/obras/{id}"),
        (("PATCH",), "/obras/{id}/estado"),
        (("GET", "POST"), "/obras/{id}/marcos"),
        (("GET",), "/obras/{id}/marcos/{id}"),
        (("PATCH", "DELETE"), "/marcos/{id}"),
        (("GET", "POST"), "/marcos/{id}/dependencias"),
        (("DELETE",), "/marcos/{id}/dependencias/{id}"),
        (("GET", "POST"), "/marcos/{id}/avancos"),
        (("GET", "PATCH", "DELETE"), "/avancos/{id}"),
        (("GET",), "/avancos/{id}/exclusao"),
        (("GET",), "/avancos/{id}/midias"),
        (("GET",), "/midias/{id}"),
        (("GET",), "/midias/{id}/conteudo"),
        (("GET", "POST"), "/avancos/{id}/publicacoes"),
        (("GET",), "/obras/{id}/previa"),
        (("GET",), "/obras/{id}/feedback-simulado"),
        (("GET",), "/avancos/{id}/versoes"),
        (("GET", "POST"), "/obras/{id}/mudancas"),
        (("GET",), "/mudancas/{id}"),
        (("GET", "POST"), "/obras/{id}/ocorrencias"),
        (("GET", "PATCH", "DELETE"), "/ocorrencias/{id}"),
        (("GET",), "/ocorrencias/{id}/exclusao"),
        (("GET", "POST"), "/ocorrencias/{id}/aceitacoes"),
        (("GET", "POST"), "/trabalhadores/obra/{id}/"),
        (("GET", "PATCH", "DELETE"), "/trabalhadores/{id}/"),
        (("GET",), "/trabalhadores/nome/Ana/"),
        (("GET",), "/trabalhadores/cargo/pedreiro/"),
    ]
    adaptador = app.url_map.bind("localhost")
    for metodos, caminho in operacoes:
        for metodo in metodos:
            adaptador.match(caminho.format(id="507f1f77bcf86cd799439011"), method=metodo)


def caminho_de_teste(regra):
    caminho = regra.rule
    for argumento in regra.arguments:
        caminho = caminho.replace(f"<string:{argumento}>", "507f1f77bcf86cd799439011")
    return caminho


def test_preflight_de_todas_as_rotas_sem_sessao(client, database):
    """O navegador negocia CORS sem token antes da chamada autenticada."""
    antes = snapshot(database)
    for regra in rotas_registradas(client.application):
        for metodo in regra.methods - {"HEAD", "OPTIONS"}:
            resposta = client.options(caminho_de_teste(regra), headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": metodo,
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            })
            assert resposta.status_code == 200, (regra.rule, metodo, resposta.get_json())
            assert resposta.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
            assert metodo in resposta.headers.get("Access-Control-Allow-Methods", "")
    assert snapshot(database) == antes


ROTAS_MARCOS = [
    ("POST", "/obras/507f1f77bcf86cd799439011/marcos"),
    ("GET", "/marcos/507f1f77bcf86cd799439011/dependencias"),
    ("POST", "/marcos/507f1f77bcf86cd799439011/dependencias"),
    ("DELETE", "/marcos/507f1f77bcf86cd799439011/dependencias/507f1f77bcf86cd799439012"),
    ("PATCH", "/marcos/507f1f77bcf86cd799439011"),
]


@pytest.mark.parametrize("situacao,status", [("perfil_incorreto", 403), ("inativa", 401), ("removida", 401)])
def test_todas_as_rotas_de_marcos_exigem_construtora_ativa(client, database, account, emitir_headers, situacao, status):
    if situacao == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    elif situacao == "removida":
        database.tbl_construtora.delete_one({"_id": account["_id"]})
    claims = {"tipo": "trabalhador"} if situacao == "perfil_incorreto" else {}
    auth = emitir_headers(claims=claims)
    antes = snapshot(database)
    for metodo, caminho in ROTAS_MARCOS:
        resposta = client.open(caminho, method=metodo, json={}, headers=auth)
        assert resposta.status_code == status, (metodo, caminho, resposta.get_json())
    assert snapshot(database) == antes


def test_rotas_protegidas_rejeitam_chamada_sem_token(client, database):
    publicas = {"construtora.cadastrar_construtora", "construtora.login_construtora", "sessoes.criar_sessao"}
    antes = snapshot(database)
    for regra in rotas_registradas(client.application):
        if regra.endpoint in publicas:
            continue
        for metodo in regra.methods - {"HEAD", "OPTIONS"}:
            resposta = client.open(caminho_de_teste(regra), method=metodo, json={})
            assert resposta.status_code == 401, (metodo, regra.rule, resposta.get_json())
    assert snapshot(database) == antes


def test_conta_inativa_nao_pode_editar_ou_excluir_cadastro(client, database, account, headers):
    database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    antes = snapshot(database)
    for metodo in ("PATCH", "DELETE"):
        resposta = client.open(f"/construtora/{account['_id']}", method=metodo,
                               json={"nome": "Alteração indevida"}, headers=headers)
        assert resposta.status_code == 403
        assert resposta.get_json()["erro"] == "Sua conta está desativada"
    assert snapshot(database) == antes


def test_ids_invalidos_nao_produzem_erro_interno(client, database, headers):
    antes = snapshot(database)
    for regra in rotas_registradas(client.application):
        if not regra.arguments:
            continue
        caminho = regra.rule
        for argumento in regra.arguments:
            caminho = caminho.replace(f"<string:{argumento}>", "invalido")
        for metodo in regra.methods - {"HEAD", "OPTIONS"}:
            resposta = client.open(caminho, method=metodo, json={}, headers=headers)
            assert resposta.status_code < 500, (metodo, caminho, resposta.get_json())
            assert resposta.is_json
    assert snapshot(database) == antes
