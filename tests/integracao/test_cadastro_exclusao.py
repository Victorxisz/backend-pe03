"""Cadastro de avanços: cenários separados por responsabilidade."""

import pytest
from bson import ObjectId

from support import isolated_app, snapshot
from support_midias import config, conteudos


from support_avancos import backend, transacao_local, marco, dados

def test_reconciliacao_nao_remove_midia_de_avanco_existente(
    app, database, backend, marco
):
    # Preparação
    from app.avancos.reconciliacao import reconciliar
    from app.integracoes.armazenamento import ArmazenamentoCloudinary

    avanco_id = database.tbl_avancos.insert_one({"marco_id": marco}).inserted_id
    operacao_id = "a" * 64
    database.tbl_uploads_pendentes.insert_one(
        {
            "_id": operacao_id,
            "estado": "pendente",
            "avanco_id": avanco_id,
            "referencias": [{}],
        }
    )

    # Execução e verificação
    with pytest.raises(ValueError, match="Avanço encontrado"):
        reconciliar(operacao_id, ArmazenamentoCloudinary(), aplicacao_parada=True)
    backend[2].assert_not_called()
    assert database.tbl_uploads_pendentes.find_one()["estado"] == "pendente"


def test_integracao_criacao_exclusao_remove_midia_apesar_do_diario(client, headers, database, marco, backend, conteudos, transacao_local):
    # Preparação e execução
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    resposta = client.delete(criado.headers["Location"], headers=headers)

    # Verificação
    assert resposta.status_code == 204
    assert database.tbl_avancos.count_documents({}) == 0
    assert database.tbl_midias.count_documents({}) == 0
    assert not backend[0]
    backend[2].assert_called_once()


def test_avanco_com_exclusao_pendente_nao_aparece_nas_consultas(client, headers, database, marco, backend, conteudos, transacao_local):
    # Preparação
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    database.tbl_avancos.update_one({"_id": ObjectId(criado.get_json()["id"])}, {"$set": {"estado": "exclusao_pendente"}})

    # Execução
    detalhe = client.get(criado.headers["Location"], headers=headers)
    lista = client.get(f"/marcos/{marco}/avancos", headers=headers)

    # Verificação
    assert detalhe.status_code == 404
    assert lista.status_code == 200 and lista.get_json() == []


def test_exclusao_preserva_arquivo_referenciado_por_upload_pendente(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    referencia = database.tbl_midias.find_one()["referencia_externa"]
    database.tbl_uploads_pendentes.insert_one({
        "_id": "b" * 64, "avanco_id": ObjectId(), "estado": "pendente", "referencias": [referencia]
    })

    # Execução
    resposta = client.delete(criado.headers["Location"], headers=headers)

    # Verificação
    assert resposta.status_code == 204
    assert referencia["public_id"] in backend[0]
    backend[2].assert_not_called()


def test_limpeza_considera_historico_mas_ignora_diario_concluido(
    client, headers, database, marco, backend, conteudos, transacao_local
):
    # Preparação
    from app.avancos import repository

    criado = client.post(f"/marcos/{marco}/avancos", headers=headers, data=dados(conteudos["png"]))
    assert criado.status_code == 201
    midia = database.tbl_midias.find_one()
    referencia = midia["referencia_externa"]
    database.tbl_midias.delete_one({"_id": midia["_id"]})
    historico = database.tbl_versoes.insert_one({"anterior": {"referencia_externa": referencia}})

    # Execução e verificação
    assert repository.referencia_em_uso(referencia)
    database.tbl_versoes.delete_one({"_id": historico.inserted_id})
    assert not repository.referencia_em_uso(referencia)
