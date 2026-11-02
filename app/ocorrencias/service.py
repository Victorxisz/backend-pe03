"""Cadastro, consulta e aceitação formal das ocorrências de uma obra."""

from bson import ObjectId
from pymongo.errors import PyMongoError, WriteError

from app.avancos.acesso_midias import midia_para_dict
from app.avancos.midias import ServicoMidias, ResultadoPersistenciaIndeterminado
from app.avancos.operacoes import OperacaoUpload
from app.dominio.comum import ErroDominio, Relogio
from app.serializacao import serializar
from .repository import (
    ChaveReenvioIncompativel,
    EstadoOcorrenciaIncompativel,
    OcorrenciaNaoEncontrada,
    RepositorioOcorrencias,
)
from .validacoes import validar_aceitacao, validar_cadastro, validar_atualizacao, validar_chave_reenvio


class ErroOcorrencia(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status, self.campos = status, list(campos)


class ServicoOcorrencias:
    def excluir(self, ocorrencia_id, dados, autor, *, previa=False):
        from app.exclusao_registros import excluir_registro
        return excluir_registro("ocorrencia", ocorrencia_id, dados, autor, previa=previa)

    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio or RepositorioOcorrencias()
        self.relogio = relogio if relogio is not None else Relogio()

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
        if documento.get("responsavel_anterior") is not None:
            # P-10: quem respondia antes de o cadastro ser removido (UC-20).
            item["responsavel_anterior"] = documento["responsavel_anterior"]
        item["aceitacoes"] = documento.get("aceitacoes", [])
        item["versao"] = documento.get("versao", 0)
        item["episodio"] = documento.get("episodio", 0)
        item["historico_estados"] = documento.get("historico_estados", [])
        item["aceitacoes_do_estado_atual"] = [
            aceitacao for aceitacao in item["aceitacoes"]
            if documento.get("estado") == "sem solução"
            and aceitacao.get("episodio", 0) == item["episodio"]]
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
                     "data_registro": self.relogio.agora(),
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

    def atualizar(self, ocorrencia_id, dados, autor):
        identificador = self._id(ocorrencia_id, "ocorrencia_id")
        try:
            alteracoes, transicao = validar_atualizacao(dados)
        except ErroDominio as erro:
            raise ErroOcorrencia(str(erro), 422, erro.campos) from erro
        anterior = self.repositorio.buscar(identificador)
        if anterior is None:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrencia_id"])
        self._contexto(anterior, autor)
        if anterior.get("versao", 0) != dados["versao"]:
            raise ErroOcorrencia("A ocorrência foi alterada; consulte novamente antes de salvar", 409, ["versao"])
        for campo in ("marco_id", "responsavel_id"):
            if campo in alteracoes:
                alteracoes[campo] = (None if alteracoes[campo] in (None, "")
                                     else self._id(alteracoes[campo], campo))
        self._contexto({**anterior, **alteracoes}, autor)
        if alteracoes.get("responsavel_id") is not None:
            self._responsavel(alteracoes["responsavel_id"], anterior["obra_id"], autor)
        campos = {campo: valor for campo, valor in alteracoes.items() if anterior.get(campo) != valor}
        evento = None
        if transicao is not None and transicao["estado"] != anterior["estado"]:
            instante = self.relogio.agora()
            evento = {"id": str(ObjectId()), "estado_anterior": anterior["estado"],
                      "novo_estado": transicao["estado"], "motivo": transicao["motivo"],
                      "autor": autor, "instante": instante,
                      "episodio_anterior": anterior.get("episodio", 0),
                      "episodio": anterior.get("episodio", 0) + 1}
            campos["estado"] = transicao["estado"]
        if not campos:
            return self._representar(anterior)
        salvo = self.repositorio.atualizar(anterior, campos, evento)
        if salvo is None:
            raise ErroOcorrencia("A ocorrência foi alterada; consulte novamente antes de salvar", 409, ["versao"])
        return self._representar(salvo)

    def aceitar(self, ocorrencia_id, dados, autor, chave_reenvio=None):
        oid = self._id(ocorrencia_id, "ocorrenciaId")
        try:
            validar_aceitacao(dados)
            validar_chave_reenvio(chave_reenvio)
        except ErroDominio as erro:
            raise ErroOcorrencia(str(erro), 422, erro.campos) from erro
        if not isinstance(autor, str) or not autor:
            raise ErroOcorrencia("Conta autenticada inválida", 401)
        ocorrencia = self.repositorio.buscar(oid)
        if ocorrencia is None:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrenciaId"])
        self._contexto(ocorrencia, autor)
        agora = self.relogio.agora()
        documento = {"id": str(ObjectId()), "justificativa": dados["justificativa"].strip(), "autor": autor, "data": agora}
        if dados.get("medida_compensatoria") is not None:
            documento["medida_compensatoria"] = dados["medida_compensatoria"].strip()
        try:
            salvo, repetida = self.repositorio.aceitar(oid, documento, chave_reenvio, esperado=ocorrencia)
        except OcorrenciaNaoEncontrada:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrenciaId"]) from None
        except EstadoOcorrenciaIncompativel:
            raise ErroOcorrencia("A ocorrência deve continuar sem solução no mesmo episódio; consulte novamente", 409, ["estado"]) from None
        except ChaveReenvioIncompativel:
            raise ErroOcorrencia("Esta chave de reenvio já identifica outra decisão; use uma nova chave", 409, ["Idempotency-Key"]) from None
        item = serializar(salvo.get("aceitacoes", [])[-1])
        return item, repetida

    def listar_aceitacoes(self, ocorrencia_id, autor=None):
        oid = self._id(ocorrencia_id, "ocorrenciaId")
        ocorrencia = self.repositorio.buscar(oid)
        if ocorrencia is None:
            raise ErroOcorrencia("Ocorrência não encontrada", 404, ["ocorrenciaId"])
        if autor is not None:
            self._contexto(ocorrencia, autor)
        return serializar(ocorrencia.get("aceitacoes", []))
