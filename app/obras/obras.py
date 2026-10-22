from datetime import date, datetime, timezone

from db import colecao_obras

def validar_obra(dados):
    entrega = dados.get("entrega")
    validacoes_de_dados = [
        eh_dicionario(dados),
        campos_sao_validos(dados),
        tipo_eh_valido(dados),
        data_eh_valida(dados),
        entrega_eh_dicionario(entrega),
        entrega_eh_valida(entrega)]
    
    for validacao in validacoes_de_dados:
        if validacao: return validacao

    return None

def criar_obra(dados):
    obra = {
        campo: dados[campo].strip()
        for campo in ("nome", "tipo", "localizacao", "descricao", "cliente_referencia")
    }
    obra.update({
        "inicio": dados["inicio"],
        "entrega": dados["entrega"].copy(),
        "estado": "planejada",
        "critica": False,
        "criado_em": datetime.now(timezone.utc),
    })
    resultado = colecao_obras.insert_one(obra)
    return {
        **{campo: valor for campo, valor in obra.items() if campo != "_id"},
        "id": str(resultado.inserted_id),
        "criado_em": obra["criado_em"].isoformat(),
    }

def data_valida(valor):
    if not isinstance(valor, str):
        return False
    try:
        return date.fromisoformat(valor).isoformat() == valor
    except ValueError:
        return False

def eh_dicionario(dados):
    if not isinstance(dados, dict):
        return "Dados não entregues em modelo JSON"

def campos_sao_validos(dados):
    for campo in ("nome", "localizacao", "descricao", "cliente_referencia"):
        if not isinstance(dados.get(campo), str) or not dados[campo].strip():
            return f"{campo} não é string ou lista"

def tipo_eh_valido(dados):
    if dados.get("tipo") not in ("casa", "apartamento"):
        return "Tipo de obra deve ser 'casa' ou 'apartamento'"

def data_eh_valida(dados):
    if not data_valida(dados.get("inicio")):
        return "data 'inicio' não é em formato ISO"

def entrega_eh_dicionario(entrega):
    if not isinstance(entrega, dict):
        "'Entrega' não é um dicionário"

def entrega_eh_valida(entrega):
    modalidade = entrega.get("modalidade")
    if modalidade == "data_exata":
        if set(entrega) != {"modalidade", "data"}:
            return "informe data valida"
        elif modalidade == "intervalo_estimado":
            if (set(entrega)) != {"modalidade", "inicio", "fim"} or entrega["fim"] < entrega["inicio"]:
                return "informe intervalo de data existente"
    else:
        return "modalidade deve ser string 'data_exata' ou 'intervalo_estimado'"

    



