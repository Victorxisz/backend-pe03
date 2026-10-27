"""Regras de negócio para registrar e consultar avanços."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.config import ConfiguracaoArmazenamento
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento, ErroLimpeza
from . import repository
from .midias import ErroMidia, ServicoMidias
from .validacoes import validar_avanco


class ErroAvanco(Exception):
    def __init__(self, mensagem, status=422, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def _id(valor, campo):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroAvanco("Identificador inválido", 400, [campo]) from None


def _representar(documento):
    return {
        "id": str(documento["_id"]), "marco_id": str(documento["marco_id"]),
        "data": documento["data"], "descricao": documento["descricao"],
        "estado": documento["estado"], "autor": documento["autor"],
        "data_registro": documento["data_registro"].isoformat().replace("+00:00", "Z"),
        "midias": [{k: m[k] for k in ("tipo", "nome", "tamanho", "mime")} for m in documento["midias"]],
    }


def criar_avanco(marco_id, dados, arquivos, autor, servico_midias=None):
    marco_oid = _id(marco_id, "marco_id")
    campos = validar_avanco(dados)
    if campos:
        raise ErroAvanco("Informe uma data válida e uma descrição", 422, campos)
    if not repository.marco_existe(marco_oid):
        raise ErroAvanco("Marco não encontrado", 404, ["marco_id"])
    arquivos = list(arquivos)
    if not arquivos:
        raise ErroMidia("Envie ao menos uma foto, vídeo ou documento")
    servico = servico_midias or ServicoMidias(
        armazenamento=ArmazenamentoCloudinary(ConfiguracaoArmazenamento.do_ambiente())
    )
    documento_base = {
        "marco_id": marco_oid, "data": dados["data"], "descricao": dados["descricao"].strip(),
        "estado": "rascunho", "autor": autor, "data_registro": datetime.now(timezone.utc),
    }
    def salvar(midias):
        documento = {**documento_base, "midias": midias}
        return repository.inserir_avanco(documento), documento
    identifier, documento = servico.executar_com_midias(arquivos, salvar)
    documento["_id"] = identifier
    return _representar(documento)


def consultar_avanco(avanco_id):
    oid = _id(avanco_id, "avanco_id")
    documento = repository.buscar_avanco(oid)
    if documento is None:
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    return _representar(documento)


def consultar_avancos(marco_id):
    oid = _id(marco_id, "marco_id")
    if not repository.marco_existe(oid):
        raise ErroAvanco("Marco não encontrado", 404, ["marco_id"])
    return [_representar(item) for item in repository.listar_avancos(oid)]
