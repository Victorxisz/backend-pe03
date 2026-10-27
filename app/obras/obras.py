"""Validação e criação de obras conforme o contrato compartilhado com a edição."""

from datetime import date, datetime, timezone

from db import colecao_obras

from .service import ErroObra

TEXTOS = ("nome", "localizacao", "descricao", "cliente")
CAMPOS_CADASTRO = {*TEXTOS, "tipo", "inicio", "entrega"}


def validar_obra(dados):
    # Valida cada etapa antes de acessar os dados da próxima.
    if not isinstance(dados, dict):
        raise ErroObra("Envie um objeto JSON com os dados da obra", 422, ["corpo"])

    desconhecidos = sorted(set(dados) - CAMPOS_CADASTRO)
    if desconhecidos:
        raise ErroObra("Campos não permitidos no cadastro", 422, desconhecidos)

    invalidos = [
        campo for campo in TEXTOS
        if not isinstance(dados.get(campo), str) or not dados[campo].strip()
    ]
    if invalidos:
        raise ErroObra("Informe textos não vazios para os campos obrigatórios", 422, invalidos)

    if dados.get("tipo") not in ("casa", "apartamentos"):
        raise ErroObra("Tipo de obra deve ser 'casa' ou 'apartamentos'", 422, ["tipo"])

    if not data_valida(dados.get("inicio")):
        raise ErroObra("Informe início no formato AAAA-MM-DD", 422, ["inicio"])

    entrega_eh_valida(dados.get("entrega"))


def criar_obra(dados, autor):
    obra = {campo: dados[campo].strip() for campo in TEXTOS}
    obra.update({
        "tipo": dados["tipo"],
        "inicio": dados["inicio"],
        "entrega": dados["entrega"].copy(),
        "estado": "planejada",
        "critica": False,
        "autor": autor,
        "data_registro": datetime.now(timezone.utc),
    })
    resultado = colecao_obras.insert_one(obra)
    return {
        **{campo: valor for campo, valor in obra.items() if campo != "_id"},
        "id": str(resultado.inserted_id),
        "data_registro": obra["data_registro"].isoformat(),
    }


def data_valida(valor):
    if not isinstance(valor, str):
        return False
    try:
        return date.fromisoformat(valor).isoformat() == valor
    except ValueError:
        return False


def entrega_eh_valida(entrega):
    if not isinstance(entrega, dict):
        raise ErroObra("Informe a entrega como objeto JSON", 422, ["entrega"])

    modalidade = entrega.get("modalidade")
    if modalidade == "data_exata":
        campos_datas = ("data",)
    elif modalidade == "intervalo_estimado":
        campos_datas = ("inicio", "fim")
    else:
        raise ErroObra(
            "Modalidade deve ser 'data_exata' ou 'intervalo_estimado'",
            422, ["entrega.modalidade"],
        )

    if set(entrega) - {"modalidade", *campos_datas}:
        raise ErroObra("Envie somente os campos da modalidade escolhida", 422, ["entrega"])

    invalidos = [
        f"entrega.{campo}" for campo in campos_datas
        if not data_valida(entrega.get(campo))
    ]
    if invalidos:
        raise ErroObra("Informe datas válidas no formato AAAA-MM-DD", 422, invalidos)

    if modalidade == "intervalo_estimado" and entrega["fim"] < entrega["inicio"]:
        raise ErroObra("O fim da entrega não pode ser anterior ao início", 422, ["entrega.fim"])
