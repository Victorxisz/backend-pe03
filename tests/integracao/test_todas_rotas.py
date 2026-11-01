"""Exercita todas as operações registradas, com banco isolado e mídia simulada."""

from io import BytesIO
import json

import pytest
from flask import request
from freezegun import freeze_time

from support import snapshot
from support_avancos import backend, transacao_local
from support_midias import config, conteudos


def test_todas_operacoes_possuem_fluxo_de_sucesso(app, client, headers, account, obra, backend, conteudos, transacao_local):
    sucessos = set()

    @app.after_request
    def observar(resposta):
        if request.url_rule is not None and 200 <= resposta.status_code < 300:
            sucessos.add((request.method, request.url_rule.rule))
        return resposta

    def chamar(metodo, caminho, status=200, auth=None, **opcoes):
        r = client.open(caminho, method=metodo, headers=headers if auth is None else auth, **opcoes)
        assert r.status_code == status, (metodo, caminho, r.get_json(silent=True))
        return r

    # Cadastro, correção e remoção de outra conta não encerram a conta do cenário.
    extra = chamar("POST", "/construtora/", 201, auth={}, json={
        "nome": "Empresa extra", "email": "extra@example.com", "telefone": "11987654321", "senha": "Senha_extra123!"}).json
    extra_auth = {"Authorization": "Bearer " + extra["access_token"]}
    extra_id = extra["construtora"]["id"]
    chamar("PATCH", f"/construtora/{extra_id}", auth=extra_auth, json={"nome": "Empresa corrigida"})
    chamar("DELETE", f"/construtora/{extra_id}", auth=extra_auth)
    credenciais = {"email": account["email"], "senha": "Senha_teste123!"}
    login = chamar("POST", "/construtora/login/", auth={}, json=credenciais).json
    chamar("POST", "/construtora/refresh/", auth={"Authorization": "Bearer " + login["refresh_token"]})
    chamar("POST", "/construtora/logout/", auth={"Authorization": "Bearer " + login["access_token"]})
    app.config["CONSTRUTORA_ID"] = str(account["_id"])
    sessao = chamar("POST", "/sessoes", auth={}, json=credenciais).json
    sessao_auth = {"Authorization": "Bearer " + sessao["access_token"]}
    chamar("GET", "/sessoes/atual", auth=sessao_auth)
    chamar("DELETE", "/sessoes/atual", auth=sessao_auth)

    obra_id = chamar("POST", "/obras", 201, json=obra).json["id"]
    assert chamar("GET", f"/obras/{obra_id}/feedback-simulado").json == {"feedbacks": []}
    chamar("GET", "/obras")
    chamar("GET", f"/obras/{obra_id}")
    chamar("PATCH", f"/obras/{obra_id}", json={"nome": "Casa revisada"})
    chamar("PATCH", f"/obras/{obra_id}/estado", json={"estado": "em andamento", "motivo": "Serviço iniciado"})

    def marco(nome):
        return chamar("POST", f"/obras/{obra_id}/marcos", 201, json={"nome": nome, "descricao": "Etapa de teste",
            "inicio_previsto": "2030-01-20", "fim_previsto": "2030-02-20"}).json["id"]

    primeiro, segundo = marco("Fundação"), marco("Estrutura")
    chamar("GET", f"/obras/{obra_id}/marcos")
    chamar("GET", f"/obras/{obra_id}/marcos/{primeiro}")
    dependencia = chamar("POST", f"/marcos/{segundo}/dependencias", 201, json={"depende_de_id": primeiro}).json
    chamar("GET", f"/marcos/{segundo}/dependencias")
    chamar("PATCH", f"/marcos/{primeiro}", json={"estado": "concluído", "motivo": "Etapa inspecionada"})
    chamar("DELETE", f"/marcos/{segundo}/dependencias/{dependencia['id']}", 204)

    trabalhador = chamar("POST", f"/trabalhadores/obra/{obra_id}/", 201, json={
        "nome": "Ana Souza", "email": "ana@example.com", "telefone": "11987654321", "cargo": "Pedreira"}).json["id"]
    chamar("GET", f"/trabalhadores/obra/{obra_id}/")
    chamar("GET", f"/trabalhadores/{trabalhador}/")
    chamar("GET", "/trabalhadores/nome/Ana/")
    chamar("GET", "/trabalhadores/cargo/pedreira/")
    chamar("PATCH", f"/trabalhadores/{trabalhador}/", json={"cargo": "Mestre de obras"})

    def avancar(descricao):
        return chamar("POST", f"/marcos/{primeiro}/avancos", 201, data={"data": "2030-10-01",
            "descricao": descricao, "midias": (BytesIO(conteudos["png"]), "foto.png")}).json

    avanco = avancar("Concretagem")
    avanco_id = avanco["id"]
    chamar("GET", f"/marcos/{primeiro}/avancos")
    chamar("GET", f"/avancos/{avanco_id}")
    chamar("PATCH", f"/avancos/{avanco_id}", json={"descricao": "Concretagem revisada"})
    chamar("GET", f"/avancos/{avanco_id}/midias")
    midia_id = avanco["midias"][0]["id"]
    chamar("GET", f"/midias/{midia_id}")
    assert chamar("GET", f"/midias/{midia_id}/conteudo").data == conteudos["png"]
    chamar("POST", f"/avancos/{avanco_id}/publicacoes", 201, json={})
    chamar("GET", f"/avancos/{avanco_id}/publicacoes")
    chamar("PATCH", f"/avancos/{avanco_id}", json={"descricao": "Concretagem inspecionada", "motivo": "Detalhe conferido"})
    chamar("GET", f"/avancos/{avanco_id}/versoes")
    chamar("GET", f"/obras/{obra_id}/previa")
    descartavel = avancar("Registro a retirar")
    chamar("DELETE", f"/avancos/{descartavel['id']}", 204)

    atual = chamar("GET", f"/obras/{obra_id}").json
    chamar("POST", f"/obras/{obra_id}/mudancas", json={"alvo": {"tipo": "obra", "id": obra_id},
        "campo": "entrega", "novo_valor": {"modalidade": "data_exata", "data": "2031-01-20"},
        "motivo": "Replanejamento", "versao": atual["versao"]})
    historico = chamar("GET", f"/obras/{obra_id}/mudancas").json["mudancas"]
    assert historico
    chamar("GET", historico[0]["consulta"])

    ocorrencia = chamar("POST", f"/obras/{obra_id}/ocorrencias", 201, json={"titulo": "Infiltração",
        "descricao": "Umidade na fachada", "estado": "sem solução", "marco_id": segundo,
        "responsavel_id": trabalhador}).json["id"]
    chamar("GET", f"/obras/{obra_id}/ocorrencias")
    chamar("GET", f"/ocorrencias/{ocorrencia}")
    chamar("POST", f"/ocorrencias/{ocorrencia}/aceitacoes", 201, json={"justificativa": "Limitação técnica constatada"})
    chamar("GET", f"/ocorrencias/{ocorrencia}/aceitacoes")
    resolvida = chamar("PATCH", f"/ocorrencias/{ocorrencia}", json={"versao": 0,
        "transicao": {"estado": "resolvida", "motivo": "Reparo inspecionado"}}).json
    assert len(resolvida["aceitacoes"]) == 1 and resolvida["aceitacoes_do_estado_atual"] == []
    chamar("GET", f"/avancos/{avanco_id}/exclusao")
    chamar("GET", f"/ocorrencias/{ocorrencia}/exclusao")
    chamar("DELETE", f"/ocorrencias/{ocorrencia}", 204, json={"confirmar": True})
    chamar("DELETE", f"/avancos/{avanco_id}", 204, json={"confirmar": True})
    chamar("DELETE", f"/trabalhadores/{trabalhador}/")
    # UC-17 também faz parte do inventário de operações obrigatórias.
    chamar("DELETE", f"/marcos/{segundo}", 204, json={"confirmar": True})
    chamar("DELETE", f"/obras/{obra_id}", 204, json={"confirmar": True})

    obrigatorias = {(metodo, regra.rule) for regra in app.url_map.iter_rules() if regra.endpoint != "static"
                    for metodo in regra.methods - {"HEAD", "OPTIONS"}}
    assert len(obrigatorias) == 55
    assert obrigatorias <= sucessos, sorted(obrigatorias - sucessos)


def test_data_de_ocorrencia_identica_no_post_e_releitura(client, headers, obra):
    obra_id = client.post("/obras", headers=headers, json=obra).json["id"]
    with freeze_time("2030-10-20 12:00:00.123456", ignore=["pymongo"]):
        criada = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers,
            json={"titulo": "Infiltração", "descricao": "Umidade", "estado": "aberta"})
        assert criada.status_code == 201
        consulta = client.get(criada.headers["Location"], headers=headers)
    assert consulta.status_code == 200 and consulta.json == criada.json


@pytest.mark.parametrize("corpo", [None, [], True, 42, "texto", {}])
def test_corpos_invalidos_nao_produzem_erro_interno(app, client, headers, account, obra, database, corpo):
    obra_id = client.post("/obras", headers=headers, json=obra).json["id"]
    marco_id = client.post(f"/obras/{obra_id}/marcos", headers=headers, json={"nome": "Fundação",
        "descricao": "Base", "inicio_previsto": "2030-01-20", "fim_previsto": "2030-02-20"}).json["id"]
    ocorrencia = client.post(f"/obras/{obra_id}/ocorrencias", headers=headers,
        json={"titulo": "Infiltração", "descricao": "Umidade", "estado": "sem solução"}).json["id"]
    inexistente = "507f1f77bcf86cd799439011"
    comandos = [
        ("POST", "/construtora/"), ("POST", "/construtora/login/"),
        ("PATCH", f"/construtora/{account['_id']}"), ("POST", "/obras"),
        ("PATCH", f"/obras/{obra_id}"), ("PATCH", f"/obras/{obra_id}/estado"),
        ("POST", f"/obras/{obra_id}/marcos"), ("PATCH", f"/marcos/{marco_id}"),
        ("POST", f"/marcos/{marco_id}/dependencias"), ("POST", f"/marcos/{marco_id}/avancos"),
        ("PATCH", f"/avancos/{inexistente}"),
        ("POST", f"/obras/{obra_id}/mudancas"), ("POST", f"/obras/{obra_id}/ocorrencias"),
        ("PATCH", f"/ocorrencias/{ocorrencia}"), ("POST", f"/ocorrencias/{ocorrencia}/aceitacoes"),
        ("POST", f"/trabalhadores/obra/{obra_id}/"), ("PATCH", f"/trabalhadores/{inexistente}/"),
    ]
    antes = snapshot(database)
    for metodo, caminho in comandos:
        r = client.open(caminho, method=metodo, headers=headers,
                        data=json.dumps(corpo), content_type="application/json")
        assert 400 <= r.status_code < 500 and r.is_json, (metodo, caminho, r.status_code)
        assert snapshot(database) == antes, (metodo, caminho)
    app.config["CONSTRUTORA_ID"] = str(account["_id"])
    r = client.post("/sessoes", data=json.dumps(corpo), content_type="application/json")
    assert 400 <= r.status_code < 500 and r.is_json
    assert snapshot(database) == antes
