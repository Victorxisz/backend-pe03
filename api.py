from flask import Flask
from flask_cors import CORS

from trabalhadores import trabalhadores_bp


app = Flask(__name__)
CORS(app)

# Registra na aplicação as rotas definidas em trabalhadores.py.
app.register_blueprint(trabalhadores_bp)


if __name__ == "__main__":
    # Debug deve ser usado somente durante o desenvolvimento.
    app.run(debug=True)