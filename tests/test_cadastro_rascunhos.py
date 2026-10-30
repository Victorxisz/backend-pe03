"""Cadastro HTTP com mídia: rede simulada, transação local com rollback simulado."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError
from support_midias import config, conteudos
from test_edicao_rascunhos import transacao_local, camadas


@pytest.fixture
def cenario(transacao_local, camadas, database, config, monkeypatch):
    from app.avancos import midias
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    obra, marco = ObjectId(), ObjectId()
    database.tbl_obras.insert_one({'_id': obra})
    database.tbl_marcos.insert_one({'_id': marco, 'obra_id': obra})
    remotos = {}
    storage = Mock(config=config)
    def enviar(f):
        ref = dict(provedor='cloudinary', public_id=config.pasta + '/' + uuid4().hex,
                   resource_type={'foto':'image','video':'video','documento':'raw'}[f.tipo],
                   delivery_type='authenticated', formato=f.formato)
        remotos[ref['public_id']] = f.conteudo
        return dict(tipo=f.tipo, nome=f.nome, mime=f.mime, tamanho=f.tamanho, referencia_externa=ref)
    storage.enviar.side_effect = enviar
    storage.remover.side_effect = lambda ref: remotos.pop(ref['public_id'], None)
    servico = midias.ServicoMidias(storage)
    monkeypatch.setattr(midias, 'ServicoMidias', lambda: servico)
    monkeypatch.setattr(ArmazenamentoCloudinary, 'obter_conteudo', lambda self, ref, size: remotos[ref['public_id']])
    monkeypatch.setattr(ArmazenamentoCloudinary, 'remover', lambda self, ref: storage.remover(ref))
    for k in ('CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET'):
        monkeypatch.setenv(k, 'ficticio')
    return SimpleNamespace(marco=marco, obra=obra, storage=storage, remotos=remotos)


def dados(cenario, conteudos, ext='png', **extra):
    return dict(marco_id=str(cenario.marco), data='2030-10-19', descricao=' Concretagem ',
                midias=(BytesIO(conteudos[ext]), 'evidencia.' + ext), **extra)


@pytest.mark.parametrize('ext', ['jpg','png','mp4','pdf'])
def test_cadastro_consulta_e_conteudo(client, headers, account, database, cenario, conteudos, ext):
    r = client.post('/avancos', headers=headers, data=dados(cenario, conteudos, ext))
    assert r.status_code == 201, r.json
    p = r.json
    assert p['autor'] == str(account['_id']) and p['estado'] == 'rascunho'
    assert p['descricao'] == 'Concretagem' and p['revisao'] == 0
    assert client.get(r.headers['Location'], headers=headers).json == p
    assert client.get(p['midias'][0]['conteudo'], headers=headers).data == conteudos[ext]
    assert client.get(p['midias'][0]['conteudo']).status_code == 401
    assert 'public_id' not in r.text and 'referencia_externa' not in r.text
    assert database.tbl_avancos.count_documents({}) == database.tbl_midias.count_documents({}) == 1


@pytest.mark.parametrize('campo,valor', [('descricao',' '), ('data','errada'), ('marco_id','invalido'), ('autor','forjado')])
def test_dados_invalidos_sem_upload(client, headers, cenario, conteudos, campo, valor):
    d = dados(cenario, conteudos)
    d[campo] = valor
    assert client.post('/avancos', headers=headers, data=d).status_code == 422
    cenario.storage.enviar.assert_not_called()


def test_sem_sessao(client, cenario, conteudos):
    assert client.post('/avancos', data=dados(cenario, conteudos)).status_code == 401
    cenario.storage.enviar.assert_not_called()


def test_arquivo_invalido(client, headers, cenario, conteudos):
    d = dados(cenario, conteudos)
    d['midias'] = (BytesIO(b'nao e png'), 'foto.png')
    assert client.post('/avancos', headers=headers, data=d).status_code == 422
    cenario.storage.enviar.assert_not_called()


def test_sem_midia(client, headers, cenario, conteudos):
    d = dados(cenario, conteudos); d.pop('midias')
    assert client.post('/avancos', headers=headers, data=d,
                       content_type='multipart/form-data').status_code == 422


def test_falha_banco_desfaz_upload_e_transacao(client, headers, database, cenario, conteudos, monkeypatch):
    monkeypatch.setattr(database.tbl_midias, 'insert_many', Mock(side_effect=PyMongoError('falha')))
    assert client.post('/avancos', headers=headers, data=dados(cenario, conteudos)).status_code == 503
    assert not cenario.remotos
    assert database.tbl_avancos.count_documents({}) == database.tbl_midias.count_documents({}) == 0


def test_falha_limpeza_registra_pendencia(client, headers, database, cenario, conteudos, monkeypatch):
    from app.integracoes.armazenamento import ErroArmazenamento
    monkeypatch.setattr(database.tbl_midias, 'insert_many', Mock(side_effect=PyMongoError('falha')))
    cenario.storage.remover.side_effect = ErroArmazenamento('indisponivel')
    r = client.post('/avancos', headers=headers, data=dados(cenario, conteudos))
    assert r.status_code == 503 and r.json['codigo'] == 'LIMPEZA_PENDENTE'
    assert database.tbl_limpezas_midias.count_documents({}) == 1
    assert database.tbl_avancos.count_documents({}) == 0


def test_marco_removido_antes_transacao(client, headers, database, cenario, conteudos):
    original = cenario.storage.enviar.side_effect
    def enviar(f):
        result = original(f)
        database.tbl_marcos.delete_one({'_id': cenario.marco})
        return result
    cenario.storage.enviar.side_effect = enviar
    assert client.post('/avancos', headers=headers, data=dados(cenario, conteudos)).status_code == 409
    assert not cenario.remotos


def test_provedor_falha_sem_registro(client, headers, database, cenario, conteudos):
    from app.integracoes.armazenamento import ErroArmazenamento
    cenario.storage.enviar.side_effect = ErroArmazenamento('falha')
    assert client.post('/avancos', headers=headers, data=dados(cenario, conteudos)).status_code == 503
    assert database.tbl_avancos.count_documents({}) == database.tbl_midias.count_documents({}) == 0


def test_lote_e_exclusao_completa(client, headers, database, cenario, conteudos):
    d = dados(cenario, conteudos)
    d['midias'] = [(BytesIO(v), 'arquivo.' + ext) for ext, v in conteudos.items()]
    r = client.post('/avancos', headers=headers, data=d)
    assert r.status_code == 201 and len(r.json['midias']) == 4
    assert client.delete(r.headers['Location'], headers=headers).status_code == 204
    assert not cenario.remotos
    assert database.tbl_avancos.count_documents({}) == database.tbl_midias.count_documents({}) == 0
    assert client.get(r.headers['Location'], headers=headers).status_code == 404


def test_lote_invalido_nao_inicia_upload(client, headers, cenario, conteudos):
    d = dados(cenario, conteudos)
    d['midias'] = [(BytesIO(conteudos['png']), 'foto.png'), (BytesIO(b'errado'), 'doc.pdf')]
    assert client.post('/avancos', headers=headers, data=d).status_code == 422
    cenario.storage.enviar.assert_not_called()


def test_commit_incerto_preserva_arquivos(client, headers, database, cenario, conteudos, monkeypatch):
    from app.avancos import repository
    error = PyMongoError('commit incerto')
    error._add_error_label('UnknownTransactionCommitResult')
    monkeypatch.setattr(repository, 'salvar_criacao', Mock(side_effect=error))
    assert client.post('/avancos', headers=headers, data=dados(cenario, conteudos)).status_code == 503
    cenario.storage.remover.assert_not_called()


def test_consulta_apos_recarregar_app(client, headers, database, cenario, conteudos):
    from support import isolated_app
    r = client.post('/avancos', headers=headers, data=dados(cenario, conteudos))
    assert r.status_code == 201
    with isolated_app(database) as nova_app:
        with nova_app.test_client() as novo_cliente:
            assert novo_cliente.get(r.headers['Location'], headers=headers).json == r.json
