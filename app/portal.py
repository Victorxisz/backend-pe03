"""Contas de comprador e consulta de obras autorizadas."""
import uuid
from functools import wraps
from io import BytesIO
from bson import ObjectId
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, verify_jwt_in_request
from pymongo.errors import DuplicateKeyError
import db
from construtora import bcrypt
from app.auth.permissions import sessao_obrigatoria
from app.publicacoes.service import consultar_previa
from app.avancos.acesso_midias import abrir_conteudo, formato_para_resposta, nome_para_resposta
from app.avancos.midias import ErroMidia
from flask import send_file

portal_bp = Blueprint('portal_comprador', __name__)

@portal_bp.after_request
def proteger(resposta):
    resposta.headers['Cache-Control'] = 'private, no-store'
    resposta.headers['X-Content-Type-Options'] = 'nosniff'
    return resposta

@portal_bp.route('/compradores', methods=['GET', 'POST'])
@sessao_obrigatoria
def compradores():
    construtora = get_jwt_identity()
    colecao = db.banco_dados['tbl_compradores']
    if request.method == 'GET':
        return jsonify(compradores=[{'id': str(x['_id']), 'nome': x['nome'], 'email': x['email'], 'obras': [str(i) for i in x.get('obras', [])], 'versao': x.get('versao', 0), 'ativo': x.get('ativo') is True} for x in colecao.find({'construtora_id': construtora})])
    dados = request.get_json(silent=True) or {}
    nome, email, senha, obras = dados.get('nome'), dados.get('email'), dados.get('senha'), dados.get('obras')
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 120 or not isinstance(email, str) or '@' not in email or len(email) > 254 or not isinstance(senha, str) or len(senha) < 8 or len(senha.encode('utf-8')) > 72 or not isinstance(obras, list) or not obras or len(obras) > 100 or any(not isinstance(i, str) or not ObjectId.is_valid(i) for i in obras):
        return jsonify(mensagem='Informe nome, e-mail, senha de pelo menos 8 caracteres e uma ou mais obras válidas.'), 422
    ids = list(set(ObjectId(i) for i in obras))
    if db.colecao_obras.count_documents({'_id': {'$in': ids}, 'autor': {'$in': [construtora, ObjectId(construtora)]}}) != len(ids):
        return jsonify(mensagem='Selecione apenas obras da sua construtora.'), 422
    email = email.strip().lower()
    colecao.create_index('email', unique=True)
    try:
        colecao.insert_one({'nome': nome.strip(), 'email': email, 'senha_hash': bcrypt.generate_password_hash(senha).decode(), 'construtora_id': construtora, 'obras': ids, 'ativo': True})
    except DuplicateKeyError:
        return jsonify(mensagem='Já existe um comprador com este e-mail.'), 409
    return jsonify(mensagem='Comprador cadastrado.'), 201

@portal_bp.post('/portal/login')
def login():
    dados = request.get_json(silent=True) or {}
    email, senha = dados.get('email'), dados.get('senha')
    if not isinstance(email, str) or not isinstance(senha, str) or len(senha.encode('utf-8')) > 72:
        return jsonify(mensagem='E-mail ou senha inválidos.'), 401
    conta = db.banco_dados['tbl_compradores'].find_one({'email': email.strip().lower()})
    if not conta or not bcrypt.check_password_hash(conta['senha_hash'], senha):
        return jsonify(mensagem='E-mail ou senha inválidos.'), 401
    if conta.get('ativo') is not True:
        return jsonify(codigo='CONTA_DESATIVADA', mensagem='Sua conta está desativada. Entre em contato com a construtora para solicitar a reativação.'), 403
    token = create_access_token(identity=str(conta['_id']), additional_claims={'tipo': 'comprador', 'sessao_id': uuid.uuid4().hex, 'versao_sessao': conta.get('versao_sessao', 0)})
    return jsonify(access_token=token)

def acesso(func):
    @wraps(func)
    def verificar(*args, **kwargs):
        verify_jwt_in_request()
        identidade = get_jwt_identity()
        if get_jwt().get('tipo') != 'comprador' or not ObjectId.is_valid(identidade):
            return jsonify(mensagem='Acesso não autorizado.'), 403
        conta = db.banco_dados['tbl_compradores'].find_one({'_id': ObjectId(identidade), 'ativo': True})
        if not conta or get_jwt().get('versao_sessao', 0) != conta.get('versao_sessao', 0):
            return jsonify(mensagem='Conta indisponível ou sessão encerrada.'), 401
        return func(conta, *args, **kwargs)
    return verificar

def obra_autorizada(conta, obra_id):
    if not ObjectId.is_valid(obra_id):
        return None
    oid = ObjectId(obra_id)
    if oid not in conta.get('obras', []):
        return None
    return db.colecao_obras.find_one({'_id': oid, 'autor': {'$in': [conta['construtora_id'], ObjectId(conta['construtora_id'])]}})

@portal_bp.get('/portal/obras')
@acesso
def listar(conta):
    obras = db.colecao_obras.find({'_id': {'$in': conta.get('obras', [])}, 'autor': {'$in': [conta['construtora_id'], ObjectId(conta['construtora_id'])]}})
    return jsonify(nome=conta['nome'], obras=[{'id': str(o['_id']), 'nome': o.get('nome'), 'localizacao': o.get('localizacao')} for o in obras])

@portal_bp.get('/portal/obras/<obra_id>')
@acesso
def consultar(conta, obra_id):
    obra = obra_autorizada(conta, obra_id)
    if not obra:
        return jsonify(mensagem='Obra não encontrada.'), 404
    atualizacoes = consultar_previa(obra_id)
    itens = [{k: item[k] for k in ('id', 'descricao', 'data', 'instante', 'marco', 'midias')} for item in atualizacoes]
    return jsonify(obra={'id': obra_id, 'nome': obra.get('nome'), 'localizacao': obra.get('localizacao')}, atualizacoes=itens)

@portal_bp.get('/portal/obras/<obra_id>/midias/<midia_id>')
@acesso
def midia(conta, obra_id, midia_id):
    if not obra_autorizada(conta, obra_id) or not ObjectId.is_valid(midia_id):
        return jsonify(mensagem='Mídia não encontrada.'), 404
    permitida = any(any(str(m.get('id')) == midia_id for m in item.get('midias', [])) for item in consultar_previa(obra_id))
    if not permitida:
        return jsonify(mensagem='Mídia não encontrada.'), 404
    try:
        documento, conteudo = abrir_conteudo(midia_id)
    except ErroMidia as erro:
        return jsonify(mensagem=str(erro)), erro.status
    mime, embutido = formato_para_resposta(documento)
    return send_file(BytesIO(conteudo), mimetype=mime, as_attachment=not embutido, download_name=nome_para_resposta(documento))


@portal_bp.patch('/portal/senha')
@acesso
def alterar_senha(conta):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify(mensagem='Informe a senha atual e a nova senha.'), 422
    atual, nova = dados.get('senha_atual'), dados.get('nova_senha')
    if (not isinstance(atual, str) or not isinstance(nova, str)
            or not atual or len(atual.encode('utf-8')) > 72
            or len(nova) < 8 or len(nova.encode('utf-8')) > 72):
        return jsonify(mensagem='Informe a senha atual e uma nova senha com pelo menos 8 caracteres e até 72 bytes.'), 422
    senha_hash = conta.get('senha_hash')
    if not senha_hash or not bcrypt.check_password_hash(senha_hash, atual):
        return jsonify(mensagem='A senha atual está incorreta.'), 400
    if atual == nova:
        return jsonify(mensagem='A nova senha deve ser diferente da senha atual.'), 422
    resultado = db.banco_dados['tbl_compradores'].update_one(
        {'_id': conta['_id'], 'ativo': True, 'senha_hash': senha_hash},
        {'$set': {'senha_hash': bcrypt.generate_password_hash(nova).decode()}},
    )
    if resultado.matched_count != 1:
        return jsonify(mensagem='A conta foi alterada. Recarregue e tente novamente.'), 409
    return jsonify(mensagem='Senha alterada com sucesso.')


@portal_bp.patch('/compradores/<string:comprador_id>')
@sessao_obrigatoria
def editar_comprador(comprador_id):
    if not ObjectId.is_valid(comprador_id):
        return jsonify(mensagem='Comprador não encontrado.'), 404
    construtora = get_jwt_identity()
    colecao = db.banco_dados['tbl_compradores']
    conta = colecao.find_one({'_id': ObjectId(comprador_id), 'construtora_id': construtora})
    if not conta:
        return jsonify(mensagem='Comprador não encontrado.'), 404
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or set(dados) != {'nome', 'email', 'obras', 'versao'}:
        return jsonify(mensagem='Informe nome, e-mail, obras e versão do cadastro.'), 422
    nome, email, obras, versao = (dados[k] for k in ('nome', 'email', 'obras', 'versao'))
    if (not isinstance(nome, str) or not nome.strip() or len(nome) > 120
            or not isinstance(email, str) or '@' not in email or len(email) > 254
            or not isinstance(obras, list) or len(obras) > 100
            or any(not isinstance(i, str) or not ObjectId.is_valid(i) for i in obras)
            or type(versao) is not int or versao < 0):
        return jsonify(mensagem='Revise o nome, e-mail e obras selecionadas.'), 422
    ids = list(dict.fromkeys(ObjectId(i) for i in obras))
    if db.colecao_obras.count_documents({'_id': {'$in': ids}, 'autor': {'$in': [construtora, ObjectId(construtora)]}}) != len(ids):
        return jsonify(mensagem='Selecione apenas obras da sua construtora.'), 422
    filtro = {'_id': conta['_id'], 'construtora_id': construtora}
    filtro['versao'] = versao if versao else {'$in': [0, None]}
    try:
        resultado = colecao.update_one(filtro, {'$set': {'nome': nome.strip(), 'email': email.strip().lower(), 'obras': ids}, '$inc': {'versao': 1}})
    except DuplicateKeyError:
        return jsonify(mensagem='Já existe um comprador com este e-mail.'), 409
    if resultado.matched_count != 1:
        return jsonify(mensagem='O cadastro foi alterado. Recarregue e revise os dados.'), 409
    return jsonify(id=str(conta['_id']), nome=nome.strip(), email=email.strip().lower(), obras=[str(i) for i in ids], versao=versao + 1, ativo=conta.get('ativo') is True)


@portal_bp.patch('/compradores/<string:comprador_id>/status')
@sessao_obrigatoria
def alterar_status_comprador(comprador_id):
    if not ObjectId.is_valid(comprador_id):
        return jsonify(mensagem='Comprador não encontrado.'), 404
    construtora = get_jwt_identity()
    colecao = db.banco_dados['tbl_compradores']
    conta = colecao.find_one({'_id': ObjectId(comprador_id), 'construtora_id': construtora})
    if not conta:
        return jsonify(mensagem='Comprador não encontrado.'), 404
    dados = request.get_json(silent=True)
    if (not isinstance(dados, dict) or set(dados) != {'ativo', 'versao'}
            or type(dados['ativo']) is not bool or type(dados['versao']) is not int or dados['versao'] < 0):
        return jsonify(mensagem='Informe o status e a versão do comprador.'), 422
    versao = dados['versao']
    filtro = {'_id': conta['_id'], 'construtora_id': construtora,
              'versao': versao if versao else {'$in': [0, None]}}
    alteracoes = {'$set': {'ativo': dados['ativo']}, '$inc': {'versao': 1}}
    if not dados['ativo']:
        alteracoes['$inc']['versao_sessao'] = 1
    resultado = colecao.update_one(filtro, alteracoes)
    if resultado.matched_count != 1:
        return jsonify(mensagem='O cadastro foi alterado. Recarregue e revise os dados.'), 409
    return jsonify(id=str(conta['_id']), nome=conta['nome'], email=conta['email'],
                   obras=[str(i) for i in conta.get('obras', [])], ativo=dados['ativo'], versao=versao + 1)

