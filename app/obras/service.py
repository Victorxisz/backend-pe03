"""Cadastro, consulta e edição descritiva das obras."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import re

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .validacoes import validar_criacao_obra

EDITAVEIS = {"nome", "descricao", "localizacao", "cliente"}
CADASTRAVEIS = EDITAVEIS | {"tipo", "inicio", "entrega"}


class ErroObra(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def obra_para_dict(documento):
    obra = {
        campo: valor
        for campo, valor in documento.items()
        if campo != "_id"
    }

    obra["id"] = str(documento["_id"])

    registro = obra.get("data_registro")
    if isinstance(registro, datetime):
        if registro.tzinfo is None:
            registro = registro.replace(tzinfo=timezone.utc)

        obra["data_registro"] = registro.isoformat()

    if "dependencias_marcos" in documento:
        obra["dependencias_marcos"] = [
            {
                "id": str(vinculo["_id"]),
                "marco_id": str(vinculo["marco_id"]),
                "depende_de_id": str(vinculo["depende_de_id"]),
            }
            for vinculo in documento["dependencias_marcos"]
        ]

    obra["alertas"] = calcular_alertas(documento)
    return obra


def criar_obra(dados, autor):
    erro = validar_criacao_obra(dados)
    if erro:
        raise ErroObra(erro["mensagem"], 422, erro["campos"])

    proibidos = sorted(set(dados) - CADASTRAVEIS)
    if proibidos:
        raise ErroObra("Envie somente os campos do cadastro da obra", 422, proibidos)

    documento = deepcopy(dados)
    registro = datetime.now(timezone.utc)
    # BSON armazena milissegundos; POST e consultas devem devolver o mesmo instante.
    registro = registro.replace(microsecond=(registro.microsecond // 1000) * 1000)
    documento.update(
        _id=ObjectId(),
        autor=autor,
        data_registro=registro,
        estado="planejada",
        critica=False,
    )
    repository.salvar_obra(documento)
    return obra_para_dict(documento)


def buscar_obra(identifier):
    try:
        obra_id = ObjectId(identifier)
    except (InvalidId, TypeError):
        raise ErroObra("ID da obra inválido", 400, ["id"])

    documento = repository.buscar_obra_por_id(obra_id)
    if documento is None:
        raise ErroObra("Obra não encontrada", 404, ["id"])
    return obra_para_dict(documento)


def listar_obras(parametros):
    permitidos = {"nome", "cliente", "estado", "registroDe", "registroAte", "entregaDe", "entregaAte"}
    desconhecidos = sorted(set(parametros) - permitidos)
    if desconhecidos:
        raise ErroObra("Filtros desconhecidos", 422, desconhecidos)
    datas = {}
    for campo in ("registroDe", "registroAte", "entregaDe", "entregaAte"):
        if campo not in parametros:
            continue
        valor = parametros[campo]
        try:
            data = date.fromisoformat(valor)
            if data.isoformat() != valor:
                raise ValueError
        except (ValueError, TypeError):
            raise ErroObra("Informe uma data válida no formato AAAA-MM-DD", 422, [campo])
        datas[campo] = data
    for inicio, fim in (("registroDe", "registroAte"), ("entregaDe", "entregaAte")):
        if inicio in datas and fim in datas and datas[fim] < datas[inicio]:
            raise ErroObra("O fim do filtro não pode ser anterior ao início", 422, [fim])

    filtro = {}

    for campo in ("nome", "cliente"):
        if campo not in parametros:
            continue

        valor = parametros[campo].strip()

        if not valor:
            continue

        filtro[campo] = {
            "$regex": re.escape(valor),
            "$options": "i"
        }

    if "estado" in parametros:
        estado = parametros["estado"]
        if estado not in {"planejada", "em andamento", "concluída", "suspensa"}:
            raise ErroObra("Estado da obra inválido", 422, ["estado"])
        filtro["estado"] = estado
    registro = {}
    if "registroDe" in datas:
        registro["$gte"] = datetime.combine(datas["registroDe"], time.min, tzinfo=timezone.utc)
    if "registroAte" in datas:
        # Inclui todo o último dia sem depender da precisão do armazenamento.
        fim = datas["registroAte"]
        if fim == date.max:
            registro["$lte"] = datetime.max.replace(tzinfo=timezone.utc)
        else:
            registro["$lt"] = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=timezone.utc)
    if registro:
        filtro["data_registro"] = registro
    entrega = {}
    for campo, operador in (("entregaDe", "$gte"), ("entregaAte", "$lte")):
        if campo in datas:
            entrega[operador] = datas[campo].isoformat()
    if entrega:
        filtro["$or"] = [
            {"entrega.modalidade": "data_exata", "entrega.data": entrega},
            {"entrega.modalidade": "intervalo_estimado", "entrega.fim": entrega},
        ]
    return [obra_para_dict(documento) for documento in repository.consultar_obras(filtro)]


def listar_marcos(identifier):
    # Compatibilidade para consumidores do serviço anterior à migração da rota.
    from app.marcos.service import ErroMarco, listar_marcos as consultar_marcos

    try:
        return consultar_marcos(identifier)
    except ErroMarco as erro:
        raise ErroObra(str(erro), erro.status, erro.campos) from erro


def editar_descricao(identifier, dados):
    try:
        obra_id = ObjectId(identifier)
    except (InvalidId, TypeError):
        raise ErroObra("ID da obra inválido", 400, ["id"])

    if not isinstance(dados, dict) or not dados:
        raise ErroObra("Envie um objeto JSON com campos para corrigir", 422, ["corpo"])

    proibidos = sorted(set(dados) - EDITAVEIS)
    if proibidos:
        raise ErroObra(
            "Esta rota aceita apenas nome, descrição, endereço e cliente. "
            "Prazo e conclusão exigem o fluxo de mudança com motivo e histórico.",
            422,
            proibidos,
        )

    invalidos = [
        campo
        for campo, valor in dados.items()
        if not isinstance(valor, str) or not valor.strip()
    ]
    if invalidos:
        raise ErroObra("Os campos enviados devem ser textos não vazios", 422, invalidos)

    documento = repository.atualizar_descricao(obra_id, dados)
    if documento is None:
        raise ErroObra("Obra não encontrada", 404, ["id"])
    return documento


def calcular_alertas (documento):
    alertas = ["crítica"] if documento.get("critica") else []

    entrega = documento.get("entrega", {})
    modalidade = entrega.get("modalidade")

    if modalidade == "data_exata":
        limite = entrega.get("data")
    elif modalidade == "intervalo_estimado":
        limite = entrega.get("fim")
    else:
        return alertas

    if not limite:
        return alertas

    prazo = date.fromisoformat(limite)

    if documento.get("estado") == "concluída":
        data_conclusao = documento.get("data_conclusao")

        if not data_conclusao:
            return alertas

        referencia = date.fromisoformat(data_conclusao)
    else:
        referencia = datetime.now(timezone.utc).date()

    if referencia > prazo:
        alertas.append("atrasada")

    return alertas