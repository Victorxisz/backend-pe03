from flask import Blueprint, jsonify


midia_bp = Blueprint("midia", __name__, url_prefix="/api/v1/avancos")


@midia_bp.get('/avancos/<int:avancoId>/midias')
def avancos_midia():
    pass

@midia_bp.get('/midias/<int:midiaId>')
def midia():
    pass
