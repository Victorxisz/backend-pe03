"""Opt-in: fluxo HTTP com Atlas e Cloudinary reais, em coleções temporárias."""
import os
from io import BytesIO
from uuid import uuid4

import pytest
from bson import ObjectId
from flask_jwt_extended import create_access_token

from support import isolated_app
from support_midias import conteudos


@pytest.mark.atlas
@pytest.mark.cloudinary
def test_cadastro_edicao_publicacao_correcao_e_reinicio(app, database, conteudos, monkeypatch):
    if os.getenv('RUN_CLOUDINARY_TESTS') != '1':
        pytest.skip('Exige RUN_CLOUDINARY_TESTS=1 e credenciais TEST_CLOUDINARY_*')
    monkeypatch.setenv('CONSTRUTORA_ID', '')
    app.config['CONSTRUTORA_ID'] = ''
    for nome in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
        valor = os.getenv('TEST_' + nome)
        if not valor:
            pytest.fail('Configure TEST_' + nome, pytrace=False)
        monkeypatch.setenv(nome, valor)
    monkeypatch.setenv('CLOUDINARY_FOLDER', 'pe03/testes-fluxo-' + uuid4().hex)
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    storage = ArmazenamentoCloudinary()
    conta, obra, marco = ObjectId(), ObjectId(), ObjectId()
    database.tbl_construtora.insert_one({'_id': conta, 'ativo': True, 'email': 'teste@example.com'})
    database.tbl_obras.insert_one({'_id': obra, 'nome': 'Obra temporária'})
    database.tbl_marcos.insert_one({'_id': marco, 'obra_id': obra, 'nome': 'Marco temporário'})
    with app.app_context():
        token = create_access_token(identity=str(conta), additional_claims={
            'tipo': 'construtora', 'sessao_id': uuid4().hex})
    headers = {'Authorization': 'Bearer ' + token, 'Idempotency-Key': uuid4().hex}
    refs = []
    try:
        with app.test_client() as client:
            def formulario():
                return {'data':'2026-10-30', 'descricao':'Teste temporário',
                        'midias':[(BytesIO(v), 'arquivo.' + ext) for ext, v in conteudos.items()]}
            r = client.post(f'/marcos/{marco}/avancos', headers=headers, data=formulario())
            assert r.status_code == 201, r.json
            local, recurso = r.headers['Location'], r.json
            assert client.post(f'/marcos/{marco}/avancos', headers=headers, data=formulario()).json == recurso
            assert database.tbl_avancos.count_documents({}) == 1
            refs.extend(m['referencia_externa'] for m in database.tbl_midias.find())
            assert client.patch(local, headers=headers, data={
                'descricao':'Edição do rascunho', 'midias':(BytesIO(conteudos['png']), 'nova.png'),
            }).status_code == 200
            refs.extend(m['referencia_externa'] for m in database.tbl_midias.find()
                        if m['referencia_externa'] not in refs)
        with isolated_app(database) as nova_app:
            with nova_app.test_client() as client:
                consultado = client.get(local, headers=headers)
                assert consultado.status_code == 200 and len(consultado.json['midias']) == 5
                for midia in consultado.json['midias']:
                    assert client.get(midia['conteudo'], headers=headers).status_code == 200
                    assert client.get(midia['conteudo']).status_code == 401
                assert client.post(local + '/publicacoes', headers=headers).status_code == 201
                r = client.patch(local, headers=headers, data={
                    'motivo':'Teste de correção', 'descricao':'Versão corrigida',
                    'midias':(BytesIO(conteudos['png']), 'correcao.png'),
                })
                assert r.status_code == 200, r.json
                assert len(r.json['versoes']) == 2
                assert r.json['versoes'][-1]['conteudo']['descricao'] == 'Versão corrigida'
                assert client.get(r.json['versoes'][-1]['conteudo']['midias'][-1]['conteudo'], headers=headers).data == conteudos['png']
                assert database.tbl_uploads_pendentes.count_documents({'estado':'pendente'}) == 0
                # Um segundo rascunho valida a exclusão HTTP completa.
                r = client.post(f'/marcos/{marco}/avancos', headers={**headers, 'Idempotency-Key':uuid4().hex},
                    data={'data':'2026-10-30', 'descricao':'Excluir', 'midias':(BytesIO(conteudos['png']), 'excluir.png')})
                assert r.status_code == 201, r.json
                avanco_id = ObjectId(r.json['id'])
                exclusiva = database.tbl_midias.find_one({'avanco_id':avanco_id})['referencia_externa']
                refs.append(exclusiva)
                assert client.delete(r.headers['Location'], headers=headers).status_code == 204
                assert not storage.verificar_disponibilidade(exclusiva)
    finally:
        refs.extend(m['referencia_externa'] for m in database.tbl_midias.find()
                    if m['referencia_externa'] not in refs)
        for diario in database.tbl_uploads_pendentes.find():
            refs.extend(r for r in diario.get('referencias', []) if r not in refs)
        for referencia in refs:
            storage.remover(referencia)
            assert not storage.verificar_disponibilidade(referencia)
