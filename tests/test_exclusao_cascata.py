"""UC-17 / CT-79 a CT-85 e CT-100: exclusão em cascata de obra e de marco.

O MongoDB é simulado por padrão e o provedor de mídia é sempre simulado: estes
casos não comprovam a remoção real no Cloudinary nem o isolamento do Atlas.
`--atlas` habilita os cenários marcados, inclusive a releitura em outro processo.
"""

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bson import ObjectId

from support import isolated_app, snapshot
from support_avancos import transacao_local  # noqa: F401 - fixture de rollback local
from support_midias import config  # noqa: F401 - credenciais fictícias do provedor

OBRAS = "/obras/"
MARCOS = "/marcos/"
INSTANTE = datetime(2030, 10, 10, 15, tzinfo=timezone.utc)
routes = pytest.mark.routes


def _referencia(pasta, tipo="foto"):
    recurso, formato = {"foto": ("image", "png"), "video": ("video", "mp4"),
                        "documento": ("raw", "pdf")}[tipo]
    sufixo = ".pdf" if recurso == "raw" else ""
    return {"provedor": "cloudinary",
            "public_id": f"{pasta}/{ObjectId()}{'a' * 8}{sufixo}",
            "resource_type": recurso, "delivery_type": "authenticated",
            "formato": formato}


@pytest.fixture
def provedor(monkeypatch, config):
    """Objetos do provedor em memória; `falhas` injeta erro em um arquivo."""
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": config.cloud_name,
                         "CLOUDINARY_API_KEY": config.api_key,
                         "CLOUDINARY_API_SECRET": config.api_secret,
                         "CLOUDINARY_FOLDER": config.pasta}.items():
        monkeypatch.setenv(chave, valor)
    objetos, falhas = {}, set()

    def remover(public_id, resource_type, **opcoes):
        chave = (resource_type, public_id)
        if chave in falhas:
            raise TimeoutError("detalhe privado do provedor")
        existia = objetos.pop(chave, None) is not None
        return {"result": "ok" if existia else "not found"}

    destroy = Mock(side_effect=remover)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    return SimpleNamespace(objetos=objetos, falhas=falhas, destroy=destroy,
                           pasta=config.pasta)


def chave(referencia):
    return referencia["resource_type"], referencia["public_id"]


@pytest.fixture
def cenario(app, database, account, provedor):
    """Obra A completa, obra B preservada e um trabalhador nas duas."""
    autor = str(account["_id"])

    def midia(dono, tipo="foto", campo="avanco_id", referencia=None):
        ref = deepcopy(referencia) if referencia is not None else _referencia(provedor.pasta, tipo)
        provedor.objetos[chave(ref)] = b"arquivo-existente"
        return {"_id": ObjectId(), campo: dono, "tipo": tipo, "nome": "evidencia",
                "mime": {"foto": "image/png", "video": "video/mp4",
                         "documento": "application/pdf"}[tipo],
                "tamanho": 18, "data_envio": INSTANTE, "referencia_externa": ref}

    obra_a, obra_b = ObjectId(), ObjectId()
    m1, m2, m_b = ObjectId(), ObjectId(), ObjectId()
    vinculo = {"_id": ObjectId(), "marco_id": m2, "depende_de_id": m1}
    database.tbl_obras.insert_many([
        {"_id": obra_a, "nome": "Residencial Aurora", "tipo": "apartamentos",
         "cliente": "Cliente de referência", "localizacao": "Campinas, SP",
         "descricao": "Construção residencial", "inicio": "2030-01-15",
         "entrega": {"modalidade": "data_exata", "data": "2030-12-20"},
         "estado": "em andamento", "autor": autor, "data_registro": INSTANTE,
         "versao": 2, "revisao_estado": 1,
         "historico_estados": [{"tipo": "estado_obra", "alvo": {"tipo": "obra", "id": obra_a},
                                "campo": "estado", "valor_anterior": {"estado": "planejada"},
                                "valor_novo": {"estado": "em andamento"},
                                "motivo": "Início das obras", "autor": autor, "instante": INSTANTE}],
         "historico_mudancas": [{"tipo": "entrega_obra", "alvo": {"tipo": "obra", "id": obra_a},
                                 "campo": "entrega", "valor_anterior": {"entrega": {}},
                                 "valor_novo": {"entrega": {"modalidade": "data_exata",
                                                            "data": "2030-12-20"}},
                                 "motivo": "Replanejamento", "autor": autor, "instante": INSTANTE}],
         "dependencias_marcos": [vinculo]},
        {"_id": obra_b, "nome": "Obra preservada", "tipo": "casa",
         "cliente": "Outro cliente", "localizacao": "Valinhos, SP",
         "descricao": "Obra que não entra na cascata", "inicio": "2030-04-01",
         "entrega": {"modalidade": "data_exata", "data": "2031-01-10"},
         "estado": "planejada", "autor": autor, "data_registro": INSTANTE},
    ])
    database.tbl_marcos.insert_many([
        {"_id": m1, "obra_id": obra_a, "nome": "Fundação", "descricao": "Base",
         "inicio_previsto": "2030-02-01", "fim_previsto": "2030-03-01", "estado": "concluído",
         "versao": 1},
        {"_id": m2, "obra_id": obra_a, "nome": "Alvenaria", "descricao": "Paredes",
         "inicio_previsto": "2030-03-01", "fim_previsto": "2030-05-01", "estado": "a iniciar",
         "dependencias": [m1]},
        {"_id": m_b, "obra_id": obra_b, "nome": "Marco de outra obra", "estado": "a iniciar"},
    ])

    rascunho, publicado, avanco_b = ObjectId(), ObjectId(), ObjectId()
    midias_rascunho = [midia(rascunho, tipo) for tipo in ("foto", "video", "documento")]
    midia_publicada = midia(publicado)
    midia_retirada = midia(publicado)
    midia_outra_obra = midia(avanco_b)
    snapshot_publicacao = [{"id": str(midia_publicada["_id"]), "avanco_id": str(publicado),
                            "tipo": "foto", "nome": "evidencia", "tamanho": 18,
                            "mime": "image/png", "visibilidade": "privada"}]

    def fato(data, descricao, marco_id, nome, midias):
        return {"autor": autor, "instante": INSTANTE, "data": data, "descricao": descricao,
                "marco": {"id": marco_id, "nome": nome}, "midias": midias}

    database.tbl_avancos.insert_many([
        {"_id": rascunho, "marco_id": m1, "data": "2030-02-10", "descricao": "Rascunho",
         "estado": "rascunho", "autor": autor, "data_registro": INSTANTE, "revisao": 0},
        {"_id": publicado, "marco_id": m1, "data": "2030-02-20", "descricao": "Concretagem",
         "estado": "publicado", "autor": autor, "data_registro": INSTANTE, "revisao": 2,
         "editado": True, "origem_simulada": {"perfil": "engenheiro", "nome": "Engenheira exemplo"},
         "publicacao": fato("2030-02-20", "Concretagem da base", m1, "Fundação",
                            snapshot_publicacao),
         "correcoes": [{"motivo": "Correção da descrição", "autor": autor, "instante": INSTANTE,
                        "antes": {"data": "2030-02-20", "descricao": "Concretagem da base",
                                  "midias": snapshot_publicacao},
                        "depois": {"data": "2030-02-20", "descricao": "Concretagem",
                                   "midias": snapshot_publicacao}}]},
        {"_id": avanco_b, "marco_id": m_b, "data": "2030-02-20", "descricao": "Outra obra",
         "estado": "publicado", "autor": autor, "data_registro": INSTANTE,
         "publicacao": fato("2030-02-20", "Outra obra", m_b, "Marco de outra obra", [])},
    ])
    database.tbl_midias.insert_many(
        deepcopy(midias_rascunho + [midia_publicada, midia_outra_obra]))
    # Tarefa de limpeza pendente de uma edição anterior do mesmo avanço.
    database.tbl_limpezas_midias.insert_one(
        {"_id": midia_retirada["_id"], "avanco_id": publicado, "midia": deepcopy(midia_retirada)})
    database.tbl_uploads_pendentes.insert_one(
        {"_id": "a" * 64, "avanco_id": rascunho, "tipo": "edicao", "estado": "pendente",
         "referencias": [], "iniciado_em": INSTANTE})

    ocorrencia = ObjectId()
    evidencia = midia(ocorrencia, campo="ocorrencia_id")
    database.tbl_ocorrencias.insert_one(
        {"_id": ocorrencia, "obra_id": obra_a, "marco_id": m1, "autor": autor,
         "titulo": "Infiltração", "descricao": "Parede úmida", "estado": "sem solução",
         "responsavel_id": None, "data_registro": INSTANTE,
         "midias": [deepcopy(evidencia)],
         "aceitacoes": [{"justificativa": "Sem solução viável", "autor": autor, "data": INSTANTE}]})
    database.tbl_historico.insert_many([
        {"_id": ObjectId(), "tipo": "estado_marco", "alvo": {"tipo": "marco", "id": m1},
         "campo": "estado", "valor_anterior": {"estado": "em andamento"},
         "valor_novo": {"estado": "concluído"}, "motivo": "Etapa concluída",
         "autor": autor, "instante": INSTANTE},
        {"_id": ObjectId(), "tipo": "fim_previsto_marco", "alvo": {"tipo": "marco", "id": m2},
         "campo": "fim_previsto", "valor_anterior": {"fim_previsto": "2030-04-01"},
         "valor_novo": {"fim_previsto": "2030-05-01"}, "motivo": "Replanejamento",
         "autor": autor, "instante": INSTANTE},
    ])

    trabalhador_duplo, trabalhador_b = ObjectId(), ObjectId()
    database.tbl_trabalhadores.insert_many([
        {"_id": trabalhador_duplo, "nome": "Pessoa nas duas obras",
         "email": "duplo@example.com", "telefone": "19999990000", "cargo": "mestre de obras",
         "construtora_id": autor, "data_cadastro": INSTANTE, "ativo": True,
         "obras": [str(obra_a), str(obra_b)]},
        {"_id": trabalhador_b, "nome": "Somente na obra preservada",
         "email": "outro@example.com", "telefone": "19999990001", "cargo": "pedreiro",
         "construtora_id": autor, "data_cadastro": INSTANTE, "ativo": True,
         "obras": [str(obra_b)]},
    ])

    return SimpleNamespace(
        autor=autor, obra=obra_a, obra_b=obra_b, marco=m1, marco_dependente=m2, marco_b=m_b,
        vinculo=vinculo, rascunho=rascunho, publicado=publicado, avanco_b=avanco_b,
        ocorrencia=ocorrencia, evidencia=evidencia, midias_rascunho=midias_rascunho,
        midia_publicada=midia_publicada, midia_retirada=midia_retirada,
        midia_outra_obra=midia_outra_obra, trabalhador=trabalhador_duplo,
        trabalhador_b=trabalhador_b, midia=midia,
        caminho=OBRAS + str(obra_a), caminho_marco=MARCOS + str(m1),
        objetos=provedor.objetos, falhas=provedor.falhas, destroy=provedor.destroy,
    )


def ids_do_conjunto(cenario):
    return {cenario.obra, cenario.marco, cenario.marco_dependente, cenario.rascunho,
            cenario.publicado, cenario.ocorrencia, cenario.evidencia["_id"],
            cenario.midia_publicada["_id"], cenario.midia_retirada["_id"],
            *(midia["_id"] for midia in cenario.midias_rascunho)}


def arquivos_do_conjunto(cenario):
    return {chave(midia["referencia_externa"]) for midia in
            [*cenario.midias_rascunho, cenario.midia_publicada,
             cenario.midia_retirada, cenario.evidencia]}


def menciona(valor, identificadores):
    if isinstance(valor, dict):
        return any(menciona(item, identificadores) for item in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(menciona(item, identificadores) for item in valor)
    return isinstance(valor, (ObjectId, str)) and str(valor) in identificadores


def referencias_restantes(database, identificadores):
    textos = {str(valor) for valor in identificadores}
    achados = []
    for nome in database.list_collection_names():
        for documento in database[nome].find():
            if menciona(documento, textos):
                achados.append((nome, documento["_id"]))
    return achados


# --- CT-79: a confirmação precede qualquer remoção -------------------------


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct79_aviso_identifica_obra_e_extensao_da_perda(client, headers, database, cenario):
    # Preparação
    antes = snapshot(database)
    # Execução: a tela abre a confirmação; o servidor recusa sem o campo.
    resposta = client.delete(cenario.caminho, headers=headers)
    # Verificação
    assert resposta.status_code == 422
    corpo = resposta.get_json()
    assert corpo["codigo"] == "CONFIRMACAO_OBRIGATORIA" and corpo["campos"] == ["confirmar"]
    assert corpo["alvo"]["nome"] == "Residencial Aurora"
    assert corpo["alvo"]["tipo"] == "obra" and corpo["alvo"]["id"] == str(cenario.obra)
    assert corpo["perda"] == {
        "marcos": 2, "avancos": 2, "publicacoes": 1, "versoes": 1, "exemplos_simulados": 1,
        "ocorrencias": 1, "aceitacoes": 1, "midias": 6, "mudancas": 1, "estados": 1,
        "dependencias": 1, "historico": 2, "trabalhadores_desvinculados": 1,
    }
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct79_cancelar_nao_envia_delete_e_consultas_nao_alteram(client, headers, database, cenario):
    # Preparação
    antes = snapshot(database)
    objetos = dict(cenario.objetos)
    # Execução: tudo que a tela de confirmação precisa ler antes de confirmar.
    # As mesmas leituras devem responder 404 depois da cascata (CT-80).
    for caminho in (
        cenario.caminho, cenario.caminho + "/marcos", cenario.caminho + "/ocorrencias",
        cenario.caminho + "/previa", cenario.caminho + "/mudancas",
        f"{cenario.caminho}/marcos/{cenario.marco}",
        MARCOS + str(cenario.marco) + "/avancos",
        MARCOS + str(cenario.marco_dependente) + "/dependencias",
        "/avancos/" + str(cenario.publicado),
        "/avancos/" + str(cenario.publicado) + "/versoes",
        "/avancos/" + str(cenario.publicado) + "/midias",
        "/avancos/" + str(cenario.publicado) + "/publicacoes",
        "/ocorrencias/" + str(cenario.ocorrencia),
        "/ocorrencias/" + str(cenario.ocorrencia) + "/aceitacoes",
        "/midias/" + str(cenario.midia_publicada["_id"]),
        "/midias/" + str(cenario.evidencia["_id"]),
    ):
        assert client.get(caminho, headers=headers).status_code == 200, caminho
    # Verificação
    assert snapshot(database) == antes
    assert cenario.objetos == objetos
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("corpo,tipo", [
    pytest.param({"confirmar": False}, "json", id="recusada"),
    pytest.param({"confirmar": "true"}, "json", id="texto"),
    pytest.param({"confirmar": True, "forcar": True}, "json", id="campo-extra"),
    pytest.param({}, "json", id="objeto-vazio"),
    pytest.param(None, "sem-corpo", id="sem-corpo"),
    pytest.param("confirmar=1", "form", id="formulario"),
])
@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"),
        ("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct79_campo_de_confirmacao_e_validado_explicitamente(
    client, headers, database, cenario, corpo, tipo
):
    # Preparação
    antes = snapshot(database)
    opcoes = {"json": corpo} if tipo == "json" else {}
    if tipo == "form":
        opcoes = {"data": corpo, "content_type": "application/x-www-form-urlencoded"}
    # Execução
    respostas = [client.delete(caminho, headers=headers, **opcoes)
                 for caminho in (cenario.caminho, cenario.caminho_marco)]
    # Verificação
    for resposta in respostas:
        assert resposta.status_code == 422, resposta.get_data(as_text=True)
        assert resposta.get_json()["codigo"] == "CONFIRMACAO_OBRIGATORIA"
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


# --- CT-80 e CT-81: cascata confirmada e ausência de órfãos ----------------


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct80_confirmar_remove_obra_com_todos_os_dependentes(
    client, headers, database, cenario, transacao_local
):
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 204 and resposta.data == b""
    assert database.tbl_obras.find_one({"_id": cenario.obra}) is None
    assert database.tbl_marcos.count_documents({"obra_id": cenario.obra}) == 0
    assert database.tbl_avancos.count_documents(
        {"_id": {"$in": [cenario.rascunho, cenario.publicado]}}) == 0
    assert database.tbl_midias.count_documents(
        {"avanco_id": {"$in": [cenario.rascunho, cenario.publicado]}}) == 0
    assert database.tbl_limpezas_midias.count_documents({"avanco_id": cenario.publicado}) == 0
    assert database.tbl_uploads_pendentes.count_documents({"avanco_id": cenario.rascunho}) == 0
    assert database.tbl_ocorrencias.find_one({"_id": cenario.ocorrencia}) is None
    assert database.tbl_historico.count_documents({}) == 0
    # Arquivos do conjunto saem do provedor; o da outra obra permanece.
    assert set(cenario.objetos) == {chave(cenario.midia_outra_obra["referencia_externa"])}
    assert cenario.destroy.call_count == len(arquivos_do_conjunto(cenario))


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct80_recursos_da_obra_deixam_de_ser_acessiveis(
    client, headers, cenario, transacao_local
):
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação
    ausentes = [
        cenario.caminho, cenario.caminho + "/marcos", cenario.caminho + "/previa",
        f"{cenario.caminho}/marcos/{cenario.marco}",
        MARCOS + str(cenario.marco) + "/avancos",
        MARCOS + str(cenario.marco) + "/dependencias",
        "/avancos/" + str(cenario.publicado),
        "/avancos/" + str(cenario.publicado) + "/versoes",
        "/avancos/" + str(cenario.publicado) + "/midias",
        "/avancos/" + str(cenario.publicado) + "/publicacoes",
        "/ocorrencias/" + str(cenario.ocorrencia),
        "/ocorrencias/" + str(cenario.ocorrencia) + "/aceitacoes",
        "/midias/" + str(cenario.midia_publicada["_id"]),
        "/midias/" + str(cenario.evidencia["_id"]),
        "/midias/" + str(cenario.midia_publicada["_id"]) + "/conteudo",
    ]
    for caminho in ausentes:
        assert client.get(caminho, headers=headers).status_code == 404, caminho
    lista = client.get("/obras", headers=headers)
    assert lista.status_code == 200
    assert [obra["id"] for obra in lista.get_json()["obras"]] == [str(cenario.obra_b)]


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct81_nenhuma_referencia_orfa_em_qualquer_colecao(
    client, headers, database, cenario, transacao_local
):
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação
    assert referencias_restantes(database, ids_do_conjunto(cenario)) == []
    assert database[ "tbl_exclusoes_pendentes"].count_documents({}) == 0


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct81_referencia_de_fora_impede_a_exclusao_em_vez_de_virar_orfa(
    client, headers, database, cenario, transacao_local
):
    # Preparação: um registro de outra obra passa a citar um marco do conjunto.
    database.tbl_ocorrencias.insert_one(
        {"_id": ObjectId(), "obra_id": cenario.obra_b, "marco_id": cenario.marco,
         "autor": cenario.autor, "titulo": "Vínculo indevido", "descricao": "Aponta para fora",
         "estado": "aberta", "responsavel_id": None, "data_registro": INSTANTE,
         "midias": [], "aceitacoes": []})
    antes = snapshot(database)
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "REFERENCIA_EXTERNA"
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct81_outra_obra_permanece_intacta(client, headers, database, cenario, transacao_local):
    # Preparação
    preservados = {
        "tbl_obras": database.tbl_obras.find_one({"_id": cenario.obra_b}),
        "tbl_marcos": database.tbl_marcos.find_one({"_id": cenario.marco_b}),
        "tbl_avancos": database.tbl_avancos.find_one({"_id": cenario.avanco_b}),
        "tbl_midias": database.tbl_midias.find_one({"_id": cenario.midia_outra_obra["_id"]}),
    }
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação
    assert database.tbl_obras.find_one({"_id": cenario.obra_b}) == preservados["tbl_obras"]
    assert database.tbl_marcos.find_one({"_id": cenario.marco_b}) == preservados["tbl_marcos"]
    assert database.tbl_avancos.find_one({"_id": cenario.avanco_b}) == preservados["tbl_avancos"]
    assert database.tbl_midias.find_one(
        {"_id": cenario.midia_outra_obra["_id"]}) == preservados["tbl_midias"]
    assert client.get(OBRAS + str(cenario.obra_b), headers=headers).status_code == 200


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct80_preserva_arquivo_ainda_referenciado_fora_do_conjunto(
    client, headers, database, cenario, transacao_local
):
    # Preparação: a outra obra compartilha o arquivo de uma mídia do conjunto.
    nova = cenario.midia(
        cenario.avanco_b, referencia=cenario.midias_rascunho[0]["referencia_externa"])
    database.tbl_midias.insert_one(deepcopy(nova))
    compartilhada = database.tbl_midias.find_one({"_id": nova["_id"]})
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 204
    assert chave(compartilhada["referencia_externa"]) in cenario.objetos
    assert cenario.destroy.call_count == len(arquivos_do_conjunto(cenario)) - 1
    assert database.tbl_midias.find_one({"_id": compartilhada["_id"]}) == compartilhada
    assert client.get("/midias/" + str(compartilhada["_id"]),
                      headers=headers).status_code == 200


# --- CT-82: exclusão de marco com dependência de outro marco --------------


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct82_aviso_do_marco_mostra_dependencia_e_nao_remove_nada(
    client, headers, database, cenario
):
    # Preparação
    antes = snapshot(database)
    # Execução
    resposta = client.delete(cenario.caminho_marco, headers=headers)
    # Verificação
    assert resposta.status_code == 422
    corpo = resposta.get_json()
    assert corpo["alvo"] == {"tipo": "marco", "id": str(cenario.marco), "nome": "Fundação",
                             "obra_id": str(cenario.obra)}
    assert corpo["perda"] == {
        "avancos": 2, "publicacoes": 1, "versoes": 1, "exemplos_simulados": 1,
        "ocorrencias": 1, "aceitacoes": 1, "midias": 6, "historico": 1, "dependencias": 1,
    }
    assert snapshot(database) == antes


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct82_marco_sai_com_dependentes_e_o_outro_marco_permanece(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    outro = database.tbl_marcos.find_one({"_id": cenario.marco_dependente})
    # Execução
    resposta = client.delete(cenario.caminho_marco, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 204
    assert database.tbl_marcos.find_one({"_id": cenario.marco}) is None
    assert database.tbl_avancos.count_documents({"marco_id": cenario.marco}) == 0
    assert database.tbl_historico.count_documents({"alvo.id": cenario.marco}) == 0
    # O marco dependente continua, sem o vínculo e sem a lista legada.
    restante = database.tbl_marcos.find_one({"_id": cenario.marco_dependente})
    assert restante == {**outro, "dependencias": []}
    obra = database.tbl_obras.find_one({"_id": cenario.obra})
    assert obra["dependencias_marcos"] == []
    assert obra["nome"] == "Residencial Aurora" and obra["estado"] == "em andamento"
    assert database.tbl_historico.count_documents({"alvo.id": cenario.marco_dependente}) == 1
    assert client.get(cenario.caminho, headers=headers).status_code == 200
    assert client.get(f"{cenario.caminho}/marcos/{cenario.marco_dependente}",
                      headers=headers).status_code == 200
    assert client.get(MARCOS + str(cenario.marco_dependente) + "/dependencias",
                      headers=headers).get_json() == []


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct82_marco_excluido_nao_deixa_referencia_nem_ocorrencia(
    client, headers, database, cenario, transacao_local
):
    # Execução
    assert client.delete(cenario.caminho_marco, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação: política proposta em P-08 — a ocorrência do marco sai na cascata.
    assert database.tbl_ocorrencias.find_one({"_id": cenario.ocorrencia}) is None
    alvo = ids_do_conjunto(cenario) - {cenario.obra, cenario.marco_dependente}
    assert referencias_restantes(database, alvo) == []
    assert client.get("/ocorrencias/" + str(cenario.ocorrencia),
                      headers=headers).status_code == 404


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct82_dependencia_inversa_tambem_e_retirada(
    client, headers, database, cenario, transacao_local
):
    # Preparação: o alvo passa a depender do outro marco, no sentido oposto.
    inverso = {"_id": ObjectId(), "marco_id": cenario.marco,
               "depende_de_id": cenario.marco_dependente}
    database.tbl_obras.update_one({"_id": cenario.obra},
                                  {"$push": {"dependencias_marcos": inverso}})
    # Execução
    resposta = client.delete(cenario.caminho_marco, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 204
    assert database.tbl_obras.find_one({"_id": cenario.obra})["dependencias_marcos"] == []
    assert database.tbl_marcos.find_one({"_id": cenario.marco_dependente}) is not None


# --- CT-83: alvo inexistente e repetição ----------------------------------


@pytest.mark.parametrize("alvo", ["obra", "marco"])
@pytest.mark.parametrize("identificador,status", [
    pytest.param("invalido", 400, id="id-invalido"),
    pytest.param("507f1f77bcf86cd799439011", 404, id="inexistente"),
])
@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"),
        ("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct83_alvo_invalido_ou_inexistente_nao_afeta_nada(
    client, headers, database, cenario, alvo, identificador, status
):
    # Preparação
    antes = snapshot(database)
    base = OBRAS if alvo == "obra" else MARCOS
    # Execução
    resposta = client.delete(base + identificador, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == status
    assert resposta.get_json()["mensagem"]
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("alvo", ["obra", "marco"])
@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"),
        ("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct83_repetir_exclusao_concluida_responde_inexistencia(
    client, headers, database, cenario, transacao_local, alvo
):
    # Preparação
    caminho = cenario.caminho if alvo == "obra" else cenario.caminho_marco
    assert client.delete(caminho, json={"confirmar": True}, headers=headers).status_code == 204
    depois = snapshot(database)
    chamadas = cenario.destroy.call_count
    # Execução
    repetida = client.delete(caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert repetida.status_code == 404
    assert snapshot(database) == depois
    assert cenario.destroy.call_count == chamadas


@pytest.mark.parametrize("alvo", ["obra", "marco"])
@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"),
        ("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_exclusao_exige_sessao_de_construtora_ativa(
    client, headers, database, account, emitir_headers, cenario, alvo
):
    # Preparação
    caminho = cenario.caminho if alvo == "obra" else cenario.caminho_marco
    antes = snapshot(database)
    # Execução
    sem_token = client.delete(caminho, json={"confirmar": True})
    outro_perfil = client.delete(caminho, json={"confirmar": True},
                                 headers=emitir_headers(claims={"tipo": "trabalhador"}))
    database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    inativa = client.delete(caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert [sem_token.status_code, outro_perfil.status_code, inativa.status_code] == [401, 403, 401]
    database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": True}})
    assert snapshot(database) == antes


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_obra_de_outra_construtora_nao_e_excluida(client, headers, database, cenario):
    # Preparação
    database.tbl_obras.update_one({"_id": cenario.obra}, {"$set": {"autor": str(ObjectId())}})
    antes = snapshot(database)
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    marco = client.delete(cenario.caminho_marco, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 404 and marco.status_code == 404
    assert snapshot(database) == antes


# --- CT-84: falha na remoção dos arquivos externos ------------------------


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct84_falha_externa_nao_e_relatada_como_cascata_concluida(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    cenario.falhas.add(chave(cenario.midia_publicada["referencia_externa"]))
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 503
    corpo = resposta.get_json()
    assert corpo["codigo"] == "LIMPEZA_PENDENTE" and corpo["pendentes"] == 1
    assert corpo["pendencia"] and "cloudinary" not in resposta.get_data(as_text=True).lower()
    # A pendência é durável e rastreável; o arquivo continua no provedor.
    pendencia = database.tbl_exclusoes_pendentes.find_one({"_id": ObjectId(corpo["pendencia"])})
    assert pendencia["alvo"] == {"tipo": "obra", "id": cenario.obra,
                                 "nome": "Residencial Aurora"}
    assert len(pendencia["pendentes"]) == 1
    assert pendencia["ultimo_erro"] and pendencia["ultima_falha_em"]
    assert pendencia["token"] is None, "o bloqueio é liberado para a retomada"
    assert chave(cenario.midia_publicada["referencia_externa"]) in cenario.objetos
    # Os documentos saíram do banco: a falha é só da limpeza externa.
    assert database.tbl_obras.find_one({"_id": cenario.obra}) is None
    assert referencias_restantes(database, ids_do_conjunto(cenario)) == [
        ("tbl_exclusoes_pendentes", pendencia["_id"])]


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct84_repetir_delete_retoma_a_limpeza_e_conclui(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    arquivo = chave(cenario.midia_publicada["referencia_externa"])
    cenario.falhas.add(arquivo)
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 503
    tentativas = database.tbl_exclusoes_pendentes.find_one({})["tentativas"]
    cenario.falhas.clear()
    # Execução: a mesma requisição retoma a limpeza do que ficou pendente.
    retomada = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert retomada.status_code == 204
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 0
    assert arquivo not in cenario.objetos
    assert set(cenario.objetos) == {chave(cenario.midia_outra_obra["referencia_externa"])}
    assert tentativas == 1
    assert referencias_restantes(database, ids_do_conjunto(cenario)) == []


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_ct84_limpeza_em_andamento_nao_e_atropelada(
    client, headers, database, cenario, transacao_local
):
    # Preparação: falha deixa a pendência registrada e um bloqueio ativo.
    cenario.falhas.add(chave(cenario.evidencia["referencia_externa"]))
    assert client.delete(cenario.caminho_marco, json={"confirmar": True},
                         headers=headers).status_code == 503
    database.tbl_exclusoes_pendentes.update_one(
        {}, {"$set": {"token": "outra-requisicao",
                      "ate": datetime(2030, 10, 20, 13, tzinfo=timezone.utc)}})
    # Execução
    resposta = client.delete(cenario.caminho_marco, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 409
    assert resposta.get_json()["codigo"] == "CONFLITO_EXCLUSAO"
    assert database.tbl_exclusoes_pendentes.find_one({})["token"] == "outra-requisicao"


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct84_referencia_de_midia_invalida_nao_remove_nada(
    client, headers, database, cenario
):
    # Preparação
    database.tbl_midias.update_one({"_id": cenario.midia_publicada["_id"]},
                                   {"$set": {"referencia_externa.delivery_type": "upload"}})
    antes = snapshot(database)
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 422
    assert resposta.get_json()["codigo"] == "REFERENCIA_INVALIDA"
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct84_falha_no_banco_nao_remove_parte_do_conjunto(
    client, headers, database, cenario, monkeypatch, transacao_local
):
    """Sem `--atlas` o rollback é simulado: não comprova a transação real."""
    # Preparação: a trilha do marco falha depois dos avanços saírem.
    from app.historico.repository import RepositorioHistorico

    def recusar(self, ids, *, session=None):
        raise RuntimeError("falha simulada durante a cascata")

    monkeypatch.setattr(RepositorioHistorico, "remover_eventos_dos_alvos", recusar)
    antes = snapshot(database)
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 500
    assert resposta.is_json and resposta.get_json()["codigo"] == "EXCLUSAO_NAO_CONCLUIDA"
    assert "falha simulada" not in resposta.get_data(as_text=True)
    assert snapshot(database) == antes
    cenario.destroy.assert_not_called()


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct84_commit_indeterminado_nao_remove_arquivos(
    client, headers, database, cenario, monkeypatch, transacao_local
):
    # Preparação: o commit pode ter ocorrido; a resposta não pode afirmar nada.
    from pymongo.errors import PyMongoError

    import app.obras.repository as obras_repository

    original = obras_repository.remover_obra

    def indeterminado(obra_id, *, session=None):
        raise PyMongoError("detalhe interno",
                           error_labels=["UnknownTransactionCommitResult"])

    monkeypatch.setattr(obras_repository, "remover_obra", indeterminado)
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 503
    corpo = resposta.get_json()
    assert corpo["codigo"] == "EXCLUSAO_INDETERMINADA" and corpo["pendencia"]
    assert "detalhe interno" not in resposta.get_data(as_text=True)
    # Nenhum arquivo é removido sem a confirmação da escrita.
    cenario.destroy.assert_not_called()
    assert set(cenario.objetos) >= arquivos_do_conjunto(cenario)
    # Repetir é seguro: ou retoma a pendência, ou refaz a cascata.
    monkeypatch.setattr(obras_repository, "remover_obra", original)
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code in (204, 404)
    assert database.tbl_obras.find_one({"_id": cenario.obra}) is None


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_cascata_sem_midias_nao_exige_credenciais_do_provedor(
    client, headers, database, cenario, monkeypatch, transacao_local
):
    # Preparação
    database.tbl_midias.delete_many({})
    database.tbl_limpezas_midias.delete_many({})
    database.tbl_ocorrencias.update_one({"_id": cenario.ocorrencia},
                                        {"$set": {"midias": []}})
    monkeypatch.delenv("CLOUDINARY_API_SECRET")
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação
    assert resposta.status_code == 204
    assert database.tbl_obras.find_one({"_id": cenario.obra}) is None
    assert database.tbl_exclusoes_pendentes.count_documents({}) == 0
    cenario.destroy.assert_not_called()


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_politica_alternativa_de_p08_desvincula_em_vez_de_excluir(
    client, headers, database, cenario, monkeypatch, transacao_local
):
    """P-08 continua aberta: a alternativa precisa funcionar sem deixar órfão."""
    # Preparação
    import app.marcos.exclusoes as exclusoes

    monkeypatch.setattr(exclusoes, "OCORRENCIAS_NA_CASCATA", False)
    # Execução
    resposta = client.delete(cenario.caminho_marco, json={"confirmar": True},
                             headers=headers)
    # Verificação
    assert resposta.status_code == 204
    ocorrencia = database.tbl_ocorrencias.find_one({"_id": cenario.ocorrencia})
    assert ocorrencia is not None and ocorrencia["marco_id"] is None
    assert ocorrencia["aceitacoes"] and ocorrencia["midias"]
    assert database.tbl_marcos.find_one({"_id": cenario.marco}) is None
    assert client.get("/ocorrencias/" + str(cenario.ocorrencia),
                      headers=headers).status_code == 200
    # A evidência da ocorrência preservada não pode ter ido ao provedor.
    assert chave(cenario.evidencia["referencia_externa"]) in cenario.objetos


# --- CT-100: trabalhador vinculado a mais de uma obra ---------------------


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct100_excluir_obra_a_preserva_cadastro_e_vinculo_b(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    somente_b = database.tbl_trabalhadores.find_one({"_id": cenario.trabalhador_b})
    antes = database.tbl_trabalhadores.find_one({"_id": cenario.trabalhador})
    # Execução
    resposta = client.delete(cenario.caminho, json={"confirmar": True}, headers=headers)
    # Verificação: política proposta em P-09 — vínculo retirado, cadastro mantido.
    assert resposta.status_code == 204
    depois = database.tbl_trabalhadores.find_one({"_id": cenario.trabalhador})
    assert depois == {**antes, "obras": [str(cenario.obra_b)]}
    assert database.tbl_trabalhadores.find_one({"_id": cenario.trabalhador_b}) == somente_b
    assert database.tbl_trabalhadores.count_documents({}) == 2
    lista = client.get(f"/trabalhadores/obra/{cenario.obra_b}/", headers=headers)
    assert sorted(item["id"] for item in lista.get_json()) == sorted(
        [str(cenario.trabalhador), str(cenario.trabalhador_b)])


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct100_vinculo_unico_tambem_preserva_o_cadastro(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    database.tbl_trabalhadores.update_one({"_id": cenario.trabalhador},
                                          {"$set": {"obras": [str(cenario.obra)]}})
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação
    documento = database.tbl_trabalhadores.find_one({"_id": cenario.trabalhador})
    assert documento is not None and documento["obras"] == []
    assert documento["ativo"] is True


@routes(("DELETE", MARCOS + "507f1f77bcf86cd799439011"))
def test_excluir_marco_nao_altera_vinculos_de_trabalhadores(
    client, headers, database, cenario, transacao_local
):
    # Preparação
    antes = sorted(database.tbl_trabalhadores.find(), key=lambda doc: str(doc["_id"]))
    # Execução
    assert client.delete(cenario.caminho_marco, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação
    assert sorted(database.tbl_trabalhadores.find(),
                  key=lambda doc: str(doc["_id"])) == antes


# --- CT-85: a exclusão persiste depois do reinício ------------------------


@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct85_aplicacao_recarregada_nao_recupera_os_dados(
    client, headers, database, cenario, transacao_local
):
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    # Verificação: nova instância Flask relê o mesmo banco, sem estado em memória.
    with isolated_app(database) as recarregada:
        with recarregada.test_client() as fresco:
            for caminho in (cenario.caminho, f"{cenario.caminho}/marcos/{cenario.marco}",
                            "/avancos/" + str(cenario.publicado),
                            "/ocorrencias/" + str(cenario.ocorrencia),
                            "/midias/" + str(cenario.midia_publicada["_id"])):
                assert fresco.get(caminho, headers=headers).status_code == 404, caminho


@pytest.mark.atlas
@routes(("DELETE", OBRAS + "507f1f77bcf86cd799439011"))
def test_ct85_processo_novo_no_atlas_nao_recupera_os_dados(
    client, headers, database, cenario
):
    # Preparação
    probe = Path(__file__).resolve().parent / "restart_probe.py"
    # Execução
    assert client.delete(cenario.caminho, json={"confirmar": True},
                         headers=headers).status_code == 204
    resultado = subprocess.run(
        [sys.executable, str(probe)],
        env=dict(os.environ, TEST_COLLECTION_PREFIX=database.prefixo,
                 TEST_RESOURCE_PATH=cenario.caminho),
        capture_output=True, text=True, timeout=60,
    )
    # Verificação
    assert resultado.returncode == 0, "Falha no processo novo; credenciais omitidas"
    assert json.loads(resultado.stdout)["status"] == 404
    assert database.tbl_obras.find_one({"_id": cenario.obra}) is None
    assert referencias_restantes(database, ids_do_conjunto(cenario)) == []
