"""UC-21/CT-102–106 e CT-50, HTTP real com banco/provedor simulados.

--atlas usa transações e coleções temporárias reais; o provedor permanece simulado.
"""

from io import BytesIO
from unittest.mock import Mock

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError
from werkzeug.datastructures import FileStorage

from support import snapshot
from support_avancos import backend, transacao_local
from support_midias import config, conteudos


@pytest.fixture
def cenario(app, database, account, backend, transacao_local, conteudos):
    from scripts.carregar_dados_demonstracao import carregar
    obra, marco, outra, outro_marco = (ObjectId() for _ in range(4))
    database.tbl_obras.insert_many([
        {"_id": obra, "nome": "Obra fictícia A", "autor": str(account["_id"])},
        {"_id": outra, "nome": "Obra fictícia B", "autor": str(account["_id"])},
    ])
    database.tbl_marcos.insert_many([
        {"_id": marco, "obra_id": obra, "nome": "Marco A"},
        {"_id": outro_marco, "obra_id": outra, "nome": "Marco B"},
    ])

    def carga():
        return carregar(str(obra), str(marco), str(account["_id"]),
                        FileStorage(stream=BytesIO(conteudos["png"]), filename="exemplo.png"),
                        data="2030-01-01")

    resultado = carga()
    return {**resultado, "outra": outra, "outro_marco": outro_marco, "carga": carga,
            "url": f"/obras/{obra}/feedback-simulado"}


def test_ct102_tipos_identidade_e_origem(client, headers, cenario):
    resposta = client.get(cenario["url"], headers=headers)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "private, no-store"
    itens = resposta.json["feedbacks"]
    assert {x["tipo"] for x in itens} == {"avaliacao", "compreensao", "duvida"}
    assert all(x["simulado"] is True and x["origem"] == "simulado"
               and x["cliente"]["ficticio"] is True for x in itens)
    assert all(x["alvo"] == {"tipo": "obra", "id": cenario["obra_id"]} for x in itens)


def test_ct103_contextos_e_vazio(client, headers, cenario):
    for filtro, tipo in (("marco_id", "marco"), ("atualizacao_id", "atualizacao")):
        valor = cenario["marco_id" if filtro == "marco_id" else "avanco_id"]
        resposta = client.get(cenario["url"], query_string={filtro: valor}, headers=headers)
        assert resposta.status_code == 200
        assert len(resposta.json["feedbacks"]) == 1
        assert resposta.json["feedbacks"][0]["alvo"] == {"tipo": tipo, "id": valor}
    assert client.get(f"/obras/{cenario['outra']}/feedback-simulado", headers=headers).json == {"feedbacks": []}
    for filtro, valor in (("marco_id", cenario["outro_marco"]), ("atualizacao_id", ObjectId())):
        assert client.get(cenario["url"], query_string={filtro: str(valor)}, headers=headers).status_code == 404
    assert client.get(f"/obras/{cenario['outra']}/feedback-simulado",
                      query_string={"atualizacao_id": cenario["avanco_id"]}, headers=headers).status_code == 404


def test_ct104_e_ct50_engenheiro_e_correcao(client, headers, cenario, database, account):
    url = f"/avancos/{cenario['avanco_id']}"
    anterior = database.tbl_avancos.find_one({"_id": ObjectId(cenario["avanco_id"])})
    resposta = client.patch(url, json={"descricao": "Texto corrigido", "motivo": "Revisão"}, headers=headers)
    assert resposta.status_code == 200, resposta.json
    previa = client.get(f"/obras/{cenario['obra_id']}/previa", headers=headers).json["atualizacoes"][0]
    assert previa["simulado"] is True and previa["origem_simulada"]["ficticio"] is True
    assert previa["autor_original"] == anterior["autor"]
    assert previa["editado_pela_construtora"] is True
    assert previa["ultima_correcao"]["autor"] == str(account["_id"])
    assert previa["ultima_correcao"]["texto_anterior"] == anterior["descricao"]
    versoes = client.get(previa["versoes"], headers=headers).json["versoes"]
    assert len(versoes) == 2 and versoes[0]["conteudo"]["descricao"] == anterior["descricao"]
    assert versoes[1]["conteudo"]["descricao"] == "Texto corrigido"
    cenario["carga"]()
    salvo = database.tbl_avancos.find_one({"_id": anterior["_id"]})
    assert salvo["descricao"] == "Texto corrigido" and len(salvo["correcoes"]) == 1
    assert database.tbl_construtora.count_documents({}) == 1


def test_carga_repetivel_sem_duplicacao_ou_remocao(database, cenario, backend):
    antes = snapshot(database)
    cenario["carga"]()
    depois = snapshot(database)
    # Somente o contador usado para detectar exclusões concorrentes muda.
    for conjunto in (antes, depois):
        for documentos in conjunto.values():
            for documento in documentos:
                documento.pop("_versao_simulados", None)
    assert antes == depois
    assert database.tbl_feedback_simulado.count_documents({}) == 5
    assert backend[1].call_count == 1


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_ct105_sem_escrita_de_comprador(client, headers, database, cenario, metodo):
    antes = snapshot(database)
    assert client.open(cenario["url"], method=metodo, headers=headers,
                       json={"texto": "Mensagem real"}).status_code == 405
    assert snapshot(database) == antes


@pytest.mark.parametrize("alvo,restantes", [("obra", 0), ("marco", 3), ("avanco", 4)])
def test_ct106_exclusao_sem_orfaos(client, headers, database, cenario, alvo, restantes):
    caminho = {"obra": "obras", "marco": "marcos", "avanco": "avancos"}[alvo]
    identificador = cenario[alvo + "_id"]
    resposta = client.delete(f"/{caminho}/{identificador}", json={"confirmar": True}, headers=headers)
    assert resposta.status_code == 204, resposta.get_data(as_text=True)
    assert database.tbl_feedback_simulado.count_documents({}) == restantes
    assert database.tbl_feedback_simulado.count_documents({"alvo.id": ObjectId(identificador)}) == 0
    assert database.tbl_obras.find_one({"_id": cenario["outra"]}) is not None


@pytest.mark.parametrize("filtros,status", [
    ("?marco_id=invalido", 400), ("?atualizacao_id=invalido", 400),
    ("?marco_id=", 400), ("?ignorado=1", 422),
    ("?marco_id=x&marco_id=y", 422), ("?marco_id=x&atualizacao_id=y", 422),
])
def test_filtros_invalidos_nao_gravam(client, headers, database, cenario, filtros, status):
    antes = snapshot(database)
    assert client.get(cenario["url"] + filtros, headers=headers).status_code == status
    assert snapshot(database) == antes


def test_sessao_perfil_e_dono(client, headers, emitir_headers, cenario, database):
    assert client.get(cenario["url"]).status_code == 401
    for perfil in ("comprador", "engenheiro"):
        assert client.get(cenario["url"], headers=emitir_headers(claims={"tipo": perfil})).status_code == 403
    database.tbl_obras.update_one({"_id": ObjectId(cenario["obra_id"])}, {"$set": {"autor": str(ObjectId())}})
    assert client.get(cenario["url"], headers=headers).status_code == 404


def test_falha_de_leitura_neutra(client, headers, cenario, monkeypatch):
    from app.simulados.repository import RepositorioSimulados
    monkeypatch.setattr(RepositorioSimulados, "listar", Mock(side_effect=PyMongoError("detalhe privado")))
    resposta = client.get(cenario["url"], headers=headers)
    assert resposta.status_code == 503 and "detalhe privado" not in resposta.get_data(as_text=True)


def test_carga_feedback_atomica(database, cenario):
    from unittest.mock import patch
    colecao = database.tbl_feedback_simulado
    colecao.delete_many({})
    original = type(colecao).update_one
    chamadas = 0

    def falhar(self, *args, **kwargs):
        nonlocal chamadas
        if self.name == colecao.name:
            chamadas += 1
            if chamadas == 2:
                raise PyMongoError("falha de escrita")
        return original(self, *args, **kwargs)

    with patch.object(type(colecao), "update_one", falhar):
        with pytest.raises(PyMongoError):
            cenario["carga"]()
    assert colecao.count_documents({}) == 0
    cenario["carga"]()
    assert colecao.count_documents({}) == 5
