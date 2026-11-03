from bson import ObjectId
from flask_jwt_extended import create_access_token


def test_isolamento_de_obras_e_recursos(client, app, database, account, headers, obra):
    outra = ObjectId()
    database.tbl_construtora.insert_one({'_id': outra, 'ativo': True, 'email': 'outra@example.com'})
    with app.app_context():
        token = create_access_token(identity=str(outra), additional_claims={'tipo': 'construtora', 'sessao_id': 'outra-sessao'})
    outro_headers = {'Authorization': 'Bearer ' + token}
    propria, alheia, antiga = ObjectId(), ObjectId(), ObjectId()
    propria_bson = database.tbl_obras.insert_one({**obra, 'autor': account['_id']}).inserted_id
    for oid, autor in [(propria, str(account['_id'])), (alheia, str(outra)), (antiga, None)]:
        documento = {**obra, '_id': oid, 'nome': str(oid), 'estado': 'planejada'}
        if autor: documento['autor'] = autor
        database.tbl_obras.insert_one(documento)
    marco_proprio = database.tbl_marcos.insert_one({'obra_id': propria, 'nome': 'Marco próprio'}).inserted_id
    marco = database.tbl_marcos.insert_one({'obra_id': alheia, 'nome': 'Marco'}).inserted_id
    avanco = database.tbl_avancos.insert_one({'marco_id': marco}).inserted_id
    midia = database.tbl_midias.insert_one({'avanco_id': avanco}).inserted_id
    ocorrencia = database.tbl_ocorrencias.insert_one({'obra_id': alheia}).inserted_id
    evento = database.tbl_historico.insert_one({'alvo': {'tipo': 'marco', 'id': marco}}).inserted_id
    lista = client.get('/obras', headers=headers)
    assert lista.status_code == 200
    assert {o['id'] for o in lista.json['obras']} == {str(propria), str(propria_bson)}
    assert [o['id'] for o in client.get('/obras', headers=outro_headers).json['obras']] == [str(alheia)]
    for path in [f'/obras/{alheia}', f'/obras/{antiga}', f'/obras/{alheia}/marcos',
                 f'/marcos/{marco}/dependencias', f'/avancos/{avanco}', f'/avancos/{avanco}/versoes',
                 f'/midias/{midia}/conteudo', f'/ocorrencias/{ocorrencia}', f'/mudancas/{evento}',
                 f'/obras/{alheia}/mudancas', f'/obras/{alheia}/previa',
                   f'/obras/{alheia}/imagem-projeto/{ObjectId()}/conteudo',
                 f'/avancos/{avanco}/publicacoes', f'/avancos/{avanco}/midias',
                 f'/avancos/{avanco}/exclusao', f'/ocorrencias/{ocorrencia}/aceitacoes',
                 f'/ocorrencias/{ocorrencia}/exclusao', f'/trabalhadores/obra/{alheia}/']:
        assert client.get(path, headers=headers).status_code == 404, path
    for path, body in [(f'/obras/{alheia}/marcos', {'nome': 'Intruso'}),
                       (f'/obras/{alheia}/mudancas', {}), (f'/obras/{alheia}/ocorrencias', {}),
                       (f'/avancos/{avanco}/publicacoes', {})]:
        assert client.post(path, headers=headers, json=body).status_code == 404, path
    assert client.post(f'/marcos/{marco_proprio}/dependencias', headers=headers, json={'depende_de_id': str(marco)}).status_code == 404
    assert client.patch(f'/obras/{alheia}', headers=headers, json={'nome': 'alterado'}).status_code == 404
    assert client.patch(f'/avancos/{avanco}', headers=headers, json={'descricao': 'alterada'}).status_code == 404
    assert client.patch(f'/ocorrencias/{ocorrencia}', headers=headers, json={'titulo': 'alterado'}).status_code == 404
    for path in (f'/obras/{alheia}', f'/obras/{alheia}/imagem-projeto', f'/marcos/{marco}',
                 f'/avancos/{avanco}', f'/ocorrencias/{ocorrencia}'):
        assert client.delete(path, headers=headers, json={'confirmar': True}).status_code == 404, path
    assert client.put(f'/obras/{alheia}/imagem-projeto', headers=headers).status_code == 404
    assert client.post(f'/ocorrencias/{ocorrencia}/aceitacoes', headers=headers, json={'justificativa': 'Intrusão'}).status_code == 404
    assert database.tbl_obras.find_one({'_id': alheia})['nome'] == str(alheia)
    assert client.get(f'/obras/{alheia}', headers=outro_headers).status_code == 200
    assert client.get(f'/obras/{propria}', headers=outro_headers).status_code == 404
    assert client.get(f'/marcos/{marco_proprio}/dependencias', headers=outro_headers).status_code == 404
    assert client.get(f'/obras/{antiga}', headers=outro_headers).status_code == 404

def test_retomada_de_exclusao_exige_mesmo_proprietario(client, app, database, account, headers, monkeypatch):
    from app.obras import exclusoes
    outra = ObjectId()
    database.tbl_construtora.insert_one({'_id': outra, 'ativo': True, 'email': 'outra@example.com'})
    with app.app_context():
        token = create_access_token(identity=str(outra), additional_claims={'tipo': 'construtora', 'sessao_id': 'outra-sessao'})
    outro_headers = {'Authorization': 'Bearer ' + token}
    obra = ObjectId()
    database.tbl_exclusoes_pendentes.insert_one({'alvo': {'tipo': 'obra', 'id': obra}, 'proprietario_id': str(account['_id'])})
    chamadas = []
    monkeypatch.setattr(exclusoes, 'retomar_pendencia', lambda tipo, identificador: chamadas.append((tipo, identificador)) or True)
    assert client.delete(f'/obras/{obra}', headers=outro_headers).status_code == 404
    assert chamadas == []
    assert client.delete(f'/obras/{obra}', headers=headers).status_code == 204
    assert chamadas == [('obra', obra)]
    antigo = ObjectId()
    database.tbl_exclusoes_pendentes.insert_one({'alvo': {'tipo': 'obra', 'id': antigo}})
    assert client.delete(f'/obras/{antigo}', headers=headers).status_code == 404
    assert chamadas == [('obra', obra)]

def test_trabalhadores_de_outra_conta_e_sem_dono_nao_sao_expostos(client, database, account, headers):
    outra = ObjectId()
    obra = database.tbl_obras.insert_one({'autor': str(account['_id'])}).inserted_id
    proprio = database.tbl_trabalhadores.insert_one({'nome': 'Pedreiro próprio', 'cargo': 'pedreiro', 'obras': [str(obra)], 'construtora_id': str(account['_id'])}).inserted_id
    alheio = database.tbl_trabalhadores.insert_one({'nome': 'Pedreiro alheio', 'cargo': 'pedreiro', 'obras': [str(obra)], 'construtora_id': str(outra)}).inserted_id
    antigo = database.tbl_trabalhadores.insert_one({'nome': 'Pedreiro antigo', 'cargo': 'pedreiro', 'obras': [str(obra)]}).inserted_id
    resposta = client.get('/trabalhadores/cargo/pedreiro/', headers=headers)
    assert resposta.status_code == 200
    assert [item['id'] for item in resposta.json] == [str(proprio)]
    for pessoa in (alheio, antigo):
        rota = f'/trabalhadores/{pessoa}/'
        assert client.get(rota, headers=headers).status_code == 404
        assert client.patch(rota, headers=headers, json={'nome': 'Invadido'}).status_code == 404
        assert client.delete(rota, headers=headers).status_code == 404
    assert database.tbl_trabalhadores.count_documents({}) == 3
