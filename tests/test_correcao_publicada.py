"""UC-11: escrita de correções publicadas (CT-46 a CT-51).

Cloudinary e rollback local são simulados; não comprova isolamento real do Atlas.
"""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from unittest.mock import Mock

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_midias import arquivo, config, conteudos
from test_avancos_uc09 import backend, transacao_local


@pytest.fixture
def publicada(app, database, backend, config, conteudos, transacao_local):
    from app.avancos.midias import validar_arquivo
    from app.avancos.acesso_midias import midia_para_dict
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    obra, marco, avanco, midia = ObjectId(), ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_one({'_id': obra, 'nome': 'Obra'})
    database.tbl_marcos.insert_one({'_id': marco, 'obra_id': obra, 'nome': 'Marco'})
    registro = dict(ArmazenamentoCloudinary().enviar(validar_arquivo(arquivo(conteudos['png'], 'original.png'), config)),
                    _id=midia, avanco_id=avanco, data_envio=datetime(2030, 1, 1))
    database.tbl_midias.insert_one(registro)
    publica = midia_para_dict(registro)
    publica['conteudo'] = f'/midias/{midia}/conteudo'
    database.tbl_avancos.insert_one({
        '_id': avanco, 'marco_id': marco, 'autor': 'autor original', 'origem_simulada': True,
        'data': '2030-01-01', 'descricao': 'Parede branca', 'revisao': 1,
        'data_registro': datetime(2030, 1, 1), 'estado': 'publicado',
        'publicacao': {'autor': 'publicador', 'instante': datetime(2030, 1, 1),
                       'marco': {'id': str(marco), 'nome': 'Marco'},
                       'data': '2030-01-01', 'descricao': 'Parede branca', 'midias': [publica]},
    })
    return {'id': avanco, 'midia': registro, 'obra': obra, 'url': f'/avancos/{avanco}'}

def test_duas_correcoes_http_persistem_e_mantem_cadeia(client, headers, database, publicada):
    primeira = client.patch(publicada['url'], headers=headers,
                            json={'descricao':'Parede azul', 'motivo':'Cor corrigida'})
    segunda = client.patch(publicada['url'], headers=headers,
                           json={'data':'2030-01-02', 'motivo':'Data corrigida'})
    assert primeira.status_code == segunda.status_code == 200
    versoes = client.get(publicada['url'] + '/versoes', headers=headers).json['versoes']
    assert [v['conteudo']['descricao'] for v in versoes] == ['Parede branca', 'Parede azul', 'Parede azul']
    assert [v['atual'] for v in versoes] == [False, False, True]
    salvo = database.tbl_avancos.find_one({'_id':publicada['id']})
    assert salvo['revisao'] == 3 and len(salvo['correcoes']) == 2
    assert salvo['correcoes'][0]['campos'] == ['descricao']
    assert salvo['correcoes'][1]['campos'] == ['data']

def test_correcao_http_com_nova_midia_e_conteudo_recuperavel(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    versoes = resposta.json["versoes"]
    assert len(versoes) == 2
    assert versoes[0]["conteudo"]["midias"] == []
    midia = versoes[1]["conteudo"]["midias"][0]
    assert client.get(midia["conteudo"], headers=headers).data == conteudos["png"]
    assert database.tbl_midias.count_documents({"avanco_id": avanco}) == 1


def test_falha_ao_gravar_correcao_remove_upload_e_nao_altera_publicacao(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    from pymongo.errors import PyMongoError
    from app.avancos import repository
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id
    antes = snapshot(database)
    monkeypatch.setattr(repository, "salvar_correcao_publicada", lambda *args: (_ for _ in ()).throw(PyMongoError("falha")))

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 503
    assert snapshot(database) == antes
    assert backend[0] == {}


def test_falha_na_compensacao_preserva_diario_para_reconciliacao(
    client, headers, database, monkeypatch, backend, transacao_local, conteudos
):
    # Preparação
    from io import BytesIO
    from pymongo.errors import PyMongoError
    from app.avancos import repository
    avanco = database.tbl_avancos.insert_one({
        "estado": "publicado", "autor": "original", "data": "2030-01-01",
        "descricao": "Antes", "revisao": 1,
        "publicacao": {"autor": "original", "instante": datetime(2030, 1, 1),
                       "data": "2030-01-01", "descricao": "Antes", "midias": []},
    }).inserted_id
    antes = database.tbl_avancos.find_one({"_id": avanco})
    monkeypatch.setattr(repository, "salvar_correcao_publicada", lambda *args: (_ for _ in ()).throw(PyMongoError("falha")))
    backend[2].side_effect = RuntimeError("remoção indisponível")

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        data={"motivo": "Foto corrigida", "midias": (BytesIO(conteudos["png"]), "foto.png")},
        content_type="multipart/form-data")

    # Verificação
    assert resposta.status_code == 503
    assert database.tbl_avancos.find_one({"_id": avanco}) == antes
    diario = database.tbl_uploads_pendentes.find_one({"avanco_id": avanco})
    assert diario["estado"] == "pendente" and diario["referencias"]
    assert diario["referencias"][0]["public_id"] in backend[0]


def test_midia_selecionada_indisponivel_recusa_correcao(
    client, headers, database, monkeypatch, backend, transacao_local
):
    # Preparação
    avanco = ObjectId()
    midia_id = ObjectId()
    referencia = {"provedor": "cloudinary", "public_id": "pe03/evidencias/" + "a" * 32,
                  "resource_type": "image", "delivery_type": "authenticated", "formato": "png"}
    midia = {"_id": midia_id, "avanco_id": avanco, "tipo": "foto", "nome": "ausente.png",
             "tamanho": 100, "mime": "image/png", "referencia_externa": referencia}
    database.tbl_midias.insert_one(midia)
    from app.avancos.acesso_midias import midia_para_dict
    publica = {"data": "2030-01-01", "descricao": "Antes", "midias": [midia_para_dict(midia)]}
    database.tbl_avancos.insert_one({"_id": avanco, "estado": "publicado", "autor": "original",
        "data": "2030-01-01", "descricao": "Antes", "revisao": 1,
        "publicacao": {**publica, "autor": "original", "instante": datetime(2030, 1, 1)}})
    from unittest.mock import Mock
    from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
    obter = Mock(side_effect=ErroArmazenamento("Arquivo ausente", 404))
    monkeypatch.setattr(ArmazenamentoCloudinary, "obter_conteudo", obter)
    antes = snapshot(database)

    # Execução
    resposta = client.patch(f"/avancos/{avanco}", headers=headers,
        json={"motivo": "Troca", "midias_manter": [str(midia_id)], "descricao": "Depois"})

    # Verificação
    assert resposta.status_code == 422
    assert "midias_manter" in resposta.json["campos"]
    obter.assert_called_once_with(referencia, 100)
    assert snapshot(database) == antes

@pytest.mark.parametrize('payload', [
    {'descricao':'Depois'}, {'descricao':'Depois', 'motivo':''},
    {'descricao':'Depois', 'motivo':'  '}, {'descricao':'Depois', 'motivo':17},
    {'descricao':None, 'motivo':'Correção'}, {'descricao':' ', 'motivo':'Correção'},
    {'autor':'forjado', 'motivo':'Correção', 'descricao':'Depois'},
    {'origem_simulada':False, 'motivo':'Correção', 'descricao':'Depois'},
    {'motivo':'Correção', 'descricao':'Depois', 'estado':'rascunho'},
    {'motivo':'Correção', 'midias_manter':['inválido']},
])
def test_ct47_validacoes_preservam_publicacao(client, headers, database, publicada, payload):
    antes = snapshot(database)
    r = client.patch(publicada['url'], headers=headers, json=payload)
    assert r.status_code == 422
    assert snapshot(database) == antes


@pytest.mark.parametrize('tipo', ['descricao', 'data', 'midias', 'motivo_so', 'sem_midia'])
def test_ct47_rejeita_sem_mudanca_ou_sem_evidencia(client, headers, database, publicada, tipo):
    d = {'motivo':'Correção'}
    if tipo == 'descricao': d['descricao'] = ' Parede branca '
    if tipo == 'data': d['data'] = '2030-01-01'
    if tipo == 'midias': d['midias_manter'] = [str(publicada['midia']['_id'])]
    if tipo == 'sem_midia': d['midias_manter'] = []
    antes = snapshot(database)
    assert client.patch(publicada['url'], headers=headers, json=d).status_code == 422
    assert snapshot(database) == antes


def test_ct47_registro_antigo_sem_midia_precisa_receber_evidencia(client, headers, database, backend, transacao_local):
    avanco = database.tbl_avancos.insert_one({
        'estado':'publicado', 'autor':'original', 'data':'2030-01-01', 'descricao':'Antes',
        'publicacao':{'data':'2030-01-01', 'descricao':'Antes', 'midias':[]},
    }).inserted_id
    antes = snapshot(database)
    r = client.patch(f'/avancos/{avanco}', headers=headers, json={'motivo':'Corrigir', 'descricao':'Depois'})
    assert r.status_code == 422
    assert snapshot(database) == antes


@pytest.mark.parametrize('status', [404, 503])
def test_ct48_confirma_midias_atuais_mesmo_em_correcao_so_de_texto(
    client, headers, database, publicada, monkeypatch, status,
):
    from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
    obter = Mock(side_effect=ErroArmazenamento('indisponível', status))
    monkeypatch.setattr(ArmazenamentoCloudinary, 'obter_conteudo', obter)
    antes = snapshot(database)
    r = client.patch(publicada['url'], headers=headers, json={'motivo':'Corrigir texto', 'descricao':'Depois'})
    assert r.status_code == (422 if status == 404 else 503)
    obter.assert_called_once()
    assert snapshot(database) == antes


def test_ct46_ct50_grava_auditoria_sem_mudar_autoria_ou_origem(
    client, headers, account, database, publicada,
):
    antes = deepcopy(database.tbl_avancos.find_one({'_id':publicada['id']}))
    r = client.patch(publicada['url'], headers=headers,
                     json={'motivo':' Corrigir a cor ', 'descricao':'Parede azul'})
    assert r.status_code == 200
    salvo = database.tbl_avancos.find_one({'_id':publicada['id']})
    assert salvo['publicacao'] == antes['publicacao']
    assert salvo['autor'] == 'autor original' and salvo['origem_simulada'] is True
    correcao = salvo['correcoes'][0]
    assert correcao['campos'] == ['descricao']
    assert correcao['autor'] == str(account['_id'])
    assert correcao['motivo'] == 'Corrigir a cor'
    assert correcao['instante'].replace(tzinfo=None) == datetime(2030, 10, 20, 12)
    assert all(v['origem_simulada'] is True for v in r.json['versoes'])
    assert all(v['autor_original'] == 'autor original' for v in r.json['versoes'])
    assert 'referencia_externa' not in r.text and 'public_id' not in r.text
    previa = client.get(f"/obras/{publicada['obra']}/previa", headers=headers)
    assert previa.json['atualizacoes'][0]['descricao'] == 'Parede azul'
    assert previa.json['atualizacoes'][0]['editado'] is True
    assert previa.json['atualizacoes'][0]['origem_simulada'] is True
    atual = client.get(publicada['url'], headers=headers).json
    assert atual['editado'] is True and atual['origem_simulada'] is True
    assert atual['autor'] == 'autor original'


def test_ct46_troca_midia_e_preserva_acesso_a_versao_antiga(
    client, headers, database, publicada, conteudos, backend,
):
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Trocar evidência', 'midias_manter':'[]',
        'midias':(BytesIO(conteudos['jpg']), 'depois.jpg'),
    })
    assert r.status_code == 200, r.json
    versoes = r.json['versoes']
    anterior = versoes[0]['conteudo']['midias'][0]
    atual = versoes[1]['conteudo']['midias'][0]
    assert anterior['id'] != atual['id']
    assert versoes[1]['correcao']['campos'] == ['midias']
    assert client.get(anterior['conteudo'], headers=headers).data == conteudos['png']
    assert client.get(atual['conteudo'], headers=headers).data == conteudos['jpg']
    assert database.tbl_midias.count_documents({'avanco_id':publicada['id']}) == 2
    backend[2].assert_not_called()
    from app.avancos import repository
    assert repository.referencia_em_uso(publicada['midia']['referencia_externa'])
    # Uma indisponibilidade histórica não invalida mídias atuais recuperáveis.
    backend[0].pop(publicada['midia']['referencia_externa']['public_id'])
    assert client.patch(publicada['url'], headers=headers,
        json={'motivo':'Texto', 'descricao':'Texto corrigido'}).status_code == 200


@pytest.mark.parametrize('causa,status', [('corrompido',422), ('limite',413), ('provedor',503)])
def test_ct48_falha_nova_midia_mantem_versao_anterior(
    client, headers, database, publicada, conteudos, backend, monkeypatch, causa, status,
):
    conteudo = conteudos['png']
    if causa == 'corrompido': conteudo = b'arquivo invalido'
    if causa == 'limite': monkeypatch.setenv('MIDIA_FOTO_MAX_BYTES', '8')
    if causa == 'provedor': backend[1].side_effect = RuntimeError('fora do ar')
    antes = snapshot(database)
    remotos = dict(backend[0])
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Nova foto', 'midias':(BytesIO(conteudo), 'nova.png'),
    })
    assert r.status_code == status, r.json
    assert snapshot(database) == antes
    assert backend[0] == remotos


def test_ct49_falha_no_banco_reverte_historico_atual_e_midias(
    client, headers, database, publicada, conteudos, backend, monkeypatch,
):
    original = database.tbl_avancos.update_one
    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        raise PyMongoError('falha após escrita')
    monkeypatch.setattr(database.tbl_avancos, 'update_one', falhar)
    antes, remotos = snapshot(database), dict(backend[0])
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Nova evidência', 'descricao':'Não confirmar',
        'midias':(BytesIO(conteudos['jpg']), 'nova.jpg'),
    })
    assert r.status_code == 503
    assert snapshot(database) == antes
    assert backend[0] == remotos


def test_ct49_correcao_concorrente_nao_e_sobrescrita(
    client, headers, account, database, publicada, conteudos, monkeypatch, backend,
):
    from app.avancos import repository
    from app.avancos.correcoes import corrigir_publicacao
    original = repository.salvar_correcao_publicada
    def concorrente(*args):
        monkeypatch.setattr(repository, 'salvar_correcao_publicada', original)
        corrigir_publicacao(str(publicada['id']), {'motivo':'Concorrente', 'descricao':'Vencedora'}, str(account['_id']))
        return original(*args)
    monkeypatch.setattr(repository, 'salvar_correcao_publicada', concorrente)
    remotos = dict(backend[0])
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Pedido antigo', 'descricao':'Não sobrescrever',
        'midias':(BytesIO(conteudos['jpg']), 'nova.jpg'),
    })
    assert r.status_code == 409
    salvo = database.tbl_avancos.find_one({'_id':publicada['id']})
    assert salvo['descricao'] == 'Vencedora' and len(salvo['correcoes']) == 1
    assert salvo['revisao'] == 2 and backend[0] == remotos


@pytest.mark.parametrize('alvo', ['midia', 'publicacao'])
def test_ct49_revalida_snapshot_mesmo_sem_incremento_de_revisao(
    client, headers, database, publicada, monkeypatch, alvo,
):
    from app.avancos import repository
    original = repository.salvar_correcao_publicada
    def mudar(*args):
        if alvo == 'midia':
            database.tbl_midias.update_one({'_id':publicada['midia']['_id']}, {'$set':{'nome':'Outra'}})
        else:
            database.tbl_avancos.update_one({'_id':publicada['id']}, {'$set':{'descricao':'Outra'}})
        return original(*args)
    monkeypatch.setattr(repository, 'salvar_correcao_publicada', mudar)
    r = client.patch(publicada['url'], headers=headers, json={'motivo':'Corrigir', 'descricao':'Depois'})
    assert r.status_code == 409
    assert database.tbl_avancos.find_one({'_id':publicada['id']}).get('correcoes') is None


def test_ct49_commit_incerto_nao_remove_midia_confirmada(
    client, headers, database, publicada, conteudos, backend, monkeypatch,
):
    from app.avancos import repository
    original = repository.salvar_correcao_publicada
    def confirmar_sem_resposta(*args):
        original(*args)
        raise PyMongoError('confirmação perdida', error_labels=['UnknownTransactionCommitResult'])
    monkeypatch.setattr(repository, 'salvar_correcao_publicada', confirmar_sem_resposta)
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Nova foto', 'midias':(BytesIO(conteudos['jpg']), 'nova.jpg'),
    })
    assert r.status_code == 503
    backend[2].assert_not_called()
    assert database.tbl_uploads_pendentes.find_one()['estado'] == 'concluida'
    assert len(client.get(publicada['url'] + '/versoes', headers=headers).json['versoes']) == 2


def test_ct47_rejeita_midia_que_pertence_a_outro_avanco(client, headers, database, publicada):
    outra = dict(publicada['midia'], _id=ObjectId(), avanco_id=ObjectId())
    database.tbl_midias.insert_one(outra)
    antes = snapshot(database)
    r = client.patch(publicada['url'], headers=headers,
                     json={'motivo':'Troca', 'midias_manter':[str(outra['_id'])]})
    assert r.status_code == 422 and snapshot(database) == antes


def test_ct50_autoria_nao_pode_ser_forjada_sem_sessao(client, database, publicada):
    antes = snapshot(database)
    assert client.patch(publicada['url'], json={'motivo':'Corrigir', 'descricao':'Depois'}).status_code == 401
    assert snapshot(database) == antes


def test_ct51_consulta_rejeita_campos_alterados_inconsistentes(client, headers, database, publicada):
    assert client.patch(publicada['url'], headers=headers,
        json={'motivo':'Texto', 'descricao':'Depois'}).status_code == 200
    database.tbl_avancos.update_one({'_id':publicada['id']}, {'$set':{'correcoes.0.campos':['midias']}})
    assert client.get(publicada['url'] + '/versoes', headers=headers).status_code == 409

def test_ct47_reordenar_as_mesmas_midias_nao_cria_versao(
    client, headers, database, publicada, conteudos, config,
):
    from app.avancos.midias import validar_arquivo
    from app.avancos.acesso_midias import midia_para_dict
    from app.integracoes.armazenamento import ArmazenamentoCloudinary
    outra = dict(ArmazenamentoCloudinary().enviar(validar_arquivo(arquivo(conteudos['jpg'], 'outra.jpg'), config)),
                 _id=ObjectId(), avanco_id=publicada['id'])
    database.tbl_midias.insert_one(outra)
    item = midia_para_dict(outra)
    item['conteudo'] = f"/midias/{item['id']}/conteudo"
    database.tbl_avancos.update_one({'_id':publicada['id']}, {'$push':{'publicacao.midias':item}})
    antes = snapshot(database)
    r = client.patch(publicada['url'], headers=headers, json={
        'motivo':'Mesmos arquivos', 'midias_manter':[str(outra['_id']), str(publicada['midia']['_id'])],
    })
    assert r.status_code == 422
    assert snapshot(database) == antes


def test_ct51_voltar_ao_texto_original_preserva_todas_as_versoes(client, headers, database, publicada):
    assert client.patch(publicada['url'], headers=headers,
        json={'motivo':'Cor', 'descricao':'Parede azul'}).status_code == 200
    r = client.patch(publicada['url'], headers=headers,
                     json={'motivo':'Restaurar texto', 'descricao':'Parede branca'})
    assert r.status_code == 200
    assert [v['conteudo']['descricao'] for v in r.json['versoes']] == ['Parede branca', 'Parede azul', 'Parede branca']
    previa = client.get(f"/obras/{publicada['obra']}/previa", headers=headers).json['atualizacoes'][0]
    assert previa['editado'] is True and previa['origem_simulada'] is True


@pytest.mark.parametrize('problema', ['metadados', 'vinculo'])
def test_ct48_recusa_midia_atual_invalida_ou_sem_vinculo(client, headers, database, publicada, problema):
    if problema == 'metadados':
        database.tbl_midias.update_one({'_id':publicada['midia']['_id']}, {'$set':{'mime':'text/html'}})
    else:
        database.tbl_midias.delete_one({'_id':publicada['midia']['_id']})
    antes = snapshot(database)
    assert client.patch(publicada['url'], headers=headers,
        json={'motivo':'Corrigir', 'descricao':'Depois'}).status_code == 422
    assert snapshot(database) == antes

def test_ct48_upload_confirmado_mas_nao_recuperavel_e_compensado(
    client, headers, database, publicada, conteudos, backend, monkeypatch,
):
    from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
    obter = ArmazenamentoCloudinary.obter_conteudo
    original_id = publicada['midia']['referencia_externa']['public_id']
    def recuperar(self, referencia, tamanho):
        if referencia['public_id'] != original_id:
            raise ErroArmazenamento('Arquivo recém-enviado indisponível', 404)
        return obter(self, referencia, tamanho)
    monkeypatch.setattr(ArmazenamentoCloudinary, 'obter_conteudo', recuperar)
    antes, remotos = snapshot(database), dict(backend[0])
    r = client.patch(publicada['url'], headers=headers, data={
        'motivo':'Nova foto', 'midias':(BytesIO(conteudos['jpg']), 'nova.jpg'),
    })
    assert r.status_code == 422
    assert snapshot(database) == antes and backend[0] == remotos
