"""UC-09 / CT-39: exclusão, arquivos compartilhados e limpeza retomável."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from bson import ObjectId
from flask_jwt_extended import decode_token
from freezegun import freeze_time
from pymongo.errors import PyMongoError

from support import snapshot
from support_midias import config

BASE = "/avancos/"


@pytest.fixture
def cenario(app, database, account, monkeypatch, config):
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": config.cloud_name,
                         "CLOUDINARY_API_KEY": config.api_key,
                         "CLOUDINARY_API_SECRET": config.api_secret,
                         "CLOUDINARY_FOLDER": config.pasta}.items():
        monkeypatch.setenv(chave, valor)
    obra = database.tbl_obras.insert_one({"nome": "Obra", "autor": str(account["_id"])}).inserted_id
    marco = database.tbl_marcos.insert_one({"obra_id": obra, "nome": "Marco"}).inserted_id
    avanco = {"_id": ObjectId(), "marco_id": marco, "estado": "rascunho", "revisao": 0,
              "autor": str(account["_id"]), "descricao": "Rascunho descartável"}
    database.tbl_avancos.insert_one(avanco)
    objetos, falhas = {}, set()
    def adicionar(tipo="foto", dono=None, referencia=None):
        recurso, mime, formato = {"foto": ("image", "image/png", "png"),
                                  "video": ("video", "video/mp4", "mp4"),
                                  "documento": ("raw", "application/pdf", "pdf")}[tipo]
        ref = deepcopy(referencia) if referencia is not None else {
            "provedor": "cloudinary", "public_id": config.pasta + "/" + str(ObjectId()) + "a" * 8 + (".pdf" if recurso == "raw" else ""),
            "resource_type": recurso, "delivery_type": "authenticated", "formato": formato}
        chave = (ref["resource_type"], ref["public_id"])
        objetos[chave] = b"arquivo-existente"
        doc = {"_id": ObjectId(), "avanco_id": avanco["_id"] if dono is None else dono,
               "tipo": tipo, "mime": mime, "nome": "evidencia." + formato,
               "tamanho": len(objetos[chave]), "referencia_externa": ref}
        database.tbl_midias.insert_one(doc)
        return doc
    midias = [adicionar(tipo) for tipo in ("foto", "video", "documento")]
    def remover(public_id, resource_type, **opcoes):
        chave = (resource_type, public_id)
        if chave in falhas:
            raise TimeoutError("detalhe privado do provedor")
        existia = objetos.pop(chave, None) is not None
        return {"result": "ok" if existia else "not found"}
    destroy = Mock(side_effect=remover)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    return SimpleNamespace(avanco=avanco, midias=midias, adicionar=adicionar,
                           objetos=objetos, falhas=falhas, destroy=destroy, remover=remover,
                           path=BASE + str(avanco["_id"]))


def chave(midia):
    ref = midia["referencia_externa"]
    return ref["resource_type"], ref["public_id"]


def test_ct39_exclui_rascunho_e_tres_tipos_sem_afetar_outros(client, headers, database, cenario):
    # Preparação
    outro = {"_id": ObjectId(), "estado": "rascunho", "descricao": "Preservado"}
    database.tbl_avancos.insert_one(outro)
    outra_midia = cenario.adicionar(dono=outro["_id"])
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204 and response.data == b""
    assert database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]}) is None
    assert database.tbl_midias.count_documents({"avanco_id": cenario.avanco["_id"]}) == 0
    assert database.tbl_avancos.find_one({"_id": outro["_id"]}) == outro
    assert database.tbl_midias.find_one({"_id": outra_midia["_id"]}) == outra_midia
    assert set(cenario.objetos) == {chave(outra_midia)}
    assert cenario.destroy.call_count == 3
    assert client.get(cenario.path + "/midias", headers=headers).status_code == 404
    assert client.get("/midias/" + str(cenario.midias[0]["_id"]), headers=headers).status_code == 404
    assert client.get(cenario.path + "/publicacoes", headers=headers).status_code == 404


def test_ct39_nenhuma_alteracao_antes_do_delete(client, headers, database, cenario):
    # Preparação
    before = snapshot(database)
    objetos = dict(cenario.objetos)
    # Execução: apenas consultas, como abrir/cancelar a confirmação na interface.
    assert client.get(cenario.path + "/midias", headers=headers).status_code == 200
    assert client.get("/midias/" + str(cenario.midias[0]["_id"]), headers=headers).status_code == 200
    # Verificação
    assert snapshot(database) == before
    assert cenario.objetos == objetos
    cenario.destroy.assert_not_called()


def test_ct39_sem_midia_nao_exige_credenciais(client, headers, database, cenario, monkeypatch):
    # Preparação
    database.tbl_midias.delete_many({"avanco_id": cenario.avanco["_id"]})
    cenario.objetos.clear()
    monkeypatch.delenv("CLOUDINARY_API_SECRET")
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("estado", ["rascunho", "publicado"])
def test_ct39_preserva_arquivo_compartilhado(client, headers, database, cenario, estado):
    # Preparação
    outro = database.tbl_avancos.insert_one({"estado": estado}).inserted_id
    midia = cenario.adicionar(dono=outro, referencia=cenario.midias[0]["referencia_externa"])
    antes = database.tbl_avancos.find_one({"_id": outro})
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204
    assert chave(midia) in cenario.objetos
    assert cenario.destroy.call_count == 2
    assert database.tbl_midias.find_one({"_id": midia["_id"]}) == midia
    assert database.tbl_avancos.find_one({"_id": outro}) == antes
    assert client.get("/midias/" + str(midia["_id"]), headers=headers).status_code == 200


def test_ct39_deduplica_referencias_ao_mesmo_objeto(client, headers, cenario):
    # Preparação: mesma referência com ordem diferente e formato extra.
    ref = dict(reversed(list(cenario.midias[0]["referencia_externa"].items())))
    ref["formato"] = "jpeg"
    cenario.adicionar(referencia=ref)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204
    assert cenario.destroy.call_count == 3
    assert not cenario.objetos


@pytest.mark.parametrize("tipo", ["referencia", "id"])
def test_ct39_preserva_arquivo_referenciado_no_historico(client, headers, database, cenario, tipo):
    # Preparação
    valor = {"referencia_externa": cenario.midias[0]["referencia_externa"]} if tipo == "referencia" else {"id": str(cenario.midias[0]["_id"])}
    historico = {"_id": ObjectId(), "versao_anterior": {"midias": [valor]}}
    database.tbl_historico.insert_one(historico)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    if tipo == "id":
        assert response.status_code == 409
        assert database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]})["estado"] == "rascunho"
        assert client.get("/midias/" + str(cenario.midias[0]["_id"]), headers=headers).status_code == 200
        cenario.destroy.assert_not_called()
    else:
        assert response.status_code == 204
    assert chave(cenario.midias[0]) in cenario.objetos
    assert database.tbl_historico.find_one({"_id": historico["_id"]}) == historico


def test_ct39_mesmo_public_id_em_outro_resource_type_nao_e_o_mesmo_arquivo(client, headers, database, cenario):
    # Preparação
    outro = database.tbl_avancos.insert_one({"estado": "publicado"}).inserted_id
    ref = {**cenario.midias[0]["referencia_externa"], "resource_type": "video"}
    outra = cenario.adicionar(tipo="video", dono=outro, referencia=ref)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204
    assert chave(cenario.midias[0]) not in cenario.objetos
    assert chave(outra) in cenario.objetos


@pytest.mark.parametrize("alteracoes", [{"estado": "publicado"}, {"estado": "rascunho", "publicacao": {}}, {"estado": "outro"}])
def test_ct39_nao_exclui_publicados_ou_estados_invalidos(client, headers, database, cenario, alteracoes):
    # Preparação
    database.tbl_avancos.update_one({"_id": cenario.avanco["_id"]}, {"$set": alteracoes})
    before = snapshot(database)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 409
    assert snapshot(database) == before
    cenario.destroy.assert_not_called()


@pytest.mark.parametrize("identificador,status", [("invalido", 400), ("507f1f77bcf86cd799439099", 404)])
def test_ct39_id_invalido_ou_ausente(client, headers, database, identificador, status):
    # Preparação
    before = snapshot(database)
    # Execução
    response = client.delete(BASE + identificador, headers=headers)
    # Verificação
    assert response.status_code == status
    assert snapshot(database) == before


@pytest.mark.parametrize("tipo", ["ausente", "expirado", "revogado", "inativa"])
def test_ct03_exclusao_exige_sessao(app, client, headers, emitir_headers, account, database, cenario, tipo):
    # Preparação
    autorizacao = headers
    if tipo == "ausente":
        autorizacao = {}
    elif tipo == "expirado":
        autorizacao = emitir_headers(expirado=True)
    elif tipo == "revogado":
        with app.app_context():
            claims = decode_token(headers["Authorization"].split()[1])
        database.tbl_sessoes_revogadas.insert_one({"_id": claims["sessao_id"]})
    else:
        database.tbl_construtora.update_one({"_id": account["_id"]}, {"$set": {"ativo": False}})
    before = snapshot(database)
    # Execução
    response = client.delete(cenario.path, headers=autorizacao)
    # Verificação
    assert response.status_code == 401
    assert snapshot(database) == before
    cenario.destroy.assert_not_called()


def test_ct39_falha_provedor_registra_pendencia_e_repeticao_conclui(client, headers, database, cenario):
    # Preparação
    cenario.falhas.update(cenario.objetos)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação da pendência persistida
    assert response.status_code == 503
    assert response.get_json()["codigo"] == "LIMPEZA_PENDENTE"
    assert response.get_json()["pendentes"] == 3
    salvo = database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]})
    assert salvo["estado"] == "exclusao_pendente"
    assert len(salvo["exclusao"]["pendentes"]) == 3
    assert salvo["exclusao"]["token"] is None
    assert "privado" not in response.get_data(as_text=True)
    assert "public_id" not in response.get_data(as_text=True)
    assert client.get(cenario.path + "/midias", headers=headers).status_code == 404
    assert client.post(cenario.path + "/publicacoes", headers=headers).status_code == 409
    # Nova tentativa retoma a mesma operação.
    cenario.falhas.clear()
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos
    assert database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]}) is None


def test_ct39_limpeza_parcial_repete_somente_arquivo_pendente(client, headers, database, cenario):
    # Preparação
    cenario.falhas.add(chave(cenario.midias[0]))
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 503
    assert response.get_json()["pendentes"] == 1
    assert set(cenario.objetos) == {chave(cenario.midias[0])}
    cenario.falhas.clear()
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert cenario.destroy.call_count == 4


def test_ct39_timeout_apos_remocao_e_idempotente_na_retomada(client, headers, database, cenario):
    # Preparação
    falhou = False
    def remover_e_falhar(**opcoes):
        nonlocal falhou
        resultado = cenario.remover(**opcoes)
        if not falhou:
            falhou = True
            raise TimeoutError("resposta perdida")
        return resultado
    cenario.destroy.side_effect = remover_e_falhar
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 503
    assert not cenario.objetos
    cenario.destroy.side_effect = cenario.remover
    assert client.delete(cenario.path, headers=headers).status_code == 204


@pytest.mark.parametrize("metodo", ["iniciar_exclusao", "arquivo_tem_outras_referencias", "concluir_arquivo"])
def test_ct39_falha_banco_nunca_anuncia_sucesso(client, headers, database, cenario, metodo):
    # Preparação
    with patch("app.avancos.repository." + metodo, side_effect=PyMongoError("conexão privada")):
        # Execução
        response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 503
    assert "privada" not in response.get_data(as_text=True)
    assert database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]}) is not None
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos


@pytest.mark.parametrize("metodo", ["delete_many", "delete_one"])
def test_ct39_falha_finalizacao_banco_pode_ser_retomada(client, headers, database, cenario, metodo):
    # Preparação: falha depois de todos os arquivos exclusivos serem removidos.
    with patch.object(type(database.tbl_midias), metodo, side_effect=PyMongoError("falha fictícia")):
        # Execução
        response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 503
    assert not cenario.objetos
    salvo = database.tbl_avancos.find_one({"_id": cenario.avanco["_id"]})
    assert salvo["exclusao"]["pendentes"] == []
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert cenario.destroy.call_count == 3


@pytest.mark.parametrize("mudanca", ["publicacao", "revisao"])
def test_ct39_conflito_antes_da_reserva_nao_remove_arquivos(client, headers, database, cenario, monkeypatch, mudanca):
    # Preparação
    from app.avancos import repository
    iniciar = repository.iniciar_exclusao
    def mudar(documento, *args):
        atualizacao = {"$set": {"estado": "publicado", "publicacao": {"autor": "teste"}}} if mudanca == "publicacao" else {"$inc": {"revisao": 1}}
        database.tbl_avancos.update_one({"_id": documento["_id"]}, atualizacao)
        return iniciar(documento, *args)
    monkeypatch.setattr(repository, "iniciar_exclusao", mudar)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 409
    assert len(cenario.objetos) == 3
    cenario.destroy.assert_not_called()


def test_ct39_requisicao_concorrente_nao_interfere_na_operacao(app, client, headers, cenario):
    # Preparação
    respostas = []
    def remover(**opcoes):
        if not respostas:
            respostas.append(app.test_client().delete(cenario.path, headers=headers).status_code)
        return cenario.remover(**opcoes)
    cenario.destroy.side_effect = remover
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 204
    assert respostas == [409]
    assert cenario.destroy.call_count == 3


def test_ct39_bloqueio_expirado_permite_retomar_apos_queda(client, headers, database, cenario):
    # Preparação
    cenario.falhas.update(cenario.objetos)
    assert client.delete(cenario.path, headers=headers).status_code == 503
    cenario.falhas.clear()
    database.tbl_avancos.update_one({"_id": cenario.avanco["_id"]}, {"$set": {
        "exclusao.token": "processo-interrompido", "exclusao.ate": datetime(2030, 10, 20, 12, 5, tzinfo=timezone.utc)}})
    # Execução e verificação
    assert client.delete(cenario.path, headers=headers).status_code == 409
    with freeze_time("2030-10-20 12:06:00", ignore=["pymongo"]):
        assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos


def test_ct39_edicao_nao_pode_passar_pela_reserva(client, headers, database, cenario):
    # Preparação
    from app.avancos.revisoes import registrar_alteracao, ConflitoRascunho
    def remover(**opcoes):
        with pytest.raises(ConflitoRascunho):
            registrar_alteracao(cenario.avanco, None)
        return cenario.remover(**opcoes)
    cenario.destroy.side_effect = remover
    # Execução e verificação
    assert client.delete(cenario.path, headers=headers).status_code == 204


def test_ct39_midia_adicionada_durante_limpeza_nao_e_descartada_sem_remover_arquivo(client, headers, database, cenario):
    # Preparação: simula um escritor que não respeitou o protocolo de revisão.
    adicionadas = []
    def remover(**opcoes):
        if not adicionadas:
            adicionadas.append(cenario.adicionar())
        return cenario.remover(**opcoes)
    cenario.destroy.side_effect = remover
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 503
    assert chave(adicionadas[0]) in cenario.objetos
    cenario.destroy.side_effect = cenario.remover
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos


def test_ct39_referencia_invalida_preserva_rascunho(client, headers, database, cenario):
    # Preparação
    database.tbl_midias.update_one({"_id": cenario.midias[0]["_id"]}, {"$set": {"referencia_externa": "legado"}})
    before = snapshot(database)
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 422
    assert snapshot(database) == before
    cenario.destroy.assert_not_called()


def test_ct39_dois_rascunhos_em_exclusao_nao_deixam_arquivo_compartilhado_orfao(client, headers, database, cenario):
    # Preparação
    from app.avancos.midias import preparar_limpeza
    outro = database.tbl_avancos.insert_one({"estado": "rascunho", "marco_id": cenario.avanco["marco_id"]}).inserted_id
    midia = cenario.adicionar(dono=outro, referencia=cenario.midias[0]["referencia_externa"])
    arquivos = preparar_limpeza([midia])
    database.tbl_avancos.update_one({"_id": outro}, {"$set": {"estado": "exclusao_pendente", "exclusao": {
        "arquivos": arquivos, "pendentes": arquivos, "token": None, "ate": None, "tentativas": 1}}})
    # Execução
    primeiro = client.delete(cenario.path, headers=headers)
    segundo = client.delete(BASE + str(outro), headers=headers)
    # Verificação
    assert primeiro.status_code == segundo.status_code == 204
    assert not cenario.objetos
    assert database.tbl_avancos.count_documents({}) == 0


def test_ct39_repetir_exclusao_concluida_nao_remove_outros_arquivos(client, headers, cenario):
    # Preparação
    assert client.delete(cenario.path, headers=headers).status_code == 204
    chamadas = cenario.destroy.call_count
    # Execução
    response = client.delete(cenario.path, headers=headers)
    # Verificação
    assert response.status_code == 404
    assert cenario.destroy.call_count == chamadas


@pytest.mark.parametrize(
    "formato", [str, lambda valor: valor], ids=["texto", "ObjectId"]
)
def test_exclusao_preserva_acesso_a_midia_usada_em_publicacao(client, headers, database, cenario, formato):
    midia = cenario.midias[0]
    database.tbl_avancos.insert_one({
        "estado": "publicado",
        "publicacao": {"midias": [{"id": formato(midia["_id"])}]},
    })
    antes = snapshot(database)
    resposta = client.delete(cenario.path, headers=headers)
    assert resposta.status_code == 409
    assert snapshot(database) == antes
    assert client.get("/midias/" + str(midia["_id"]), headers=headers).status_code == 200
    cenario.destroy.assert_not_called()


def preparar_tarefa_antiga(database, cenario, *, compartilhada=False):
    midia = cenario.adicionar()
    database.tbl_midias.delete_one({"_id": midia["_id"]})
    database.tbl_limpezas_midias.insert_one({
        "_id": midia["_id"], "avanco_id": cenario.avanco["_id"], "midia": midia,
    })
    if compartilhada:
        outro = database.tbl_avancos.insert_one({"estado": "rascunho"}).inserted_id
        cenario.adicionar(dono=outro, referencia=midia["referencia_externa"])
    return midia


def test_exclusao_limpa_pendencias_de_edicoes_anteriores(client, headers, database, cenario):
    preparar_tarefa_antiga(database, cenario)
    resposta = client.delete(cenario.path, headers=headers)
    assert resposta.status_code == 204
    assert not cenario.objetos
    assert database.tbl_limpezas_midias.count_documents({"avanco_id": cenario.avanco["_id"]}) == 0
    assert cenario.destroy.call_count == 4


def test_falha_em_pendencia_antiga_impede_204_e_permite_retomada(client, headers, database, cenario):
    midia = preparar_tarefa_antiga(database, cenario)
    cenario.falhas.add(chave(midia))
    resposta = client.delete(cenario.path, headers=headers)
    assert resposta.status_code == 503
    assert resposta.get_json()["pendentes"] == 1
    assert database.tbl_limpezas_midias.find_one({"_id": midia["_id"]})
    cenario.falhas.clear()
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos
    assert database.tbl_limpezas_midias.count_documents({}) == 0


def test_pendencia_antiga_compartilhada_preserva_arquivo(client, headers, database, cenario):
    midia = preparar_tarefa_antiga(database, cenario, compartilhada=True)
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert set(cenario.objetos) == {chave(midia)}
    assert database.tbl_limpezas_midias.count_documents({}) == 0


def test_retomada_incorpora_tarefa_antiga_fora_do_diario(client, headers, database, cenario):
    cenario.falhas.update(cenario.objetos)
    assert client.delete(cenario.path, headers=headers).status_code == 503
    preparar_tarefa_antiga(database, cenario)
    cenario.falhas.clear()
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos
    assert database.tbl_limpezas_midias.count_documents({}) == 0


def test_tarefa_de_limpeza_nao_e_referencia_ativa(client, headers, database, cenario):
    midia = cenario.midias[0]
    database.tbl_limpezas_midias.insert_one({
        "_id": midia["_id"], "avanco_id": cenario.avanco["_id"], "midia": midia,
    })
    assert client.delete(cenario.path, headers=headers).status_code == 204
    assert not cenario.objetos
    assert cenario.destroy.call_count == 3
    assert database.tbl_limpezas_midias.count_documents({}) == 0
