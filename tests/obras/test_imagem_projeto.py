"""Perspectiva da obra com Cloudinary simulado e vínculos persistidos no banco isolado."""
from io import BytesIO
import json
from unittest.mock import patch

from bson import ObjectId
import pytest
from pymongo.errors import NetworkTimeout, WriteError
from werkzeug.datastructures import MultiDict

from support_avancos import backend, transacao_local
from support_midias import config, conteudos
from support import isolated_app


def criar(client, headers, obra, conteudos):
    return client.post('/obras', headers=headers, data={
        'cadastro': json.dumps(obra), 'imagem_projeto': (BytesIO(conteudos['png']), 'perspectiva.png')})


def substituir(client, headers, id, conteudos, atual=''):
    return client.put(f'/obras/{id}/imagem-projeto', headers=headers, data={
        'imagem_atual': atual, 'imagem_projeto': (BytesIO(conteudos['jpg']), 'fachada.jpg')})


def test_cadastro_imagem_privada_releitura_e_nova_aplicacao(client, app, headers, obra, conteudos, backend, database):
    response = criar(client, headers, obra, conteudos)
    assert response.status_code == 201
    body = response.json
    imagem = body['imagem_projeto']
    assert imagem['mime'] == 'image/png'
    assert set(imagem) == {'id', 'nome', 'mime', 'tamanho', 'conteudo'}
    assert 'cloudinary' not in json.dumps(imagem)
    assert client.get('/obras/' + body['id'], headers=headers).json['imagem_projeto'] == imagem
    assert client.get('/obras', headers=headers).json['obras'][0]['imagem_projeto'] == imagem
    conteudo = client.get(imagem['conteudo'], headers=headers)
    assert conteudo.status_code == 200 and conteudo.data == conteudos['png']
    assert conteudo.mimetype == 'image/png'
    assert 'no-store' in conteudo.headers['Cache-Control']
    assert conteudo.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get(imagem['conteudo']).status_code == 401
    assert len(backend[0]) == 1
    # Nova instância Flask: os vínculos não dependem de estado em memória do serviço.
    with isolated_app(database) as fresh:
        with fresh.test_client() as novo:
            assert novo.get('/obras/' + body['id'], headers=headers).json['imagem_projeto'] == imagem


def test_substituir_remover_preserva_cadastro_e_impede_sobrescrita_antiga(client, headers, obra, conteudos, backend, database):
    criada = criar(client, headers, obra, conteudos).json
    id, antiga = criada['id'], criada['imagem_projeto']
    original = database.tbl_obras.find_one({'_id': ObjectId(id)})
    nova = substituir(client, headers, id, conteudos, antiga['id'])
    assert nova.status_code == 200 and not nova.json['limpeza_pendente']
    imagem = nova.json['imagem_projeto']
    assert imagem['id'] != antiga['id']
    assert len(backend[0]) == 1
    salvo = database.tbl_obras.find_one({'_id': ObjectId(id)})
    assert {k: v for k, v in salvo.items() if k != 'imagem_projeto'} == {k: v for k, v in original.items() if k != 'imagem_projeto'}
    assert client.get(antiga['conteudo'], headers=headers).status_code == 404
    assert substituir(client, headers, id, conteudos, antiga['id']).status_code == 409
    assert client.delete(f'/obras/{id}/imagem-projeto', headers=headers, json={'imagem_atual': antiga['id']}).status_code == 409
    removida = client.delete(f'/obras/{id}/imagem-projeto', headers=headers, json={'imagem_atual': imagem['id']})
    assert removida.status_code == 200 and removida.json['imagem_projeto'] is None
    assert not backend[0]
    assert 'imagem_projeto' not in client.get('/obras/' + id, headers=headers).json


@pytest.mark.parametrize('conteudo,nome', [(b'<svg></svg>', 'fachada.png'), (b'\x89PNG\r\n\x1a\nquebrada', 'foto.png')])
def test_rejeita_imagem_falsa_antes_do_upload(client, headers, obra, backend, conteudo, nome, database):
    result = client.post('/obras', headers=headers, data={'cadastro': json.dumps(obra), 'imagem_projeto': (BytesIO(conteudo), nome)})
    assert result.status_code == 422
    assert database.tbl_obras.count_documents({}) == 0
    assert not backend[0]
    backend[1].assert_not_called()


def test_rejeita_pdf_limite_repeticoes_e_cadastro_invalido(client, headers, obra, conteudos, backend, database, monkeypatch):
    result = client.post('/obras', headers=headers, data={'cadastro': json.dumps(obra), 'imagem_projeto': (BytesIO(conteudos['pdf']), 'arquivo.pdf')})
    assert result.status_code == 422
    invalidos = [
        MultiDict([('cadastro', json.dumps(obra)), ('cadastro', json.dumps(obra)), ('imagem_projeto', (BytesIO(conteudos['png']), 'foto.png'))]),
        {'cadastro': json.dumps({**obra, 'nome': '  '}), 'imagem_projeto': (BytesIO(conteudos['png']), 'foto.png')},
        {'cadastro': json.dumps({**obra, 'imagem_projeto': 'https://example.test/foto.png'}), 'imagem_projeto': (BytesIO(conteudos['png']), 'foto.png')},
    ]
    for dados in invalidos:
        assert client.post('/obras', headers=headers, data=dados).status_code == 422
    monkeypatch.setenv('MIDIA_FOTO_MAX_BYTES', '20')
    assert criar(client, headers, obra, conteudos).status_code == 413
    assert not backend[0]
    assert database.tbl_obras.count_documents({}) == 0


def test_rejeicao_confirmada_compensa_upload(client, headers, obra, conteudos, backend, database):
    from app.obras import repository
    with patch.object(repository, 'salvar_obra', side_effect=WriteError('rejeição')):
        result = criar(client, headers, obra, conteudos)
    assert result.status_code == 500
    assert not backend[0]
    assert database.tbl_obras.count_documents({}) == 0
    assert database.tbl_uploads_pendentes.count_documents({'estado': 'pendente'}) == 0


def test_resposta_perdida_preserva_imagem_e_reconciliacao(client, headers, obra, conteudos, backend, database):
    from app.obras import repository
    from app.avancos.reconciliacao import ServicoReconciliacao
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    salvar = repository.salvar_obra

    def timeout(documento):
        salvar(documento)
        raise NetworkTimeout('confirmação perdida')
    with patch.object(repository, 'salvar_obra', side_effect=timeout):
        result = criar(client, headers, obra, conteudos)
    assert result.status_code == 503
    assert database.tbl_obras.count_documents({}) == 1
    operacao = database.tbl_uploads_pendentes.find_one({'estado': 'pendente'})
    servico = ServicoReconciliacao(ArmazenamentoCloudinary())
    assert servico.reconciliar(operacao['_id'], aplicacao_parada=True) == 'limpa'
    assert len(backend[0]) == 1
    imagem = client.get('/obras', headers=headers).json['obras'][0]['imagem_projeto']
    assert client.get(imagem['conteudo'], headers=headers).data == conteudos['png']


def test_limpeza_pendente_tem_retomada_sem_apagar_imagem_atual(client, headers, obra, conteudos, backend, database):
    from app.avancos.reconciliacao import ServicoReconciliacao
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    criada = criar(client, headers, obra, conteudos).json
    destruir = backend[2].side_effect
    backend[2].side_effect = RuntimeError('provedor indisponível')
    result = substituir(client, headers, criada['id'], conteudos, criada['imagem_projeto']['id'])
    assert result.status_code == 200 and result.json['limpeza_pendente']
    assert len(backend[0]) == 2
    assert database.tbl_limpezas_midias.count_documents({}) == 1
    backend[2].side_effect = destruir
    assert ServicoReconciliacao(ArmazenamentoCloudinary()).limpar_removidas(aplicacao_parada=True) == 1
    assert len(backend[0]) == 1
    assert client.get(result.json['imagem_projeto']['conteudo'], headers=headers).data == conteudos['jpg']


def test_exclusao_da_obra_remove_imagem_e_diarios(client, headers, obra, conteudos, backend, database, transacao_local):
    criada = criar(client, headers, obra, conteudos).json
    result = client.delete('/obras/' + criada['id'], headers=headers, json={'confirmar': True})
    assert result.status_code == 204, result.json
    assert not backend[0]
    assert database.tbl_uploads_pendentes.count_documents({'obra_id': ObjectId(criada['id'])}) == 0
    assert client.get(criada['imagem_projeto']['conteudo'], headers=headers).status_code == 404


def test_imagem_inacessivel_a_outra_conta(client, headers, obra, conteudos, backend, database, emitir_headers):
    criada = criar(client, headers, obra, conteudos).json
    outra = ObjectId()
    database.tbl_construtora.insert_one({'_id': outra, 'nome': 'Outra', 'ativo': True})
    auth = emitir_headers(identidade=str(outra))
    assert client.get(criada['imagem_projeto']['conteudo'], headers=auth).status_code == 404
    assert substituir(client, auth, criada['id'], conteudos, criada['imagem_projeto']['id']).status_code == 404
    assert client.delete(f"/obras/{criada['id']}/imagem-projeto", headers=auth, json={'imagem_atual': criada['imagem_projeto']['id']}).status_code == 404
