"""Edição e exclusão de rascunhos com retenção das mídias compartilhadas."""

from datetime import timedelta
from uuid import uuid4
import logging

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from app.integracoes.armazenamento import ErroArmazenamento
from app.dominio.avancos import Avanco
from app.dominio.comum import ErroDominio, Relogio
from app.publicacoes.validacoes import validar_midias
from . import midias, repository
from .midias import ErroMidia, ServicoMidias
from .revisoes import ConflitoRascunho
from .validacoes import normalizar_edicao, validar_avanco, validar_edicao
from app.serializacao import serializar

TEMPO_BLOQUEIO = timedelta(minutes=5)
logger = logging.getLogger(__name__)


class ErroAvanco(Exception):
    def __init__(self, mensagem, status, campos=(), *, codigo="AVANCO_INVALIDO", pendentes=None):
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo
        self.campos, self.pendentes = list(campos), pendentes


class ServicoAvancos:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.relogio = relogio if relogio is not None else Relogio()

    def _conflito(self):
        return ErroAvanco("O avanço foi alterado ou há uma exclusão em andamento. Tente novamente",
                          409, ["avanco_id"], codigo="CONFLITO_EXCLUSAO")

    def excluir_rascunho(self, avanco_id):
        identificador = self._identificar_avanco(avanco_id)
        documento = self.repositorio.buscar_avanco(identificador)
        if documento is None:
            raise ErroAvanco(
                "Avanço não encontrado", 404, ["avanco_id"],
                codigo="AVANCO_NAO_ENCONTRADO",
            )
        if "publicacao" in documento or documento.get("estado") not in {
            "rascunho", self.repositorio.ESTADO_EXCLUSAO,
        }:
            raise ErroAvanco(
                "Somente rascunhos podem ser excluídos por esta rota", 409,
                ["estado"], codigo="AVANCO_NAO_E_RASCUNHO",
            )

        token = uuid4().hex
        agora = self.relogio.agora()
        try:
            if documento["estado"] == "rascunho":
                arquivos = midias.preparar_limpeza(
                    self.repositorio.consultar_midias_para_limpeza(identificador)
                )
                operacao = self.repositorio.iniciar_exclusao(
                    documento, arquivos, token, agora, agora + TEMPO_BLOQUEIO
                )
            else:
                operacao = self.repositorio.retomar_exclusao(
                    identificador, token, agora, agora + TEMPO_BLOQUEIO
                )
        except ConflitoRascunho:
            raise self._conflito() from None
        if operacao is None:
            raise self._conflito()

        concluido = False
        try:
            # Incorpora tarefas antigas também ao retomar diários criados antes
            # desta correção. O diário só é reduzido após confirmação do provedor.
            conhecidas = {item["chave"] for item in operacao["exclusao"]["arquivos"]}
            extras = [
                item for item in midias.preparar_limpeza(
                    self.repositorio.consultar_midias_para_limpeza(identificador)
                ) if item["chave"] not in conhecidas
            ]
            if extras:
                if not self.repositorio.acrescentar_pendencias(identificador, token, extras):
                    raise self._conflito()
            pendentes = operacao["exclusao"]["pendentes"] + extras

            self.repositorio.validar_referencias_das_midias(
                identificador, self.repositorio.consultar_midias(identificador)
            )
            for arquivo in pendentes:
                if not self.repositorio.renovar_exclusao(
                    identificador, token, self.relogio.agora() + TEMPO_BLOQUEIO
                ):
                    raise self._conflito()
                if not self.repositorio.arquivo_tem_outras_referencias(identificador, arquivo):
                    if not self.repositorio.renovar_exclusao(
                        identificador, token, self.relogio.agora() + TEMPO_BLOQUEIO
                    ):
                        raise self._conflito()
                    try:
                        midias.remover_arquivo(arquivo["referencia"])
                    except (ErroArmazenamento, ValueError):
                        self.repositorio.registrar_falha_limpeza(
                            identificador, token, self.relogio.agora()
                        )
                        continue
                if not self.repositorio.concluir_arquivo(identificador, token, arquivo["chave"]):
                    raise self._conflito()

            atual = self.repositorio.buscar_avanco(identificador)
            if atual is None or atual.get("exclusao", {}).get("token") != token:
                raise self._conflito()
            conhecidas = {item["chave"] for item in atual["exclusao"]["arquivos"]}
            novas = [
                item for item in midias.preparar_limpeza(
                    self.repositorio.consultar_midias_para_limpeza(identificador)
                ) if item["chave"] not in conhecidas
            ]
            if novas:
                if not self.repositorio.acrescentar_pendencias(identificador, token, novas):
                    raise self._conflito()
            quantidade = len(atual["exclusao"]["pendentes"]) + len(novas)
            if quantidade:
                raise ErroAvanco(
                    "Exclusão ainda não concluída. Repita a requisição para retomar a limpeza",
                    503, ["midias"], codigo="LIMPEZA_PENDENTE", pendentes=quantidade,
                )
            if not self.repositorio.renovar_exclusao(
                identificador, token, self.relogio.agora() + TEMPO_BLOQUEIO
            ):
                raise self._conflito()
            if not self.repositorio.finalizar_exclusao(identificador, token):
                raise self._conflito()
            concluido = True
        except ConflitoRascunho:
            raise self._conflito() from None
        finally:
            if not concluido:
                self.repositorio.liberar_exclusao(identificador, token)

    def _identificar_avanco(self, valor):
        if not isinstance(valor, (str, ObjectId)):
            raise ErroAvanco(
                "Identificador do avanço inválido",
                400,
                ["avanco_id"],
            )

        try:
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroAvanco(
                "Identificador do avanço inválido",
                400,
                ["avanco_id"],
            ) from None

    def _preparar_edicao(self, avanco_id, dados, arquivos=()):
        identificador = self._identificar_avanco(avanco_id)
        arquivos = list(arquivos)

        documento = self.repositorio.buscar_avanco(identificador)

        if documento is None:
            raise ErroAvanco(
                "Avanço não encontrado",
                404,
                ["avanco_id"],
            )

        entidade = Avanco.de_documento(documento)
        try:
            entidade.exigir_rascunho()
        except ErroDominio as erro:
            raise ErroAvanco(str(erro), 409, erro.campos) from erro

        erro = validar_edicao(
            dados,
            possui_novas_midias=bool(arquivos),
        )

        if erro is not None:
            mensagem, campos = erro
            raise ErroAvanco(mensagem, 422, campos)

        normalizados = normalizar_edicao(dados)

        midias_anteriores = self.repositorio.consultar_midias(
            identificador
        )

        ids_anteriores = {
            midia["_id"]
            for midia in midias_anteriores
        }

        if "midias_manter" in normalizados:
            ids_manter = set(normalizados["midias_manter"])
        else:
            ids_manter = ids_anteriores.copy()

        if not ids_manter.issubset(ids_anteriores):
            raise ErroAvanco(
                "Selecione somente mídias vinculadas a este avanço",
                422,
                ["midias_manter"],
            )

        try:
            entidade.validar_midias_finais(len(ids_manter) + len(arquivos))
        except ErroDominio as erro:
            raise ErroAvanco(str(erro), 422, erro.campos) from erro

        mantidas = [
            midia
            for midia in midias_anteriores
            if midia["_id"] in ids_manter
        ]

        alteracoes = {
            campo: normalizados[campo]
            for campo in ("data", "descricao")
            if campo in normalizados
        }

        return {
            "documento": documento,
            "alteracoes": alteracoes,
            "midias_anteriores": midias_anteriores,
            "ids_manter": ids_manter,
            "mantidas": mantidas,
            "arquivos": arquivos,
        }

    def editar_rascunho(self,
        avanco_id,
        dados,
        arquivos=(),
        *,
        servico_midias=None,
    ):
        preparacao = self._preparar_edicao(
            avanco_id,
            dados,
            arquivos,
        )

        mantidas = preparacao["mantidas"]

        # A lista pode estar vazia se o usuário substituir
        # todas as mídias existentes por arquivos novos.
        if mantidas and not validar_midias(mantidas):
            raise ErroAvanco(
                "Existem mídias inválidas entre as selecionadas",
                422,
                ["midias_manter"],
            )

        if servico_midias is None:
            try:
                servico_midias = ServicoMidias()
            except (ErroArmazenamento, ValueError):
                raise ErroAvanco(
                    "O armazenamento de mídias não está disponível "
                    "ou está configurado incorretamente",
                    503,
                    ["midias"],
                ) from None

        # Confirma que as mídias mantidas continuam recuperáveis.
        # Faz isso antes de enviar os arquivos novos.
        for midia in mantidas:
            try:
                servico_midias.armazenamento.obter_conteudo(
                    midia["referencia_externa"],
                    midia["tamanho"],
                )
            except ErroArmazenamento as erro:
                if erro.status in (404, 422):
                    raise ErroAvanco(
                        "Uma mídia selecionada não está disponível "
                        "no armazenamento",
                        422,
                        ["midias_manter"],
                    ) from None

                raise ErroAvanco(
                    "Não foi possível confirmar as mídias "
                    "no armazenamento",
                    503,
                    ["midias"],
                ) from None

        def salvar(novas_midias):
            midias_finais = mantidas + novas_midias

            if not validar_midias(midias_finais):
                raise ErroAvanco(
                    "O avanço precisa manter um conjunto "
                    "de mídias válido e não vazio",
                    422,
                    ["midias"],
                )

            return self.repositorio.salvar_edicao(
                documento=preparacao["documento"],
                alteracoes=preparacao["alteracoes"],
                midias_anteriores=preparacao["midias_anteriores"],
                ids_manter=preparacao["ids_manter"],
                novas_midias=novas_midias,
            )

        try:
            salvo, removidas = servico_midias.executar_com_midias(
                preparacao["arquivos"],
                salvar,
                permitir_sem_novos=True,
            )
        except ConflitoRascunho:
            raise ErroAvanco(
                "O avanço foi alterado ou publicado durante a edição; "
                "consulte novamente antes de editar",
                409,
                ["avanco_id"],
            ) from None

        resposta = {
            "id": str(salvo["_id"]),
            "data": salvo.get("data"),
            "descricao": salvo.get("descricao"),
            "estado": salvo["estado"],
            "revisao": salvo["revisao"],
        }

        self._limpar_apos_edicao(servico_midias, removidas)

        return resposta

    def _limpar_apos_edicao(self, servico_midias, removidas):
        for midia in removidas:
            referencia = midia.get("referencia_externa")

            if not isinstance(referencia, dict):
                logger.warning(
                    "Limpeza pendente: mídia sem referência válida. "
                    "midia_id=%s",
                    midia["_id"],
                )
                continue

            em_uso = False

            def verificar_referencia(referencia_consultada):
                nonlocal em_uso

                em_uso = self.repositorio.referencia_em_uso(
                    referencia_consultada,
                    ids_midias=[midia["_id"]],
                )

                return em_uso

            pendentes = servico_midias.limpar_sem_referencias(
                [midia],
                verificar_referencia,
            )

            if em_uso:
                # Preserva o arquivo e a tarefa para reavaliação.
                continue

            if pendentes:
                logger.warning(
                    "Não foi possível concluir a limpeza. "
                    "midia_id=%s",
                    midia["_id"],
                )
                continue

            try:
                self.repositorio.concluir_limpeza(midia["_id"])
            except PyMongoError:
                logger.warning(
                    "Arquivo removido, mas a tarefa de limpeza "
                    "continua pendente. midia_id=%s",
                    midia["_id"],
                )


    def _id(self, valor, campo):
        try:
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroAvanco("Identificador inválido", 400, [campo]) from None

    def _representar(self, documento):
        midias = documento.get("midias")
        if midias is None:
            midias = self.repositorio.consultar_midias(documento["_id"])
        return {
            "id": str(documento["_id"]), "marco_id": str(documento["marco_id"]),
            "data": documento["data"], "descricao": documento["descricao"],
            "estado": documento["estado"], "autor": documento["autor"],
            "data_registro": serializar(documento["data_registro"]).replace("+00:00", "Z"),
            "midias": [{k: m[k] for k in ("tipo", "nome", "tamanho", "mime")} for m in midias],
        }

    def criar_avanco(self, marco_id, dados, arquivos, autor, servico_midias=None):
        marco_oid = self._id(marco_id, "marco_id")
        campos = validar_avanco(dados)
        if campos:
            raise ErroAvanco("Informe uma data válida e uma descrição", 422, campos)
        if not self.repositorio.marco_existe(marco_oid):
            raise ErroAvanco("Marco não encontrado", 404, ["marco_id"])
        arquivos = list(arquivos)
        if not arquivos:
            raise ErroMidia("Envie ao menos uma foto, vídeo ou documento")
        servico = servico_midias if servico_midias is not None else ServicoMidias()
        documento_base = {
            "marco_id": marco_oid, "data": dados["data"], "descricao": dados["descricao"].strip(),
            "estado": "rascunho", "autor": autor, "data_registro": self.relogio.agora(),
        }
        def salvar(midias):
            documento = dict(documento_base)
            return self.repositorio.inserir_avanco_com_midias(documento, midias), documento
        identifier, documento = servico.executar_com_midias(arquivos, salvar)
        documento["_id"] = identifier
        return self._representar(documento)

    def consultar_avanco(self, avanco_id):
        oid = self._id(avanco_id, "avanco_id")
        documento = self.repositorio.buscar_avanco(oid)
        if documento is None:
            raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
        return self._representar(documento)

    def consultar_avancos(self, marco_id):
        oid = self._id(marco_id, "marco_id")
        if not self.repositorio.marco_existe(oid):
            raise ErroAvanco("Marco não encontrado", 404, ["marco_id"])
        return [self._representar(item) for item in self.repositorio.listar_avancos(oid)]

_servico = ServicoAvancos()

# Fachada para consumidores anteriores à refatoração.
_conflito = _servico._conflito
excluir_rascunho = _servico.excluir_rascunho
_identificar_avanco = _servico._identificar_avanco
_preparar_edicao = _servico._preparar_edicao
editar_rascunho = _servico.editar_rascunho
_limpar_apos_edicao = _servico._limpar_apos_edicao

criar_avanco = _servico.criar_avanco
consultar_avanco = _servico.consultar_avanco
consultar_avancos = _servico.consultar_avancos
