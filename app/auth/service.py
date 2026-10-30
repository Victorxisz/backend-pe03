"""Consulta e apresentação da conta da sessão autenticada."""
from bson import ObjectId
from flask import current_app
from flask_jwt_extended import get_jwt_identity
from db import colecao_construtora


def consultar_sessao():
    identidade = get_jwt_identity()
    configurada = current_app.config.get("CONSTRUTORA_ID", "")
    if identidade != configurada or not ObjectId.is_valid(identidade):
        return None
    conta = colecao_construtora.find_one({"_id": ObjectId(identidade), "ativo": True})
    if conta is None:
        return None
    return {"id": str(conta["_id"]), "nome": conta["nome"],
            "email": conta["email"], "telefone": conta.get("telefone")}
