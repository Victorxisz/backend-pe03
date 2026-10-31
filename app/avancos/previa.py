"""Consulta da linha do tempo publicada de uma obra."""

from datetime import timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

from app.auth.permissions import sessao_obrigatoria
from . import repository


previa_bp = Blueprint("previa", __name__)


class ErroConsultaPrevia(ValueError):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def _id_obra(valor):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroConsultaPrevia("Identificador inválido", 400, ["obra_id"]) from None


def _representar(documento):
    fato = documento["publicacao"]
    instante = fato["instante"]
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    descricao = documento.get("descricao", fato["descricao"])
    data = documento.get("data", fato["data"])
    midias = []
    # A composição atual, quando persistida por uma correção, prevalece sobre
    # o snapshot original. Publicações anteriores continuam usando o snapshot.
    for original in documento.get("midias", fato.get("midias", [])):
        item = dict(original)
        if "conteudo" not in item and item.get("id"):
            item["conteudo"] = f"/midias/{item['id']}/conteudo"
        midias.append(item)
    representacao = {
        "id": str(documento["_id"]),
        "avanco_id": str(documento["_id"]),
        "estado": "publicado",
        "autor": fato["autor"],
        "instante": instante.isoformat(),
        "data": data,
        "descricao": descricao,
        "marco": {"id": str(fato["marco"]["id"]), "nome": fato["marco"]["nome"]},
        "midias": midias,
    }
    if (descricao != fato["descricao"] or data != fato["data"]
            or documento.get("midias", fato.get("midias", [])) != fato.get("midias", [])
            or documento.get("editado") is True):
        representacao["editado"] = True
    if "origem_simulada" in documento:
        representacao["origem_simulada"] = documento["origem_simulada"]
    return representacao


def consultar_previa(obra_id):
    identificador = _id_obra(obra_id)
    if repository.buscar_obra(identificador) is None:
        raise ErroConsultaPrevia("Obra não encontrada", 404, ["obra_id"])
    return [_representar(item) for item in repository.consultar_publicados(identificador)]


@previa_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@previa_bp.after_request
def proteger_resposta(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@previa_bp.errorhandler(ErroConsultaPrevia)
def responder_erro(erro):
    return jsonify(mensagem=str(erro), campos=erro.campos), erro.status


@previa_bp.errorhandler(PyMongoError)
def responder_falha_banco(erro):
    current_app.logger.error("Falha no banco durante consulta da prévia")
    return jsonify(mensagem="Não foi possível concluir a solicitação", campos=[]), 503


@previa_bp.get("/obras/<string:obra_id>/previa")
def previa(obra_id):
    return jsonify(atualizacoes=consultar_previa(obra_id))
