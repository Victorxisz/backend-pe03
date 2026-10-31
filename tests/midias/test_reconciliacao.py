"""Recuperação de uploads após falhas, com provedor e banco simulados."""
from datetime import datetime
from unittest.mock import Mock

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support_midias import config, conteudos
from support_avancos import backend, transacao_local


def ref(letra='a'):
    return dict(provedor='cloudinary', public_id='pe03/evidencias/' + letra * 32,
                resource_type='image', delivery_type='authenticated', formato='png')


@pytest.fixture
def ambiente(app, database):
    from app.avancos.reconciliacao import ServicoReconciliacao
    storage = Mock()
    return ServicoReconciliacao(storage), storage


def operacao(database, chave='a' * 64, tipo='correcao', referencias=None):
    avanco = ObjectId()
    database.tbl_avancos.insert_one({'_id': avanco, 'estado': 'publicado'})
    database.tbl_uploads_pendentes.insert_one({
        '_id': chave, 'avanco_id': avanco, 'estado': 'pendente',
        'referencias': referencias if referencias is not None else [ref()],
        **({'tipo': tipo} if tipo else {}),
    })
    return avanco


@pytest.mark.parametrize('tamanho,tipo', [(32, None), (64, 'correcao'), (64, 'edicao')])
def test_recupera_atualizacao_sem_apagar_avanco(database, ambiente, tamanho, tipo):
    servico, storage = ambiente
    chave = 'a' * tamanho
    avanco = operacao(database, chave, tipo)
    assert servico.reconciliar(chave, aplicacao_parada=True) == 'limpa'
    storage.remover.assert_called_once_with(ref())
    assert database.tbl_avancos.find_one({'_id': avanco}) is not None
    assert servico.reconciliar(chave, aplicacao_parada=True) == 'limpa'
    assert storage.remover.call_count == 1


def test_exige_parada_sem_tocar_provedor(database, ambiente):
    servico, storage = ambiente
    operacao(database)
    with pytest.raises(ValueError, match='Pare a aplicação'):
        servico.reconciliar('a' * 64)
    storage.remover.assert_not_called()


@pytest.mark.parametrize('origem', ['midia', 'historico', 'outro_upload'])
def test_preserva_referencias_ativas_e_remove_so_orfas(database, ambiente, origem):
    servico, storage = ambiente
    operacao(database, referencias=[ref('a'), ref('b')])
    if origem == 'midia':
        database.tbl_midias.insert_one({'referencia_externa': ref('a')})
    elif origem == 'historico':
        database.tbl_avancos.insert_one({'correcoes': [{'antes': {'referencia': ref('a')}}]})
    else:
        database.tbl_uploads_pendentes.insert_one({'_id': 'c' * 64, 'estado': 'pendente', 'referencias': [ref('a')]})
    assert servico.reconciliar('a' * 64, aplicacao_parada=True) == 'limpa'
    storage.remover.assert_called_once_with(ref('b'))
    assert database.tbl_uploads_pendentes.find_one({'_id': 'a' * 64})['preservadas'] == [ref('a')]


def test_falha_provedor_permite_retomar(database, ambiente):
    from app.integracoes.armazenamento import ErroArmazenamento
    servico, storage = ambiente
    operacao(database, referencias=[ref('a'), ref('b')])
    storage.remover.side_effect = [None, ErroArmazenamento('fora do ar')]
    with pytest.raises(ErroArmazenamento):
        servico.reconciliar('a' * 64, aplicacao_parada=True)
    assert database.tbl_uploads_pendentes.find_one()['estado'] == 'pendente'
    storage.remover.side_effect = None
    assert servico.reconciliar('a' * 64, aplicacao_parada=True) == 'limpa'


def test_falha_ao_confirmar_limpeza_nao_perde_diario(database, ambiente, monkeypatch):
    servico, storage = ambiente
    operacao(database)
    original = database.tbl_uploads_pendentes.update_one
    monkeypatch.setattr(database.tbl_uploads_pendentes, 'update_one', Mock(side_effect=PyMongoError('falha')))
    with pytest.raises(PyMongoError):
        servico.reconciliar('a' * 64, aplicacao_parada=True)
    assert database.tbl_uploads_pendentes.find_one()['estado'] == 'pendente'
    monkeypatch.setattr(database.tbl_uploads_pendentes, 'update_one', original)
    assert servico.reconciliar('a' * 64, aplicacao_parada=True) == 'limpa'


def test_valida_lote_inteiro_antes_de_remover(database, ambiente):
    from app.avancos.midias import ErroMidia
    servico, storage = ambiente
    operacao(database, referencias=[ref(), {}])
    with pytest.raises(ErroMidia):
        servico.reconciliar('a' * 64, aplicacao_parada=True)
    storage.remover.assert_not_called()


def test_tarefas_de_midias_removidas_preservam_compartilhadas(database, ambiente):
    servico, storage = ambiente
    for letra in ['a', 'b']:
        midia = {'_id': ObjectId(), 'referencia_externa': ref(letra)}
        database.tbl_limpezas_midias.insert_one({'_id': midia['_id'], 'midia': midia})
    database.tbl_midias.insert_one({'referencia_externa': ref('b')})
    assert servico.limpar_removidas(aplicacao_parada=True) == 1
    storage.remover.assert_called_once_with(ref('a'))
    assert database.tbl_limpezas_midias.count_documents({}) == 1


def test_correcao_http_falha_e_reconciliacao_limpa_so_upload_novo(
    client, headers, database, backend, transacao_local, conteudos, monkeypatch,
):
    from io import BytesIO
    from app.avancos import repository
    from app.avancos.reconciliacao import reconciliar
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    avanco = database.tbl_avancos.insert_one({
        'estado': 'publicado', 'autor': 'original', 'data': '2030-01-01',
        'descricao': 'Antes', 'revisao': 1,
        'publicacao': {'autor': 'original', 'instante': datetime(2030, 1, 1),
                       'data': '2030-01-01', 'descricao': 'Antes', 'midias': []},
    }).inserted_id
    original = database.tbl_avancos.find_one({'_id': avanco})
    monkeypatch.setattr(repository, 'salvar_correcao_publicada', Mock(side_effect=PyMongoError('falha')))
    destroy = backend[2].side_effect
    backend[2].side_effect = RuntimeError('provider indisponivel')
    r = client.patch(f'/avancos/{avanco}', headers=headers,
                     data={'motivo': 'Nova foto', 'midias': (BytesIO(conteudos['png']), 'foto.png')})
    assert r.status_code == 503
    diario = database.tbl_uploads_pendentes.find_one()
    assert diario['tipo'] == 'correcao' and len(diario['_id']) == 64
    backend[2].side_effect = destroy
    assert reconciliar(diario['_id'], ArmazenamentoCloudinary(), aplicacao_parada=True) == 'limpa'
    assert not backend[0]
    assert database.tbl_avancos.find_one({'_id': avanco}) == original
