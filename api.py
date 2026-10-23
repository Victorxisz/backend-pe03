from flask import Flask, jsonify
from pymongo.errors import PyMongoError
from flask_cors import CORS
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager
import os

from trabalhadores import trabalhadores_bp
from construtora import bcrypt, construtora_bp
from app.obras.routes import obras_bp
from db import colecao_sessoes_revogadas

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
CORS(app)

chave_jwt = os.getenv("JWT_SECRET_KEY")

if not chave_jwt:
    raise RuntimeError("Configure a JWT_SECRET_KEY no arquivo .env")

app.config["JWT_SECRET_KEY"] = chave_jwt
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)

jwt = JWTManager(app)

@jwt.token_in_blocklist_loader
def verificar_sessao_encerrada(cabecalho, dados_token):
    sessao_id = dados_token.get("sessao_id")

    if not isinstance(sessao_id, str) or not sessao_id:
        return True

    sessao = colecao_sessoes_revogadas.find_one(
        {"_id": sessao_id},
        {"_id": 1}
    )

    return sessao is not None

@jwt.revoked_token_loader
def responder_sessao_encerrada(cabecalho, dados_token):
    return jsonify({
        "erro": "Seu acesso foi encerrado. Entre novamente"
    }), 401


@app.errorhandler(PyMongoError)
def tratar_falha_banco(erro):
    app.logger.exception("Erro ao acessar o banco de dados")
    return jsonify({
        "erro": "Não foi possível concluir a solicitação. Tente novamente"
    }), 503

bcrypt.init_app(app)

# Registra na aplicação as rotas definidas em trabalhadores.py.
app.register_blueprint(trabalhadores_bp)
app.register_blueprint(construtora_bp)
app.register_blueprint(obras_bp)

if __name__ == "__main__":
    # Debug deve ser usado somente durante o desenvolvimento.
    app.run(debug=True)
