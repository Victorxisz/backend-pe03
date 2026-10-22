from flask import Flask
from flask_cors import CORS

from trabalhadores import trabalhadores_bp
from app.obras.routes import obras_bp


app = Flask(__name__)
CORS(app)

# Registra os grupos de rotas na aplicação.
app.register_blueprint(trabalhadores_bp)
app.register_blueprint(obras_bp)


if __name__ == "__main__":
    # Debug deve ser usado somente durante o desenvolvimento.
    app.run(debug=True)
