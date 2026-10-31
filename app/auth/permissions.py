from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)
from db import colecao_construtora

def sessao_obrigatoria (funcao):
    @wraps(funcao)
    def verificar_sessao(*args, **kwargs):
        # O preflight CORS não executa a operação. JWT também isenta OPTIONS,
        # portanto não há claims para consultar nessa requisição do navegador.
        if request.method == "OPTIONS":
            return None
        # Verifica token, expiração e revogação.
        # Reutiliza a configuração do JWTManager em api.py
        verify_jwt_in_request()

        if get_jwt().get("tipo") != "construtora":
            return jsonify({
                "erro":"Você não tem permissão para realizar está ação"
            }), 403

        identidade = get_jwt_identity()

        if not isinstance(identidade, str):
            return jsonify({
                "erro":"Entre novamente em sua conta"
            }), 401

        try:
            construtora_id = ObjectId(identidade)
        except (InvalidId, TypeError):
            return jsonify({
                "erro":"Entre novamente em sua conta"
            }), 401

        construtora = colecao_construtora.find_one(
            {"_id":construtora_id},
            {"ativo":1},
        )

        if construtora is None or construtora.get("ativo") is not True:
            return jsonify({
                "erro":"Entre em uma conta ativa"
            }), 401

        return funcao(*args, **kwargs)

    return verificar_sessao
