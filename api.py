import os

from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from trabalhadores import trabalhadores_bp
from app.obras.routes import obras_bp

app = Flask(__name__)
CORS(app)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
JWTManager(app)

# Registra na aplicação as rotas definidas em trabalhadores.py.
app.register_blueprint(trabalhadores_bp)
app.register_blueprint(obras_bp)


if __name__ == "__main__":
    # Debug deve ser usado somente durante o desenvolvimento.
    app.run(debug=True)
