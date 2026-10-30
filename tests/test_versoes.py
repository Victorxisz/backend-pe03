"""UC-11: consulta e comparação das versões de um avanço publicado.

A publicação é gravada como o UC-10 a persiste e cada correção é gravada como o
`PATCH /avancos/{id}` deve gravá-la — conteúdo anterior completo em `correcoes`
e conteúdo corrigido em `publicacao`. Somente a rede do provedor de mídia é
simulada; o restante usa o MongoDB da execução.
"""

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from bson import ObjectId
from cloudinary.exceptions import NotFound
from flask_jwt_extended import decode_token
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot


VERSOES = "/avancos/{}/versoes"
PUBLICADO_EM = datetime(2030, 10, 20, 12, 0, tzinfo=timezone.utc)
CORRIGIDO_EM = (datetime(2030, 10, 21, 9, 30, tzinfo=timezone.utc),
                datetime(2030, 10, 22, 16, 45, tzinfo=timezone.utc))
CONTEUDO = ("data", "descricao", "marco", "midias")


def reconstruir(trechos, lado):
    """Texto anterior ou posterior refeito a partir dos trechos destacáveis."""
    operacoes = {"anterior": ("igual", "removido"), "posterior": ("igual", "inserido")}[lado]
    return "".join(trecho["texto"] for trecho in trechos if trecho["operacao"] in operacoes)


@pytest.fixture
def cenario(app, database, account, monkeypatch):
    from app.avancos.acesso_midias import midia_para_dict

    for chave, valor in {"CLOUDINARY_CLOUD_NAME": "nuvem-ficticia",
                         "CLOUDINARY_API_KEY": "chave-ficticia",
                         "CLOUDINARY_API_SECRET": "segredo-ficticio",
                         "CLOUDINARY_FOLDER": "pe03/evidencias"}.items():
        monkeypatch.setenv(chave, valor)
    arquivos = {}
    obra, marco, avanco = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_one({"_id": obra, "nome": "Casa teste"})
    database.tbl_marcos.insert_one({"_id": marco, "obra_id": obra, "nome": "Fundação"})

    def enviar_midia(nome, conteudo):
        """Persiste a mídia como o envio do UC-08 a deixa no acervo."""
        referencia = {"provedor": "cloudinary", "public_id": "pe03/evidencias/" + uuid4().hex,
                      "resource_type": "image", "delivery_type": "authenticated", "formato": "png"}
        documento = {"_id": ObjectId(), "avanco_id": avanco, "tipo": "foto", "nome": nome,
                     "mime": "image/png", "tamanho": len(conteudo), "data_envio": PUBLICADO_EM,
                     "referencia_externa": referencia}
        database.tbl_midias.insert_one(documento)
        arquivos[referencia["public_id"]] = conteudo
        return documento

    def representar(documento):
        midia = midia_para_dict(documento)
        midia["conteudo"] = f"/midias/{midia['id']}/conteudo"
        return midia

    def publicar(descricao="Fundação concretada", data="2030-10-19", midias=None, **extra):
        midias = [enviar_midia("fundacao.png", b"foto-original")] if midias is None else midias
        publicacao = {"autor": str(account["_id"]), "instante": PUBLICADO_EM, "data": data,
                      "descricao": descricao, "marco": {"id": marco, "nome": "Fundação"},
                      "midias": [representar(documento) for documento in midias]}
        database.tbl_avancos.insert_one({"_id": avanco, "marco_id": marco, "data": data,
                                         "descricao": descricao, "estado": "publicado",
                                         "revisao": 1, "publicacao": publicacao, **extra})
        return publicacao

    def corrigir(motivo, instante, autor=None, midias=None, **campos):
        """Correção do UC-11: a versão anterior é preservada, não substituída."""
        publicacao = database.tbl_avancos.find_one({"_id": avanco})["publicacao"]
        corrigida = {**publicacao, **campos}
        if midias is not None:
            corrigida["midias"] = [representar(documento) for documento in midias]
        correcao = {"autor": str(account["_id"]) if autor is None else autor,
                    "instante": instante, "motivo": motivo,
                    "anterior": {campo: publicacao[campo] for campo in CONTEUDO}}
        database.tbl_avancos.update_one(
            {"_id": avanco},
            {"$set": {"publicacao": corrigida, "data": corrigida["data"],
                      "descricao": corrigida["descricao"]},
             "$push": {"correcoes": correcao}, "$inc": {"revisao": 1}},
        )
        return correcao

    def baixar(url, timeout):
        return BytesIO(arquivos[parse_qs(urlparse(url).query)["public_id"][0]])

    def consultar(**opcoes):
        if opcoes["public_id"] not in arquivos:
            raise NotFound("objeto ausente")
        return {"public_id": opcoes["public_id"]}

    resource, download = Mock(side_effect=consultar), Mock(side_effect=baixar)
    monkeypatch.setattr("cloudinary.api.resource", resource)
    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", download)
    monkeypatch.setattr("urllib.request.urlopen", download)
    return SimpleNamespace(obra=obra, marco=marco, avanco=avanco, rota=VERSOES.format(avanco),
                           enviar_midia=enviar_midia, publicar=publicar, corrigir=corrigir,
                           arquivos=arquivos, resource=resource, download=download)


def test_ct46_correcao_de_texto_expoe_anterior_campos_motivo_e_autoria(
    client, headers, account, cenario
):
    cenario.publicar(descricao="Fundação concretada no bloco A")
    cenario.corrigir("Bloco informado estava errado", CORRIGIDO_EM[0],
                     descricao="Fundação concretada no bloco B")

    resposta = client.get(cenario.rota, headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["avanco_id"] == str(cenario.avanco)
    assert (corpo["versao_atual"], corpo["total_versoes"]) == (2, 2)
    assert [versao["versao"] for versao in corpo["versoes"]] == [1, 2]
    assert [versao["atual"] for versao in corpo["versoes"]] == [False, True]
    anterior, atual = corpo["versoes"]
    assert anterior["conteudo"]["descricao"] == "Fundação concretada no bloco A"
    assert atual["conteudo"]["descricao"] == "Fundação concretada no bloco B"
    assert anterior["correcao"] is None
    correcao = atual["correcao"]
    assert correcao["campos"] == ["descricao"]
    assert correcao["motivo"] == "Bloco informado estava errado"
    assert correcao["autor"] == str(account["_id"])
    assert datetime.fromisoformat(correcao["instante"]) == CORRIGIDO_EM[0]
    assert correcao["anterior"] == anterior["conteudo"]
    assert correcao["posterior"] == atual["conteudo"]
    assert resposta.headers["Cache-Control"] == "private, no-store"
    corpo_texto = resposta.get_data(as_text=True)
    assert "referencia_externa" not in corpo_texto and "public_id" not in corpo_texto


def test_ct46_diferencas_permitem_destacar_o_trecho_alterado(client, headers, cenario):
    cenario.publicar(descricao="Fundação concretada no bloco A", data="2030-10-19")
    cenario.corrigir("Data e bloco corrigidos", CORRIGIDO_EM[0],
                     descricao="Fundação concretada no bloco B", data="2030-10-18")

    corpo = client.get(cenario.rota, headers=headers).get_json()

    correcao = corpo["versoes"][1]["correcao"]
    assert correcao["campos"] == ["data", "descricao"]
    for campo, antes, depois in (("data", "2030-10-19", "2030-10-18"),
                                 ("descricao", "Fundação concretada no bloco A",
                                  "Fundação concretada no bloco B")):
        diferenca = correcao["diferencas"][campo]
        assert diferenca["tipo"] == "texto"
        assert (diferenca["anterior"], diferenca["posterior"]) == (antes, depois)
        # A interface destaca os trechos sem recalcular o texto completo.
        assert reconstruir(diferenca["trechos"], "anterior") == antes
        assert reconstruir(diferenca["trechos"], "posterior") == depois
    trechos = correcao["diferencas"]["descricao"]["trechos"]
    assert [trecho["operacao"] for trecho in trechos] == ["igual", "removido", "inserido"]
    assert trechos[0]["texto"] == "Fundação concretada no bloco "
    assert (trechos[1]["texto"], trechos[2]["texto"]) == ("A", "B")
    assert "midias" not in correcao["diferencas"]


def test_ct47_correcao_de_midia_mantem_a_anterior_rastreavel(client, headers, cenario):
    original = cenario.enviar_midia("fundacao.png", b"foto-original")
    cenario.publicar(midias=[original])
    substituta = cenario.enviar_midia("fundacao-corrigida.png", b"foto-corrigida")
    cenario.corrigir("Foto mostrava outro trecho", CORRIGIDO_EM[0], midias=[substituta])

    corpo = client.get(cenario.rota, headers=headers).get_json()

    anterior, atual = (versao["conteudo"]["midias"][0] for versao in corpo["versoes"])
    assert (anterior["id"], atual["id"]) == (str(original["_id"]), str(substituta["_id"]))
    assert (anterior["nome"], atual["nome"]) == ("fundacao.png", "fundacao-corrigida.png")
    # Política de retenção: as duas referências seguem recuperáveis no acervo.
    assert anterior["disponivel"] is True and atual["disponivel"] is True
    for midia, conteudo in ((atual, b"foto-corrigida"), (anterior, b"foto-original")):
        assert midia["conteudo"] == f"/midias/{midia['id']}/conteudo"
        arquivo = client.get(midia["conteudo"], headers=headers)
        assert arquivo.status_code == 200 and arquivo.data == conteudo
    correcao = corpo["versoes"][1]["correcao"]
    assert correcao["campos"] == ["midias"]
    diferenca = correcao["diferencas"]["midias"]
    assert diferenca["tipo"] == "midias"
    assert [midia["id"] for midia in diferenca["removidas"]] == [str(original["_id"])]
    assert [midia["id"] for midia in diferenca["adicionadas"]] == [str(substituta["_id"])]
    assert diferenca["mantidas"] == []


def test_ct47_midia_fora_do_acervo_mantem_metadados_sem_conteudo(client, headers, database, cenario):
    original = cenario.enviar_midia("fundacao.png", b"foto-original")
    cenario.publicar(midias=[original])
    substituta = cenario.enviar_midia("fundacao-corrigida.png", b"foto-corrigida")
    cenario.corrigir("Foto ilegível", CORRIGIDO_EM[0], midias=[substituta])
    # A retenção pode encerrar: a referência histórica não deve desaparecer com o arquivo.
    database.tbl_midias.delete_one({"_id": original["_id"]})

    corpo = client.get(cenario.rota, headers=headers).get_json()

    historica = corpo["versoes"][0]["conteudo"]["midias"][0]
    assert historica["disponivel"] is False and historica["conteudo"] is None
    assert historica["id"] == str(original["_id"])
    assert (historica["nome"], historica["tipo"]) == ("fundacao.png", "foto")
    assert historica["tamanho"] == len(b"foto-original")
    assert corpo["versoes"][1]["conteudo"]["midias"][0]["disponivel"] is True


def test_ct50_origem_simulada_e_autoria_das_correcoes_sao_separadas(
    client, headers, account, cenario
):
    cenario.publicar(descricao="Laje do segundo pavimento concluída",
                     origem={"simulado": True, "perfil": "engenheiro", "nome": "Eng. Marta Dias"})
    cenario.corrigir("Pavimento informado estava errado", CORRIGIDO_EM[0],
                     descricao="Laje do terceiro pavimento concluída")

    corpo = client.get(cenario.rota, headers=headers).get_json()

    autoria = corpo["autoria"]
    assert autoria["origem_simulada"] == {"simulado": True, "perfil": "engenheiro",
                                          "nome": "Eng. Marta Dias"}
    assert autoria["original"]["simulado"] is True
    assert autoria["original"]["perfil"] == "engenheiro"
    assert datetime.fromisoformat(autoria["original"]["instante"]) == PUBLICADO_EM
    # A correção é da construtora autenticada; o engenheiro simulado não vira usuário.
    assert autoria["editado_pela_construtora"] is True
    assert autoria["correcoes"] == [{
        "versao": 2, "autor": str(account["_id"]), "perfil": "construtora",
        "instante": autoria["correcoes"][0]["instante"],
        "motivo": "Pavimento informado estava errado",
    }]
    assert datetime.fromisoformat(autoria["correcoes"][0]["instante"]) == CORRIGIDO_EM[0]
    assert "autor" not in autoria["origem_simulada"]
    anterior = corpo["versoes"][0]["conteudo"]["descricao"]
    assert anterior == "Laje do segundo pavimento concluída"
    trechos = corpo["versoes"][1]["correcao"]["diferencas"]["descricao"]["trechos"]
    assert reconstruir(trechos, "anterior") == anterior
    assert {"operacao": "removido", "texto": "segundo"} in trechos
    assert {"operacao": "inserido", "texto": "terceiro"} in trechos


def test_publicacao_propria_da_construtora_nao_e_simulada(client, headers, account, cenario):
    cenario.publicar()

    corpo = client.get(cenario.rota, headers=headers).get_json()

    assert corpo["autoria"]["origem_simulada"] is None
    assert corpo["autoria"]["original"] == {"autor": str(account["_id"]), "perfil": "construtora",
                                            "instante": PUBLICADO_EM.isoformat(), "simulado": False}
    assert corpo["autoria"]["editado_pela_construtora"] is False
    assert corpo["autoria"]["correcoes"] == []


def test_ct51_duas_correcoes_preservam_a_cadeia_ordenada(client, headers, cenario):
    textos = ["Alvenaria iniciada", "Alvenaria do bloco A iniciada",
              "Alvenaria do bloco A concluída"]
    datas = ["2030-10-19", "2030-10-18", "2030-10-18"]
    motivos = ["Bloco faltava na descrição", "Etapa já havia terminado"]
    cenario.publicar(descricao=textos[0], data=datas[0])
    for indice, motivo in enumerate(motivos):
        cenario.corrigir(motivo, CORRIGIDO_EM[indice],
                         descricao=textos[indice + 1], data=datas[indice + 1])

    corpo = client.get(cenario.rota, headers=headers).get_json()

    assert (corpo["versao_atual"], corpo["total_versoes"]) == (3, 3)
    assert [versao["versao"] for versao in corpo["versoes"]] == [1, 2, 3]
    assert [versao["atual"] for versao in corpo["versoes"]] == [False, False, True]
    # A sequência do conteúdo é reconstruída inteira, não apenas a última versão.
    assert [versao["conteudo"]["descricao"] for versao in corpo["versoes"]] == textos
    assert [versao["conteudo"]["data"] for versao in corpo["versoes"]] == datas
    assert [correcao["motivo"] for correcao in corpo["autoria"]["correcoes"]] == motivos
    assert [correcao["versao"] for correcao in corpo["autoria"]["correcoes"]] == [2, 3]
    instantes = [datetime.fromisoformat(correcao["instante"])
                 for correcao in corpo["autoria"]["correcoes"]]
    assert instantes == list(CORRIGIDO_EM)
    for indice in (1, 2):
        correcao = corpo["versoes"][indice]["correcao"]
        assert correcao["anterior"] == corpo["versoes"][indice - 1]["conteudo"]
        assert correcao["posterior"] == corpo["versoes"][indice]["conteudo"]
    assert corpo["versoes"][2]["correcao"]["campos"] == ["descricao"]
    assert corpo["versoes"][1]["correcao"]["campos"] == ["data", "descricao"]


def test_ct51_versoes_persistem_em_nova_instancia(client, headers, database, cenario):
    cenario.publicar(descricao="Cobertura iniciada")
    cenario.corrigir("Texto incompleto", CORRIGIDO_EM[0], descricao="Cobertura metálica iniciada")
    esperado = client.get(cenario.rota, headers=headers).get_json()

    with isolated_app(database) as nova_app:
        resposta = nova_app.test_client().get(cenario.rota, headers=headers)

    assert resposta.status_code == 200 and resposta.get_json() == esperado


def test_publicacao_sem_correcoes_difere_de_avanco_inexistente(client, headers, cenario):
    cenario.publicar(descricao="Fundação concretada")

    publicado = client.get(cenario.rota, headers=headers)
    inexistente = client.get(VERSOES.format(ObjectId()), headers=headers)

    assert publicado.status_code == 200
    corpo = publicado.get_json()
    assert (corpo["versao_atual"], corpo["total_versoes"]) == (1, 1)
    assert corpo["versoes"][0] == {"versao": 1, "atual": True, "correcao": None,
                                   "conteudo": corpo["versoes"][0]["conteudo"]}
    assert corpo["versoes"][0]["conteudo"]["descricao"] == "Fundação concretada"
    assert inexistente.status_code == 404
    assert inexistente.get_json() == {"codigo": "AVANCO_NAO_ENCONTRADO",
                                      "mensagem": "Avanço não encontrado",
                                      "campos": ["avanco_id"]}


def test_rascunho_nao_tem_versao_publicada(client, headers, database, cenario):
    rascunho = database.tbl_avancos.insert_one(
        {"marco_id": cenario.marco, "data": "2030-10-19", "descricao": "Em revisão",
         "estado": "rascunho"}
    ).inserted_id

    resposta = client.get(VERSOES.format(rascunho), headers=headers)

    assert resposta.status_code == 200
    assert resposta.get_json() == {"avanco_id": str(rascunho), "estado": "rascunho",
                                   "versao_atual": None, "total_versoes": 0,
                                   "autoria": None, "versoes": []}


@pytest.mark.parametrize("avanco_id", [" ", "abc", "507f1f77bcf86cd79943901",
                                       "507f1f77bcf86cd799439011x"])
def test_identificador_invalido_nao_consulta_o_banco(
    client, headers, cenario, monkeypatch, avanco_id
):
    consulta = Mock()
    monkeypatch.setattr("app.avancos.repository.buscar_avanco", consulta)

    resposta = client.get(VERSOES.format(avanco_id), headers=headers)

    assert resposta.status_code == 400
    assert resposta.get_json() == {"codigo": "ID_INVALIDO", "mensagem": "ID inválido",
                                   "campos": ["avanco_id"]}
    consulta.assert_not_called()


@pytest.mark.parametrize("correcoes", [
    "duas", {"motivo": "x"}, [None], [{"motivo": "sem conteúdo anterior"}],
    [{"anterior": "texto", "motivo": "x"}],
])
def test_cadeia_corrompida_nao_inventa_historico(client, headers, database, cenario, correcoes):
    cenario.publicar()
    database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$set": {"correcoes": correcoes}})

    resposta = client.get(cenario.rota, headers=headers)

    assert resposta.status_code == 500
    assert resposta.get_json()["codigo"] == "VERSOES_INCONSISTENTES"
    assert "versoes" not in resposta.get_json()


def test_consulta_nao_altera_o_banco(client, headers, database, cenario):
    cenario.publicar()
    cenario.corrigir("Descrição imprecisa", CORRIGIDO_EM[0], descricao="Fundação concretada ontem")
    antes = snapshot(database)

    assert client.get(cenario.rota, headers=headers).status_code == 200

    assert snapshot(database) == antes


def test_falha_no_banco_nao_expoe_detalhe_interno(client, headers, cenario, monkeypatch):
    cenario.publicar()

    def falhar(*args, **kwargs):
        raise PyMongoError("coleção tests_segredo indisponível")

    monkeypatch.setattr("app.avancos.repository.buscar_avanco", falhar)

    resposta = client.get(cenario.rota, headers=headers)

    assert resposta.status_code == 503
    assert resposta.get_json()["codigo"] == "FALHA_NO_BANCO"
    assert "tests_segredo" not in resposta.get_data(as_text=True)


@pytest.mark.parametrize("sessao", ["ausente", "expirada", "revogada", "inativa"])
def test_consulta_exige_sessao_da_construtora(
    app, client, headers, emitir_headers, account, database, cenario, sessao
):
    cenario.publicar()
    cenario.corrigir("Descrição imprecisa", CORRIGIDO_EM[0], descricao="Outra descrição")
    autenticacao = headers
    if sessao == "ausente":
        autenticacao = {}
    elif sessao == "expirada":
        autenticacao = emitir_headers(expirado=True)
    elif sessao == "inativa":
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    else:
        with app.app_context():
            claims = decode_token(headers["Authorization"].split()[1])
        database.tbl_sessoes_revogadas.insert_one({"_id": claims["sessao_id"]})

    resposta = client.get(cenario.rota, headers=autenticacao)

    assert resposta.status_code == 401
    assert "Fundação" not in resposta.get_data(as_text=True)


@pytest.mark.parametrize("anterior,posterior,esperado", [
    ("Laje concluída", "Laje concluída", [("igual", "Laje concluída")]),
    ("Laje", "Laje concluída", [("igual", "Laje"), ("inserido", " concluída")]),
    ("Laje concluída", "Laje", [("igual", "Laje"), ("removido", " concluída")]),
    ("", "Primeira descrição", [("inserido", "Primeira descrição")]),
    ("Texto removido", "", [("removido", "Texto removido")]),
    ("bloco A", "bloco B", [("igual", "bloco "), ("removido", "A"), ("inserido", "B")]),
    (None, "Descrição nova", [("inserido", "Descrição nova")]),
])
def test_diferenca_texto_marca_trechos_e_permite_reconstruir(app, anterior, posterior, esperado):
    from app.avancos.versoes import diferenca_texto

    trechos = diferenca_texto(anterior, posterior)

    assert [(trecho["operacao"], trecho["texto"]) for trecho in trechos] == esperado
    assert reconstruir(trechos, "anterior") == (anterior or "")
    assert reconstruir(trechos, "posterior") == (posterior or "")
