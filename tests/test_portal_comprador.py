from bson import ObjectId

def test_comprador_acessa_somente_obras_vinculadas(client, database, account, headers):
    a, b = ObjectId(), ObjectId()
    database.tbl_obras.insert_many([{'_id': a, 'autor': str(account['_id']), 'nome': 'A'}, {'_id': b, 'autor': str(account['_id']), 'nome': 'B'}])
    response = client.post('/compradores', headers=headers, json={'nome': 'Cliente', 'email': 'cliente@example.com', 'senha': 'senha123', 'obras': [str(a)]})
    assert response.status_code == 201
    response = client.post('/portal/login', json={'email': 'cliente@example.com', 'senha': 'senha123'})
    assert response.status_code == 200
    buyer = {'Authorization': 'Bearer ' + response.json['access_token']}
    assert [x['id'] for x in client.get('/portal/obras', headers=buyer).json['obras']] == [str(a)]
    assert client.get(f'/portal/obras/{a}', headers=buyer).status_code == 200
    assert client.get(f'/portal/obras/{b}', headers=buyer).status_code == 404
    assert client.get(f'/portal/obras/{b}/midias/{ObjectId()}', headers=buyer).status_code == 404
    assert client.get('/compradores', headers=buyer).status_code == 403

def test_construtora_nao_vincula_obra_de_outra(client, database, account, headers):
    outra = ObjectId()
    database.tbl_obras.insert_one({'_id': outra, 'autor': str(ObjectId()), 'nome': 'Outra'})
    result = client.post('/compradores', headers=headers, json={'nome': 'Cliente', 'email': 'cliente@example.com', 'senha': 'senha123', 'obras': [str(outra)]})
    assert result.status_code == 422

def test_comprador_altera_somente_sua_senha(client, database, account, headers):
    obra_id = ObjectId()
    database.tbl_obras.insert_one({'_id': obra_id, 'autor': str(account['_id']), 'nome': 'Casa'})
    cadastro = {'nome': 'Cliente', 'email': 'senha@example.com', 'senha': 'senha123', 'obras': [str(obra_id)]}
    assert client.post('/compradores', headers=headers, json=cadastro).status_code == 201
    token = client.post('/portal/login', json={'email': cadastro['email'], 'senha': cadastro['senha']}).json['access_token']
    buyer = {'Authorization': 'Bearer ' + token}
    assert client.patch('/portal/senha', headers=headers, json={'senha_atual': 'senha123', 'nova_senha': 'outrasenha'}).status_code == 403
    assert client.patch('/portal/senha', headers=buyer, json={'senha_atual': 'errada', 'nova_senha': 'outrasenha'}).status_code == 400
    assert client.patch('/portal/senha', headers=buyer, json={'senha_atual': 'senha123', 'nova_senha': 'curta'}).status_code == 422
    assert client.patch('/portal/senha', headers=buyer, json={'senha_atual': 'senha123', 'nova_senha': 'outrasenha'}).status_code == 200
    assert client.post('/portal/login', json={'email': cadastro['email'], 'senha': 'senha123'}).status_code == 401
    assert client.post('/portal/login', json={'email': cadastro['email'], 'senha': 'outrasenha'}).status_code == 200

def test_edicao_comprador_atualiza_acesso_e_protege_concorrencia(client, database, account, headers):
    a, b, outra = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_many([{'_id': a, 'autor': str(account['_id']), 'nome': 'A'}, {'_id': b, 'autor': str(account['_id']), 'nome': 'B'}, {'_id': outra, 'autor': str(ObjectId()), 'nome': 'Outra'}])
    cadastro = {'nome': 'Cliente', 'email': 'edit@example.com', 'senha': 'senha123', 'obras': [str(a)]}
    assert client.post('/compradores', headers=headers, json=cadastro).status_code == 201
    comprador = client.get('/compradores', headers=headers).json['compradores'][0]
    token = client.post('/portal/login', json={'email': cadastro['email'], 'senha': cadastro['senha']}).json['access_token']
    buyer = {'Authorization': 'Bearer ' + token}
    url = '/compradores/' + comprador['id']
    dados = {'nome': 'Nome novo', 'email': 'novo@example.com', 'obras': [str(b)], 'versao': comprador['versao']}
    assert client.patch(url, headers=buyer, json=dados).status_code == 403
    assert client.patch(url, headers=headers, json={**dados, 'obras': [str(outra)]}).status_code == 422
    assert client.patch(url, headers=headers, json=dados).status_code == 200
    assert client.get(f'/portal/obras/{a}', headers=buyer).status_code == 404
    assert client.get(f'/portal/obras/{b}', headers=buyer).status_code == 200
    assert client.patch(url, headers=headers, json=dados).status_code == 409
    assert client.patch(url, headers=headers, json={**dados, 'obras': [], 'versao': 1}).status_code == 200
    assert client.get('/portal/obras', headers=buyer).json['obras'] == []
    assert client.patch('/compradores/' + str(ObjectId()), headers=headers, json=dados).status_code == 404

def test_desativar_e_reativar_comprador_revoga_sessoes(client, database, account, headers):
    obra_id = ObjectId()
    database.tbl_obras.insert_one({'_id': obra_id, 'autor': str(account['_id']), 'nome': 'Casa'})
    cadastro = {'nome': 'Cliente', 'email': 'status@example.com', 'senha': 'senha123', 'obras': [str(obra_id)]}
    assert client.post('/compradores', headers=headers, json=cadastro).status_code == 201
    comprador = client.get('/compradores', headers=headers).json['compradores'][0]
    assert comprador['ativo'] is True
    credenciais = {'email': cadastro['email'], 'senha': cadastro['senha']}
    token = client.post('/portal/login', json=credenciais).json['access_token']
    buyer = {'Authorization': 'Bearer ' + token}
    url = '/compradores/' + comprador['id'] + '/status'
    assert client.patch(url, headers=buyer, json={'ativo': False, 'versao': 0}).status_code == 403
    assert client.patch(url, headers=headers, json={'ativo': 'false', 'versao': 0}).status_code == 422
    resposta = client.patch(url, headers=headers, json={'ativo': False, 'versao': 0})
    assert resposta.status_code == 200 and resposta.json['ativo'] is False
    assert client.get('/portal/obras', headers=buyer).status_code == 401
    bloqueado = client.post('/portal/login', json=credenciais)
    assert bloqueado.status_code == 403
    assert bloqueado.json['codigo'] == 'CONTA_DESATIVADA'
    assert 'desativada' in bloqueado.json['mensagem']
    assert client.post('/portal/login', json={**credenciais, 'senha': 'errada'}).status_code == 401
    assert client.patch(url, headers=headers, json={'ativo': True, 'versao': 0}).status_code == 409
    assert client.patch(url, headers=headers, json={'ativo': True, 'versao': 1}).status_code == 200
    assert client.get('/portal/obras', headers=buyer).status_code == 401
    assert client.post('/portal/login', json=credenciais).status_code == 200
    assert client.get('/compradores', headers=headers).json['compradores'][0]['obras'] == [str(obra_id)]
    assert client.patch('/compradores/' + str(ObjectId()) + '/status', headers=headers, json={'ativo': False, 'versao': 0}).status_code == 404

def test_construtora_nao_altera_status_de_comprador_de_outra(client, database, account, headers):
    id_comprador = ObjectId()
    database.tbl_compradores.insert_one({'_id': id_comprador, 'nome': 'Outro', 'email': 'outro@example.com', 'construtora_id': str(ObjectId()), 'ativo': True})
    assert client.patch(f'/compradores/{id_comprador}/status', headers=headers, json={'ativo': False, 'versao': 0}).status_code == 404

