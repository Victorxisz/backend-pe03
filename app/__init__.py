"""Composição e inicialização da aplicação Flask."""

from datetime import timedelta
from pathlib import Path
import os

def create_app(config=None):
    from dotenv import load_dotenv
    from flask import Flask, jsonify
    from flask_cors import CORS
    from flask_jwt_extended import JWTManager
    from pymongo.errors import PyMongoError

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    application = Flask(__name__)
    application.config.update(
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY"),
        CONSTRUTORA_ID=os.getenv("CONSTRUTORA_ID", "").strip(),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=2),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=7),
    )
    if config:
        application.config.update(config)
    if not application.config["JWT_SECRET_KEY"]:
        raise RuntimeError("Configure a JWT_SECRET_KEY no arquivo .env")
    CORS(application)
    jwt = JWTManager(application)

    from db import colecao_sessoes_revogadas
    from construtora import bcrypt, construtora_bp
    from app.auth.routes import sessoes_bp
    from trabalhadores import trabalhadores_bp
    from app.obras.routes import obras_bp
    from app.marcos.routes import estado_marcos_bp, marcos_bp
    from app.avancos.midias_routes import midias_bp
    from app.avancos.routes import avancos_bp
    from app.publicacoes.routes import publicacoes_bp
    from app.mudanças.routes import mudancas_bp
    from app.ocorrencias.routes import ocorrencias_bp
    from app.historico.routes import historico_bp

    @jwt.token_in_blocklist_loader
    def verificar_sessao_encerrada(cabecalho, dados_token):
        configurada = application.config.get("CONSTRUTORA_ID")
        if configurada and dados_token.get("sub") != configurada:
            return True
        sessao_id = dados_token.get("sessao_id")
        if not isinstance(sessao_id, str) or not sessao_id:
            return True
        return colecao_sessoes_revogadas.find_one({"_id": sessao_id}, {"_id": 1}) is not None

    @jwt.revoked_token_loader
    def responder_sessao_encerrada(cabecalho, dados_token):
        return jsonify(erro="Seu acesso foi encerrado. Entre novamente"), 401

    @application.errorhandler(PyMongoError)
    def tratar_falha_banco(erro):
        application.logger.error("Erro ao acessar o banco de dados")
        return jsonify(erro="Não foi possível concluir a solicitação. Tente novamente"), 503

    bcrypt.init_app(application)
    for blueprint in (trabalhadores_bp, construtora_bp, obras_bp, marcos_bp,
                      estado_marcos_bp, midias_bp, avancos_bp, publicacoes_bp, mudancas_bp,
                      ocorrencias_bp, historico_bp, sessoes_bp):
        application.register_blueprint(blueprint)
    return application
