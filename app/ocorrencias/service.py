"""Regras de aceitação formal sem alterar o estado da ocorrência."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.dominio.comum import ErroDominio
from app.serializacao import serializar
from .repository import (
    EstadoOcorrenciaIncompativel,
    OcorrenciaNaoEncontrada,
    RepositorioOcorrencias,
)
from .validacoes import validar_aceitacao


class ErroOcorrencia(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status, self.campos = status, list(campos)


class ServicoOcorrencias:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio or RepositorioOcorrencias()
        self.relogio = relogio

    def aceitar(self, ocorrencia_id, dados, autor, chave_reenvio=None):
        try:
            validar_aceitacao(dados)
        except ErroDominio as erro:
            raise ErroOcorrencia(str(erro), 422, erro.campos) from erro
        try:
            oid = ObjectId(ocorrencia_id)
        except (InvalidId, TypeError):
            raise ErroOcorrencia("ID da ocorrência inválido", 400, ["ocorrenciaId"]) from None
        if not isinstance(autor, str) or not autor:
            raise ErroOcorrencia("Conta autenticada inválida", 401)
        agora = self.relogio.agora() if self.relogio else datetime.now(timezone.utc)
        documento = {"justificativa": dados["justificativa"].strip(), "autor": autor, "data": agora}
        if dados.get("medida_compensatoria") is not None:
            documento["medida_compensatoria"] = dados["medida_compensatoria"].strip()
        try:
            salvo, repetida = self.repositorio.aceitar(oid, documento, chave_reenvio)
        except OcorrenciaNaoEncontrada:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrenciaId"]) from None
        except EstadoOcorrenciaIncompativel:
            raise ErroOcorrencia("Somente ocorrência sem solução pode ser aceita", 409, ["estado"]) from None
        item = serializar(salvo.get("aceitacoes", [])[-1])
        return item, repetida

    def listar_aceitacoes(self, ocorrencia_id):
        try:
            oid = ObjectId(ocorrencia_id)
        except (InvalidId, TypeError):
            raise ErroOcorrencia("ID da ocorrência inválido", 400, ["ocorrenciaId"]) from None
        ocorrencia = self.repositorio.buscar(oid)
        if ocorrencia is None:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrenciaId"])
        return serializar(ocorrencia.get("aceitacoes", []))
