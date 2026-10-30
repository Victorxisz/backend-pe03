"""Ponto de entrada compatível com python api.py e servidores WSGI."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
