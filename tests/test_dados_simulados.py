"""UC-21 / CT-102 a CT-106: exemplos simulados de comprador e engenheiro.

A carga usada aqui é a mesma de ``scripts/carregar_dados_demonstracao.py``: os
testes não inventam documentos próprios para o acervo simulado. O provedor de
mídia é simulado e o MongoDB roda em memória por padrão, com rollback local;
estes casos não comprovam isolamento real do Atlas nem remoção no Cloudinary.

CT-50 aparece aqui apenas no recorte de UC-21: corrigir o avanço do engenheiro
simulado preserva origem, autoria original e versões. A escrita da correção é
coberta por ``tests/avancos/test_correcao_publicada.py``.
"""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from bson import ObjectId

from scripts.carregar_dados_demonstracao import (
    AUTOR_ENGENHEIRO,
    COMPRADOR,
    ENGENHEIRO,
    EXEMPLOS,
    ErroCarga,
    carregar,
)
from support import snapshot
from support_avancos import backend, transacao_local  # noqa: F401 - fixtures
from support_midias import arquivo, config, conteudos  # noqa: F401 - fixtures

CAMINHO = "/obras/{}/feedback-simulado"
EXEMPLO = CAMINHO.format("507f1f77bcf86cd799439011")
CLIENTE = "Família Andrade (cliente fictício)"
routes = pytest.mark.routes


def _midia(database, avanco_id, config, conteudos, nome="evidencia.png"):
    from app.avancos.acesso_midias import midia_para_dict
    from app.avancos.midias import validar_arquivo
    from app.integracoes.armazenamento import ArmazenamentoCloudinary

    enviada = ArmazenamentoCloudinary().enviar(
        validar_arquivo(arquivo(conteudos["png"], nome), config))
    registro = dict(enviada, _id=ObjectId(), avanco_id=avanco_id,
                    data_envio=datetime(2030, 1, 1))
    database.tbl_midias.insert_one(registro)
    publica = midia_para_dict(registro)
    publica["conteudo"] = "/midias/" + str(registro["_id"]) + "/conteudo"
    return registro, publica


@pytest.fixture
def cenario(client, database, account, backend, config, conteudos):
    """Obra com dois marcos e a carga de demonstração aplicada uma vez.

    A segunda obra e o avanço autoral da construtora existem para provar que o
    painel não mistura contextos nem transforma registro real em simulado.
    """
    autor = str(account["_id"])
    obra, outra = ObjectId(), ObjectId()
    marco, segundo, marco_outra = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_many([
        {"_id": obra, "nome": "Residencial Aurora", "tipo": "apartamentos",
         "cliente": CLIENTE, "localizacao": "Campinas, SP", "estado": "em andamento",
         "autor": autor, "data_registro": datetime(2030, 1, 1)},
        {"_id": outra, "nome": "Obra sem exemplos", "tipo": "casa",
         "cliente": "Outro cliente fictício", "estado": "planejada",
         "autor": autor, "data_registro": datetime(2030, 1, 1)},
    ])
    database.tbl_marcos.insert_many([
        {"_id": marco, "obra_id": obra, "nome": "Fundação", "estado": "concluído"},
        {"_id": segundo, "obra_id": obra, "nome": "Alvenaria", "estado": "a iniciar"},
        {"_id": marco_outra, "obra_id": outra, "nome": "Marco de outra obra"},
    ])

    # Avanço publicado pela própria construtora: nunca é exemplo simulado.
    autoral = ObjectId()
    _, publica = _midia(database, autoral, config, conteudos, "autoral.png")
    database.tbl_avancos.insert_one(
        {"_id": autoral, "marco_id": marco, "data": "2030-02-01",
         "descricao": "Registro da construtora", "estado": "publicado", "autor": autor,
         "data_registro": datetime(2030, 2, 1), "revisao": 1,
         "publicacao": {"autor": autor, "instante": datetime(2030, 2, 1),
                        "data": "2030-02-01", "descricao": "Registro da construtora",
                        "marco": {"id": marco, "nome": "Fundação"},
                        "midias": [publica]}})

    relatorio = carregar(database, obra_id=str(obra))
    simulado = database.tbl_avancos.find_one({"origem_simulada.exemplo": ENGENHEIRO["exemplo"]})
    return SimpleNamespace(
        autor=autor, obra=obra, outra=outra, marco=marco, segundo=segundo,
        marco_outra=marco_outra, autoral=autoral, relatorio=relatorio,
        simulado=simulado["_id"], avanco_simulado=simulado,
        caminho=CAMINHO.format(obra), caminho_outra=CAMINHO.format(outra),
    )


def _corpo(client, headers, caminho, parametros=None):
    resposta = client.get(caminho, headers=headers, query_string=parametros)
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    return resposta.get_json()


def referencias_restantes(database, identificadores):
    textos = {str(valor) for valor in identificadores}

    def menciona(valor):
        if isinstance(valor, dict):
            return any(menciona(item) for item in valor.values())
        if isinstance(valor, (list, tuple)):
            return any(menciona(item) for item in valor)
        return isinstance(valor, (ObjectId, str)) and str(valor) in textos

    return [(nome, documento["_id"]) for nome in database.list_collection_names()
            for documento in database[nome].find() if menciona(documento)]


# --- CT-102: tipos, cliente fictício de referência e marca simulado --------


@routes(("GET", EXEMPLO))
def test_ct102_tipos_origem_e_marca_simulada_da_obra(client, headers, database, cenario):
    antes = snapshot(database)
    corpo = _corpo(client, headers, cenario.caminho)

    assert corpo["simulado"] is True and corpo["somente_leitura"] is True
    assert "simula" in corpo["aviso"].lower()
    assert corpo["obra"] == {"id": str(cenario.obra), "nome": "Residencial Aurora",
                             "cliente": CLIENTE}
    da_obra = [item for item in corpo["feedbacks"] if item["alvo"]["tipo"] == "obra"]
    assert {item["tipo"] for item in da_obra} == {"avaliacao", "compreensao", "duvida"}
    for item in corpo["feedbacks"]:
        assert item["simulado"] is True and item["interacao_real"] is False
        assert item["somente_leitura"] is True
        origem = item["origem"]
        assert origem["perfil"] == "comprador" and origem["simulado"] is True
        assert origem["identidade"] == "ficticia" and origem["autenticado"] is False
        assert origem["nome"] == COMPRADOR["nome"]
        # O exemplo se apresenta como o cliente de referência da obra, fictício.
        assert origem["cliente_referencia"] == CLIENTE
        assert origem["procedencia"] == "carga_demonstracao"
    avaliacao = next(item for item in da_obra if item["tipo"] == "avaliacao")
    assert avaliacao["conteudo"]["nota"] == 4 and avaliacao["conteudo"]["escala"] == 5
    duvida = next(item for item in da_obra if item["tipo"] == "duvida")
    assert duvida["conteudo"]["respondida"] is False
    assert corpo["totais"] == {"avaliacao": 1, "compreensao": 2, "duvida": 2,
                               "feedbacks": 5, "avancos_simulados": 1}
    assert snapshot(database) == antes


@routes(("GET", EXEMPLO))
def test_ct102_filtra_por_tipo_e_recusa_filtro_invalido(client, headers, cenario):
    corpo = _corpo(client, headers, cenario.caminho, {"tipo": "duvida"})
    assert {item["tipo"] for item in corpo["feedbacks"]} == {"duvida"}
    assert corpo["filtros_aplicados"] == {"tipo": "duvida"}

    for parametros, campo in (({"tipo": "elogio"}, "tipo"), ({"alvo": "contrato"}, "alvo"),
                              ({"comprador": "Helena"}, "comprador")):
        resposta = client.get(cenario.caminho, headers=headers, query_string=parametros)
        assert resposta.status_code == 422, resposta.get_data(as_text=True)
        assert campo in resposta.get_json()["campos"]


# --- CT-103: cada exemplo só no contexto vinculado -------------------------


@routes(("GET", EXEMPLO))
def test_ct103_marco_e_atualizacao_aparecem_apenas_no_proprio_contexto(
    client, headers, cenario
):
    do_marco = _corpo(client, headers, cenario.caminho, {"marco_id": str(cenario.marco)})
    assert [item["exemplo"] for item in do_marco["feedbacks"]] == ["compreensao-marco"]
    alvo = do_marco["feedbacks"][0]["alvo"]
    assert alvo["tipo"] == "marco" and alvo["id"] == str(cenario.marco)
    assert alvo["rotulo"] == "Fundação" and alvo["avanco_id"] is None

    da_atualizacao = _corpo(client, headers, cenario.caminho,
                            {"avanco_id": str(cenario.simulado)})
    assert [item["exemplo"] for item in da_atualizacao["feedbacks"]] == ["duvida-atualizacao"]
    alvo = da_atualizacao["feedbacks"][0]["alvo"]
    assert alvo["tipo"] == "atualizacao" and alvo["id"] == str(cenario.simulado)
    assert alvo["marco_id"] == str(cenario.marco)
    assert str(cenario.avanco_simulado["data"]) in alvo["rotulo"]

    # Nenhum exemplo da obra entra no painel do marco ou da atualização.
    for corpo in (do_marco, da_atualizacao):
        assert all(item["alvo"]["tipo"] != "obra" for item in corpo["feedbacks"])
    da_obra = _corpo(client, headers, cenario.caminho, {"alvo": "obra"})
    assert len(da_obra["feedbacks"]) == 3
    assert all(item["alvo"]["id"] == str(cenario.obra) for item in da_obra["feedbacks"])

    # Marco sem exemplo próprio devolve lista vazia, não o exemplo do vizinho.
    vazio = _corpo(client, headers, cenario.caminho, {"marco_id": str(cenario.segundo)})
    assert vazio["feedbacks"] == [] and vazio["totais"]["feedbacks"] == 0


@routes(("GET", EXEMPLO))
def test_ct103_alvo_de_outra_obra_e_obra_sem_exemplos(client, headers, cenario):
    resposta = client.get(cenario.caminho, headers=headers,
                          query_string={"marco_id": str(cenario.marco_outra)})
    assert resposta.status_code == 404
    corpo = resposta.get_json()
    assert corpo["codigo"] == "ALVO_FORA_DA_OBRA" and corpo["campos"] == ["marco_id"]

    vazio = _corpo(client, headers, cenario.caminho_outra)
    assert vazio["feedbacks"] == [] and vazio["avancos_simulados"] == []
    assert vazio["totais"] == {"avaliacao": 0, "compreensao": 0, "duvida": 0,
                               "feedbacks": 0, "avancos_simulados": 0}

    ausente = client.get(CAMINHO.format(ObjectId()), headers=headers)
    assert ausente.status_code == 404
    assert ausente.get_json()["codigo"] == "OBRA_NAO_ENCONTRADA"
    invalida = client.get(CAMINHO.format("nao-e-id"), headers=headers)
    assert invalida.status_code == 400 and invalida.get_json()["codigo"] == "ID_INVALIDO"


# --- CT-104: avanço do engenheiro simulado, sem sessão desse perfil -------


@routes(("GET", EXEMPLO))
def test_ct104_avanco_do_engenheiro_tem_origem_explicita(client, headers, database, cenario):
    corpo = _corpo(client, headers, cenario.caminho)
    assert len(corpo["avancos_simulados"]) == 1
    avanco = corpo["avancos_simulados"][0]

    assert avanco["id"] == str(cenario.simulado)
    assert avanco["simulado"] is True and avanco["somente_leitura"] is True
    assert avanco["sessao_do_engenheiro"] is False
    origem = avanco["origem_simulada"]
    assert origem["perfil"] == "engenheiro" and origem["simulado"] is True
    assert origem["nome"] == ENGENHEIRO["nome"] and origem["identidade"] == "ficticia"
    assert origem["autenticado"] is False
    assert avanco["autor_original"] == AUTOR_ENGENHEIRO
    # A autoria do exemplo não pode ser confundida com uma identidade de sessão.
    assert not ObjectId.is_valid(avanco["autor_original"])
    assert database.tbl_construtora.count_documents({"nome": ENGENHEIRO["nome"]}) == 0
    assert avanco["estado"] == "publicado" and avanco["versoes"] == 1
    assert avanco["editado_pela_construtora"] is False and "correcao" not in avanco
    assert avanco["marco"] == {"id": str(cenario.marco), "nome": "Fundação"}
    assert len(avanco["midias"]) == 1
    assert avanco["comparacao"] == "/avancos/" + str(cenario.simulado) + "/versoes"
    # O registro autoral da construtora continua fora da lista de exemplos.
    assert all(item["id"] != str(cenario.autoral) for item in corpo["avancos_simulados"])
    # Nenhuma referência do provedor vaza na resposta do painel.
    texto = client.get(cenario.caminho, headers=headers).get_data(as_text=True)
    assert "public_id" not in texto and "referencia_externa" not in texto


@routes(("GET", EXEMPLO))
def test_ct104_previa_e_secoes_usam_a_mesma_origem(client, headers, cenario):
    previa = client.get("/obras/" + str(cenario.obra) + "/previa", headers=headers)
    assert previa.status_code == 200
    publicado = next(item for item in previa.get_json()["atualizacoes"]
                     if item["id"] == str(cenario.simulado))
    assert publicado["origem_simulada"]["perfil"] == "engenheiro"

    engenheiro = _corpo(client, headers, cenario.caminho, {"secao": "engenheiro"})
    assert engenheiro["feedbacks"] == [] and len(engenheiro["avancos_simulados"]) == 1
    comprador = _corpo(client, headers, cenario.caminho, {"secao": "comprador"})
    assert comprador["avancos_simulados"] == [] and len(comprador["feedbacks"]) == 5


@routes(("GET", EXEMPLO))
def test_ct104_exemplo_sem_publicacao_mostra_estado_e_evidencias(
    client, headers, database, cenario, config, conteudos
):
    """Exemplo de engenheiro ainda em rascunho: estado real e mídias do acervo."""
    rascunho = ObjectId()
    _midia(database, rascunho, config, conteudos, "rascunho.png")
    database.tbl_avancos.insert_one(
        {"_id": rascunho, "marco_id": cenario.segundo, "data": "2030-04-01",
         "descricao": "Rascunho do engenheiro", "estado": "rascunho",
         "autor": AUTOR_ENGENHEIRO, "revisao": 0,
         "data_registro": datetime(2030, 4, 1),
         "origem_simulada": dict(ENGENHEIRO, exemplo="avanco-engenheiro-rascunho")})

    corpo = _corpo(client, headers, cenario.caminho, {"marco_id": str(cenario.segundo)})
    avanco = corpo["avancos_simulados"][0]
    assert avanco["id"] == str(rascunho) and avanco["estado"] == "rascunho"
    assert avanco["simulado"] is True and avanco["versoes"] == 1
    assert avanco["marco"] == {"id": str(cenario.segundo), "nome": "Alvenaria"}
    assert len(avanco["midias"]) == 1 and avanco["midias"][0]["tipo"] == "foto"
    assert client.get(avanco["midias"][0]["conteudo"], headers=headers).status_code == 200
    assert "public_id" not in str(avanco)


# --- CT-105: não há interação real de comprador ou engenheiro -------------


def test_ct105_nao_existe_envio_de_feedback_pela_api(client, headers, database, cenario):
    antes = snapshot(database)
    for metodo in ("post", "put", "patch", "delete"):
        resposta = getattr(client, metodo)(
            cenario.caminho, headers=headers,
            json={"tipo": "avaliacao", "comentario": "mensagem real"})
        assert resposta.status_code == 405, (metodo, resposta.get_data(as_text=True))
        corpo = resposta.get_json()
        assert corpo["codigo"] == "INTERACAO_NAO_DISPONIVEL"
        assert "GET" in resposta.headers["Allow"]
    assert snapshot(database) == antes


def test_ct105_nenhuma_rota_escreve_exemplos_ou_autentica_comprador(client, cenario):
    escrita = {"POST", "PUT", "PATCH", "DELETE"}
    for regra in client.application.url_map.iter_rules():
        if "feedback-simulado" in regra.rule:
            # As escritas existem apenas para recusar; a leitura é o contrato.
            assert regra.endpoint in {"simulados.feedback_simulado",
                                      "simulados.recusar_interacao"}
        else:
            assert "comprador" not in regra.rule and "engenheiro" not in regra.rule
    cadastros = [regra.rule for regra in client.application.url_map.iter_rules()
                 if regra.methods & escrita and
                 any(termo in regra.rule for termo in ("comprador", "engenheiro",
                                                       "avaliacao", "duvida"))]
    assert cadastros == []


def test_ct105_leitura_exige_sessao_da_construtora(client, cenario, emitir_headers):
    assert client.get(cenario.caminho).status_code == 401
    for metodo in ("post", "patch"):
        assert getattr(client, metodo)(cenario.caminho).status_code == 401
    perfil = emitir_headers(claims={"tipo": "comprador"})
    assert client.get(cenario.caminho, headers=perfil).status_code == 403


# --- CT-106: excluir o alvo não deixa exemplo órfão -----------------------


@routes(("DELETE", "/obras/507f1f77bcf86cd799439011"))
def test_ct106_exclusao_da_obra_leva_os_exemplos(
    client, headers, database, cenario, transacao_local
):
    aviso = client.delete("/obras/" + str(cenario.obra), headers=headers)
    assert aviso.status_code == 422
    perda = aviso.get_json()["perda"]
    assert perda["feedbacks_simulados"] == 5 and perda["exemplos_simulados"] == 1

    exemplos = [documento["_id"] for documento in database.tbl_feedback_simulado.find()]
    assert len(exemplos) == 5
    resposta = client.delete("/obras/" + str(cenario.obra), headers=headers,
                             json={"confirmar": True})
    assert resposta.status_code == 204, resposta.get_data(as_text=True)
    assert database.tbl_feedback_simulado.count_documents({}) == 0
    assert referencias_restantes(
        database, [cenario.obra, cenario.marco, cenario.simulado, *exemplos]) == []
    assert client.get(cenario.caminho, headers=headers).status_code == 404
    # A obra alheia ao cenário permanece consultável e sem exemplos.
    intacta = _corpo(client, headers, cenario.caminho_outra)
    assert intacta["feedbacks"] == []


@routes(("DELETE", "/marcos/507f1f77bcf86cd799439011"))
def test_ct106_exclusao_do_marco_preserva_os_exemplos_da_obra(
    client, headers, database, cenario, transacao_local
):
    aviso = client.delete("/marcos/" + str(cenario.marco), headers=headers)
    assert aviso.status_code == 422
    assert aviso.get_json()["perda"]["feedbacks_simulados"] == 2

    resposta = client.delete("/marcos/" + str(cenario.marco), headers=headers,
                             json={"confirmar": True})
    assert resposta.status_code == 204, resposta.get_data(as_text=True)
    restantes = list(database.tbl_feedback_simulado.find())
    assert {documento["exemplo"] for documento in restantes} == {
        "avaliacao-obra", "compreensao-obra", "duvida-obra"}
    assert referencias_restantes(database, [cenario.marco, cenario.simulado]) == []
    corpo = _corpo(client, headers, cenario.caminho)
    assert len(corpo["feedbacks"]) == 3 and corpo["avancos_simulados"] == []
    assert "exemplos_inconsistentes" not in corpo


def test_ct106_exclusao_do_rascunho_leva_o_exemplo_vinculado(
    client, headers, database, cenario, backend, transacao_local
):
    """UC-18: exemplo ligado a um rascunho sai com ele, sem referência órfã."""
    rascunho = ObjectId()
    database.tbl_avancos.insert_one(
        {"_id": rascunho, "marco_id": cenario.segundo, "data": "2030-03-01",
         "descricao": "Rascunho", "estado": "rascunho", "autor": cenario.autor,
         "data_registro": datetime(2030, 3, 1), "revisao": 0})
    database.tbl_feedback_simulado.insert_one(
        {"_id": ObjectId(), "simulado": True, "exemplo": "duvida-rascunho",
         "tipo": "duvida", "origem": dict(COMPRADOR), "obra_id": cenario.obra,
         "marco_id": cenario.segundo, "avanco_id": rascunho,
         "alvo": {"tipo": "atualizacao", "id": rascunho},
         "conteudo": {"pergunta": "Esta etapa já começou?", "respondida": False},
         "registrado_em": datetime(2030, 3, 2)})

    resposta = client.delete("/avancos/" + str(rascunho), headers=headers)
    assert resposta.status_code == 204, resposta.get_data(as_text=True)
    assert database.tbl_feedback_simulado.count_documents({"avanco_id": rascunho}) == 0
    assert referencias_restantes(database, [rascunho]) == []
    corpo = _corpo(client, headers, cenario.caminho)
    assert all(item["exemplo"] != "duvida-rascunho" for item in corpo["feedbacks"])


@routes(("GET", EXEMPLO))
def test_exemplo_de_alvo_inexistente_nao_e_apresentado(client, headers, database, cenario):
    """Vínculo quebrado não aparece no painel nem contamina outro contexto."""
    database.tbl_feedback_simulado.insert_one(
        {"_id": ObjectId(), "simulado": True, "exemplo": "duvida-perdida",
         "tipo": "duvida", "origem": dict(COMPRADOR), "obra_id": cenario.obra,
         "marco_id": ObjectId(), "avanco_id": None,
         "alvo": {"tipo": "marco", "id": ObjectId()},
         "conteudo": {"pergunta": "Pergunta sem alvo", "respondida": False},
         "registrado_em": datetime(2030, 3, 2)})
    corpo = _corpo(client, headers, cenario.caminho)
    assert corpo["exemplos_inconsistentes"] == 1
    assert all(item["exemplo"] != "duvida-perdida" for item in corpo["feedbacks"])
    assert corpo["totais"]["feedbacks"] == 5


# --- Carga repetível ------------------------------------------------------


def test_carga_repetida_nao_duplica_nem_remove_dados_alheios(
    client, headers, database, cenario
):
    antes = snapshot(database)
    relatorio = carregar(database, obra_id=str(cenario.obra))

    assert {item["situacao"] for item in relatorio["feedbacks"]} == {"mantido"}
    assert relatorio["avanco_simulado"]["situacao"] == "mantido"
    assert database.tbl_feedback_simulado.count_documents({}) == len(EXEMPLOS)
    assert database.tbl_avancos.count_documents(
        {"origem_simulada.exemplo": ENGENHEIRO["exemplo"]}) == 1
    # Nada muda no banco: nem outro exemplo, nem outro upload, nem dado alheio.
    assert snapshot(database) == antes
    corpo = _corpo(client, headers, cenario.caminho)
    assert corpo["totais"] == {"avaliacao": 1, "compreensao": 2, "duvida": 2,
                               "feedbacks": 5, "avancos_simulados": 1}


def test_carga_exige_obra_do_cenario(database, app, backend, config):
    with pytest.raises(ErroCarga, match="Nenhuma obra"):
        carregar(database)
    obra = database.tbl_obras.insert_one({"nome": "Única", "cliente": "Cliente"}).inserted_id
    database.tbl_obras.insert_one({"nome": "Segunda", "cliente": "Outro"})
    with pytest.raises(ErroCarga, match="--obra"):
        carregar(database)
    with pytest.raises(ErroCarga, match="Obra não encontrada"):
        carregar(database, obra_id=str(ObjectId()))
    with pytest.raises(ErroCarga, match="Identificador inválido"):
        carregar(database, obra_id="nao-e-id")
    # Sem marco não há como vincular marco e atualização; a obra ainda recebe
    # os exemplos próprios e o relatório diz o que ficou de fora.
    relatorio = carregar(database, obra_id=str(obra))
    situacoes = {item["exemplo"]: item["situacao"] for item in relatorio["feedbacks"]}
    assert situacoes["compreensao-obra"] == "criado"
    assert situacoes["compreensao-marco"] == "ignorado"
    assert situacoes["duvida-atualizacao"] == "ignorado"
    assert relatorio["avanco_simulado"]["situacao"] == "ignorado"
    assert "marco" in relatorio["avanco_simulado"]["motivo"]


def test_carga_sem_provedor_configurado_ignora_o_avanco(database, app, monkeypatch):
    obra = database.tbl_obras.insert_one({"nome": "Obra", "cliente": "Cliente"}).inserted_id
    database.tbl_marcos.insert_one({"obra_id": obra, "nome": "Marco"})
    for variavel in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.delenv(variavel, raising=False)
    relatorio = carregar(database, obra_id=str(obra))
    assert relatorio["avanco_simulado"]["situacao"] == "ignorado"
    assert "provedor" in relatorio["avanco_simulado"]["motivo"]
    assert database.tbl_avancos.count_documents({}) == 0
    # Com --sem-midia o exemplo é criado, mas sem evidência para corrigir.
    relatorio = carregar(database, obra_id=str(obra), sem_midia=True)
    assert relatorio["avanco_simulado"]["situacao"] == "criado"
    assert relatorio["avanco_simulado"]["midias"] == 0


def test_carga_adota_avanco_publicado_preservando_autoria_anterior(
    database, app, account, backend, config, conteudos
):
    autor = str(account["_id"])
    obra = database.tbl_obras.insert_one(
        {"nome": "Obra", "cliente": "Cliente", "autor": autor}).inserted_id
    marco = database.tbl_marcos.insert_one({"obra_id": obra, "nome": "Marco"}).inserted_id
    avanco = ObjectId()
    _, publica = _midia(database, avanco, config, conteudos)
    database.tbl_avancos.insert_one(
        {"_id": avanco, "marco_id": marco, "data": "2030-02-01", "descricao": "Texto",
         "estado": "publicado", "autor": autor, "revisao": 1,
         "publicacao": {"autor": autor, "instante": datetime(2030, 2, 1),
                        "data": "2030-02-01", "descricao": "Texto",
                        "marco": {"id": marco, "nome": "Marco"}, "midias": [publica]}})

    relatorio = carregar(database, obra_id=str(obra), avanco_id=str(avanco))
    assert relatorio["avanco_simulado"]["situacao"] == "adotado"
    salvo = database.tbl_avancos.find_one({"_id": avanco})
    assert salvo["origem_simulada"]["perfil"] == "engenheiro"
    assert salvo["origem_simulada"]["autor_anterior"] == autor
    assert salvo["autor"] == salvo["publicacao"]["autor"] == AUTOR_ENGENHEIRO
    assert salvo["publicacao"]["midias"] == [publica]
    # Repetir mantém a adoção e não cria um segundo exemplo de engenheiro.
    assert carregar(database, obra_id=str(obra))["avanco_simulado"]["situacao"] == "mantido"
    assert database.tbl_avancos.count_documents({}) == 1


# --- CT-50 no recorte de UC-21: correção preserva a origem simulada -------


@routes(("GET", EXEMPLO))
def test_ct50_correcao_da_construtora_preserva_origem_e_versoes(
    client, headers, account, database, cenario, transacao_local
):
    original = deepcopy(cenario.avanco_simulado)
    resposta = client.patch("/avancos/" + str(cenario.simulado), headers=headers,
                            json={"motivo": "Ajuste do texto informado",
                                  "descricao": "Concretagem concluída e cura acompanhada."})
    assert resposta.status_code == 200, resposta.get_data(as_text=True)

    corpo = _corpo(client, headers, cenario.caminho)
    avanco = corpo["avancos_simulados"][0]
    assert avanco["origem_simulada"] == original["origem_simulada"]
    assert avanco["autor_original"] == AUTOR_ENGENHEIRO
    assert avanco["editado"] is True and avanco["editado_pela_construtora"] is True
    assert avanco["versoes"] == 2
    correcao = avanco["correcao"]
    # A construtora assina a correção; o engenheiro segue como autor original.
    assert correcao["autor"] == str(account["_id"])
    assert correcao["motivo"] == "Ajuste do texto informado"
    assert correcao["campos"] == ["descricao"]
    assert correcao["antes"]["descricao"] == original["descricao"]
    assert correcao["depois"]["descricao"] == avanco["descricao"]

    versoes = client.get(avanco["comparacao"], headers=headers).get_json()["versoes"]
    assert [item["autor_original"] for item in versoes] == [AUTOR_ENGENHEIRO] * 2
    assert all(item["origem_simulada"] == original["origem_simulada"] for item in versoes)
    assert versoes[0]["conteudo"]["descricao"] == original["descricao"]

    # Reexecutar a carga não desfaz a correção nem recria o exemplo.
    relatorio = carregar(database, obra_id=str(cenario.obra))
    assert relatorio["avanco_simulado"]["situacao"] == "mantido"
    assert relatorio["avanco_simulado"]["corrigido_pela_construtora"] is True
    salvo = database.tbl_avancos.find_one({"_id": cenario.simulado})
    assert len(salvo["correcoes"]) == 1 and salvo["autor"] == AUTOR_ENGENHEIRO
