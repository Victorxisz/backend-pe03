from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timezone
import re
import os
from pymongo import MongoClient
from pymongo.errors import PyMongoError

#Carregar as variaveis do .env
load_dotenv()

# Retorna uma tupla com erro e status, ou None se os dados forem válidos.
def validar_dados_tabalhador(data):
    if not isinstance(data, dict):
        return {"erro": "Envie um objeto JSON válido"}, 422

    campos = ("nome", "email", "telefone", "cargo")

    # Verifica presença, tipo e conteúdo de todos os campos.
    for campo in campos:
        valor = data.get(campo)

        if not isinstance(valor, str) or not valor.strip():
            return {
                "erro": f"O campo '{campo}' deve ser um texto preenchido"
            }, 422

    email = data["email"].strip()

    # Verificação básica do formato do email.
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return {"erro": "Informe um email em formato válido"}, 422

    telefone = data["telefone"].strip()

    # Impede letras e outros caracteres indevidos.
    if not re.fullmatch(r"[0-9()\s-]+", telefone):
        return {
            "erro": "O telefone deve conter apenas números, espaços, parênteses ou hífen"
        }, 422

    numeros = re.sub(r"[^0-9]", "", telefone)

    if len(numeros) not in (10, 11):
        return {
            "erro": "Informe um telefone com DDD, com 10 ou 11 dígitos, sem +55"
        }, 422

    return None

#Verifica se tem os dados. SE tiver ele continua passando o dicionário
def worker_to_dict (data):
    if not data:
        return None
    return {
        "id":str(data["_id"]),
        "nome":data.get("nome"),
        "email":data.get("email"),
        "telefone":data.get("telefone"),
        "cargo":data.get("cargo"),
        "obras":data.get("obras"),
        "ativo":data.get("ativo"),
        "criado_em":data.get("criado_em")
    }

mongo_uri = os.getenv("MONGO_URI")

if not mongo_uri:
    raise RuntimeError("Configure MONGO_URI no arquivo .env")

client = MongoClient(mongo_uri)
db = client.get_default_database()

app = Flask(__name__)
CORS(app)

@app.route("/construtora/<int:obra_id>", methods=["POST"])
def cadastrar_trabalhadores(obra_id):
    data = request.get_json(silent=True) # Retorna None se o corpo não for interpretado como um JSON
    erro_validacao = validar_dados_tabalhador(data)

    if erro_validacao:
        erro, status = erro_validacao
        return jsonify(erro), status

    # Monta o trabalhador com status ativo e data/hora de criação em UTC.
    novo_trabalhador = {
        "nome": data["nome"].strip(),
        "email": data["email"].strip(),
        "telefone": re.sub(r"[^0-9]", "", data["telefone"]),
        "cargo": data["cargo"].strip().lower(),
        "obras": [obra_id],
        "ativo": True,
        "criado_em": datetime.now(timezone.utc)
    }

    try:
        resultado = db.tbl_trabalhadores.insert_one(novo_trabalhador)
    except PyMongoError:
        app.logger.exception("Erro ao cadastrar trabalhador")
        return jsonify({"erro": "Não foi possível salvar o trabalhador"}), 500

    return jsonify({
        "mensagem": "Trabalhador criado com sucesso",
        "id": str(resultado.inserted_id)
    }), 201

if (__name__) == "__main__":
    app.run(debug=True)