"""Cadastro, consulta e aceitação formal das ocorrências de uma obra."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError, WriteError

from app.avancos.acesso_midias import midia_para_dict
from app.avancos.midias import ServicoMidias, ResultadoPersistenciaIndeterminado
from app.avancos.operacoes import OperacaoUpload
from app.dominio.comum import ErroDominio
from app.serializacao import serializar
from .repository import (
    EstadoOcorrenciaIncompativel,
    OcorrenciaNaoEncontrada,
    RepositorioOcorrencias,
)
from .validacoes import validar_aceitacao, validar_cadastro


class ErroOcorrencia(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status, self.campos = status, list(campos)


class ServicoOcorrencias:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio or RepositorioOcorrencias()
        self.relogio = relogio

    def _id(self, valor, campo):
        if not isinstance(valor, str) or not ObjectId.is_valid(valor):
            raise ErroOcorrencia("ID inválido", 400, [campo])
        return ObjectId(valor)

    def _obra(self, obra_id, autor):
        obra = self.repositorio.buscar_obra(obra_id)
        if obra is None or (obra.get("autor") and str(obra["autor"]) != autor):
            raise ErroOcorrencia("Obra não encontrada", 404, ["obra_id"])
        return obra

    def _contexto(self, documento, autor):
        self._obra(documento.get("obra_id"), autor)
        marco_id = documento.get("marco_id")
        if marco_id is not None:
            marco = self.repositorio.buscar_marco(marco_id)
            if marco is None or marco.get("obra_id") != documento["obra_id"]:
                raise ErroOcorrencia("Marco não encontrado nesta obra", 404, ["marco_id"])

    def _representar(self, documento):
        item = {campo: documento.get(campo) for campo in (
            "titulo", "descricao", "estado", "obra_id", "marco_id", "responsavel_id", "autor", "data_registro")}
        item["id"] = str(documento["_id"])
        item["aceitacoes"] = documento.get("aceitacoes", [])
        item["midias"] = [{**midia_para_dict(midia),
                          "conteudo": f"/midias/{midia['_id']}/conteudo"}
                         for midia in documento.get("midias", [])]
        return serializar(item)

    def _responsavel(self, trabalhador_id, obra_id, autor):
        trabalhador = self.repositorio.buscar_trabalhador(trabalhador_id)
        if (trabalhador is None
                or str(obra_id) not in {str(v) for v in trabalhador.get("obras", [])}
                or trabalhador.get("construtora_id") and str(trabalhador["construtora_id"]) != autor):
            raise ErroOcorrencia("Responsável não encontrado nesta obra", 404, ["responsavel_id"])

    def cadastrar(self, obra_id, dados, autor, arquivos=()):
        obra_id = self._id(obra_id, "obra_id")
        try:
            dados = validar_cadastro(dados)
        except ErroDominio as erro:
            raise ErroOcorrencia(str(erro), 422, erro.campos) from erro
        documento = {"_id": ObjectId(), "obra_id": obra_id, "autor": autor,
                     "data_registro": self.relogio.agora() if self.relogio else datetime.now(timezone.utc),
                     **{campo: dados[campo] for campo in ("titulo", "descricao", "estado")},
                     "marco_id": None, "responsavel_id": None, "aceitacoes": [], "midias": []}
        if dados.get("marco_id") not in (None, ""):
            documento["marco_id"] = self._id(dados["marco_id"], "marco_id")
        self._contexto(documento, autor)
        if dados.get("responsavel_id") not in (None, ""):
            trabalhador_id = self._id(dados["responsavel_id"], "responsavel_id")
            self._responsavel(trabalhador_id, obra_id, autor)
            documento["responsavel_id"] = trabalhador_id
        arquivos = list(arquivos)
        if len(arquivos) > 5:
            raise ErroOcorrencia("Envie até cinco arquivos", 422, ["midias"])
        operacao = None

        def salvar(midias):
            documento["midias"] = [{**midia, "_id": ObjectId(), "ocorrencia_id": documento["_id"],
                                    "data_envio": documento["data_registro"]} for midia in midias]
            # Revalida o contexto após o envio, antes da escrita de negócio.
            self._contexto(documento, autor)
            if documento["responsavel_id"] is not None:
                self._responsavel(documento["responsavel_id"], obra_id, autor)
            try:
                self.repositorio.inserir(documento)
            except WriteError:
                raise  # Rejeição confirmada permite compensar os arquivos.
            except PyMongoError:
                # Timeout de escrita pode ter ocorrido após o commit no servidor.
                raise ResultadoPersistenciaIndeterminado(
                    [midia["referencia_externa"] for midia in midias]) from None
            if operacao is not None:
                try:
                    self.repositorio.concluir_operacao(operacao.id)
                except PyMongoError:
                    # Ocorrência já confirmada. Reconciliação preserva suas referências.
                    pass
            return self._representar(documento)

        if not arquivos:
            return salvar([])
        try:
            midias = ServicoMidias()
        except ValueError:
            raise ErroOcorrencia("O armazenamento de evidências não está configurado corretamente", 503) from None
        operacao = OperacaoUpload(self.repositorio, documento["_id"], "ocorrencia",
                                  campo_vinculo="ocorrencia_id")
        return operacao.executar(midias, arquivos, salvar)

    def listar(self, obra_id, autor):
        obra_id = self._id(obra_id, "obra_id")
        self._obra(obra_id, autor)
        return {"ocorrencias": [self._representar(item) for item in self.repositorio.listar(obra_id)]}

    def consultar(self, ocorrencia_id, autor):
        item = self.repositorio.buscar(self._id(ocorrencia_id, "ocorrencia_id"))
        if item is None:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrencia_id"])
        self._contexto(item, autor)
        return self._representar(item)

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
