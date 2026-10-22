from flask import Flask
from flask_cors import CORS
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager
import os

from trabalhadores import trabalhadores_bp
from construtora import bcrypt, construtora_bp

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
CORS(app)

chave_jwt = os.getenv("JWT_SECRET_KEY")

if not chave_jwt:
    raise RuntimeError("Configure a JWT_SECRET_KEY no arquivo .env")

app.config["JWT_SECRET_KEY"] = chave_jwt
app.config["JWT_SECRET_KEY_EXPIRES"] = timedelta(hours=2)

jwt = JWTManager(app)
bcrypt.init_app(app)

# Registra na aplicação as rotas definidas em trabalhadores.py.
app.register_blueprint(trabalhadores_bp)
app.register_blueprint(construtora_bp)

if __name__ == "__main__":
    # Debug deve ser usado somente durante o desenvolvimento.
    app.run(debug=True)
