"""Validação de entrada; regras de prazo pertencem ao domínio."""

from app.dominio.comum import ErroDominio, ler_data
from app.dominio.obras import PrazoEntrega


def validar_criacao_obra(dados):
    if not isinstance(dados, dict):
        return {"mensagem": "Envie um objeto JSON válido", "campos": ["corpo"]}
    for campo in ("nome", "cliente", "localizacao", "descricao"):
        valor = dados.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            return {"mensagem": f"O campo '{campo}' deve ser um texto não vazio", "campos": [campo]}
    if dados.get("tipo") not in ("casa", "apartamentos"):
        return {"mensagem": "O tipo deve ser 'casa' ou 'apartamentos'", "campos": ["tipo"]}
    try:
        ler_data(dados.get("inicio"), "inicio")
        PrazoEntrega.de_dados(dados.get("entrega"))
    except ErroDominio as erro:
        return {"mensagem": str(erro), "campos": erro.campos}
    return None
