"""Opt-in: HTTP + transação Atlas + arquivos Cloudinary reais e temporários."""
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
def test_fluxo_real_com_reinicio(app, database, conteudos, monkeypatch):
    if os.getenv('RUN_CLOUDINARY_TESTS') != '1':
        pytest.skip('Exige RUN_CLOUDINARY_TESTS=1 e credenciais TEST_CLOUDINARY_*')
    for nome in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'):
        valor = os.getenv('TEST_' + nome)
        if not valor:
            pytest.fail('Configure TEST_' + nome, pytrace=False)
        monkeypatch.setenv(nome, valor)
    monkeypatch.setenv('CLOUDINARY_FOLDER', 'pe03/testes-fluxo-' + uuid4().hex)
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    storage = ArmazenamentoCloudinary()
    obra, marco, autor = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_one({'_id': obra})
    database.tbl_marcos.insert_one({'_id': marco, 'obra_id': obra})
    database.tbl_construtora.insert_one({'_id': autor, 'ativo': True, 'email': 'fluxo@example.com'})
    with app.app_context():
        token = create_access_token(identity=str(autor), additional_claims={
            'tipo': 'construtora', 'sessao_id': uuid4().hex})
    headers = {'Authorization': 'Bearer ' + token}
    try:
        with app.test_client() as client:
            resposta = client.post('/avancos', headers=headers, data={
                'marco_id': str(marco), 'data': '2026-10-30', 'descricao': 'Teste temporário',
                'midias': [(BytesIO(v), 'teste.' + ext) for ext, v in conteudos.items()],
            })
            assert resposta.status_code == 201, resposta.json
            local = resposta.headers['Location']
            recurso = resposta.json
            assert len(recurso['midias']) == 4
            referencias = [m['referencia_externa'] for m in database.tbl_midias.find()]
        # Nova aplicação, mesmas coleções temporárias, sem usar dados em memória.
        with isolated_app(database) as nova_app:
            with nova_app.test_client() as client:
                assert client.get(local, headers=headers).json == recurso
                for m, original in zip(recurso['midias'], conteudos.values()):
                    assert client.get(m['conteudo'], headers=headers).data == original
                    assert client.get(m['conteudo']).status_code == 401
                assert client.delete(local, headers=headers).status_code == 204
                assert client.get(local, headers=headers).status_code == 404
        assert database.tbl_midias.count_documents({}) == 0
        for ref in referencias:
            assert not storage.verificar_disponibilidade(ref)
    finally:
        # Falhas intermediárias também tentam remover os objetos desta execução.
        for m in database.tbl_midias.find():
            storage.remover(m['referencia_externa'])
