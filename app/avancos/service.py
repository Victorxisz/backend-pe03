"""Regras de negócio para cadastrar, consultar, editar e excluir rascunhos."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import logging

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from app.config import ConfiguracaoArmazenamento
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento, ErroLimpeza
from app.mudanças.ocorrencias.historico.validacoes import validar_midias
from . import midias, repository
from .midias import ErroMidia, ServicoMidias
from .revisoes import ConflitoRascunho
from .validacoes import normalizar_edicao, validar_avanco, validar_edicao

logger = logging.getLogger(__name__)
TEMPO_BLOQUEIO = timedelta(minutes=5)

class ErroAvanco(Exception):
    def __init__(self, mensagem, status=422, codigo=None, campos=(), pendentes=None):
        if isinstance(codigo, (list, tuple)):
            campos, codigo = codigo, None
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo
        self.campos, self.pendentes = list(campos), pendentes

def _conflito():
    return ErroAvanco("O avanço foi alterado ou há uma exclusão em andamento. Tente novamente",
                      409, "CONFLITO_EXCLUSAO", ["avanco_id"])


def excluir_rascunho(avanco_id):
    try:
        if not isinstance(avanco_id, (str, ObjectId)):
            raise TypeError
        identificador = ObjectId(avanco_id)
    except (InvalidId, TypeError):
        raise ErroAvanco("ID do avanço inválido", 400, "ID_INVALIDO", ["avanco_id"]) from None
    documento = repository.buscar_avanco(identificador)
    if documento is None:
        raise ErroAvanco("Avanço não encontrado", 404, "AVANCO_NAO_ENCONTRADO", ["avanco_id"])
    if "publicacao" in documento or documento.get("estado") not in {"rascunho", repository.ESTADO_EXCLUSAO}:
        raise ErroAvanco("Somente rascunhos podem ser excluídos por esta rota", 409,
                         "AVANCO_NAO_E_RASCUNHO", ["estado"])
    token, agora = uuid4().hex, datetime.now(timezone.utc)
    if documento["estado"] == "rascunho":
        arquivos = midias.preparar_limpeza(repository.consultar_midias(identificador))
        try:
            operacao = repository.iniciar_exclusao(documento, arquivos, token, agora, agora + TEMPO_BLOQUEIO)
        except ConflitoRascunho:
            raise _conflito() from None
    else:
        operacao = repository.retomar_exclusao(identificador, token, agora, agora + TEMPO_BLOQUEIO)
    if operacao is None:
        raise _conflito()

    concluido = False
    try:
        for arquivo in operacao["exclusao"]["pendentes"]:
            if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
                raise _conflito()
            if not repository.arquivo_tem_outras_referencias(identificador, arquivo):
                if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
                    raise _conflito()
                try:
                    midias.remover_arquivo(arquivo["referencia"])
                except (ErroArmazenamento, ValueError):
                    repository.registrar_falha_limpeza(identificador, token, datetime.now(timezone.utc))
                    continue
            if not repository.concluir_arquivo(identificador, token, arquivo["chave"]):
                raise _conflito()

        atual = repository.buscar_avanco(identificador)
        if atual is None or atual.get("exclusao", {}).get("token") != token:
            raise _conflito()
        # Escritores de rascunho devem usar revisoes.registrar_alteracao. Além
        # disso, não descartamos mídias novas que apareceram durante a limpeza.
        conhecidas = {item["chave"] for item in atual["exclusao"]["arquivos"]}
        novas = [item for item in midias.preparar_limpeza(repository.consultar_midias(identificador))
                 if item["chave"] not in conhecidas]
        if novas:
            repository.acrescentar_pendencias(identificador, token, novas)
        quantidade = len(atual["exclusao"]["pendentes"]) + len(novas)
        if quantidade:
            raise ErroAvanco("Exclusão ainda não concluída. Repita a requisição para retomar a limpeza",
                             503, "LIMPEZA_PENDENTE", ["midias"], quantidade)
        if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
            raise _conflito()
        if not repository.finalizar_exclusao(identificador, token):
            raise _conflito()
        concluido = True
    finally:
        if not concluido:
            repository.liberar_exclusao(identificador, token)

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


def _identificar_avanco(valor):
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


def _preparar_edicao(avanco_id, dados, arquivos=()):
    identificador = _identificar_avanco(avanco_id)
    arquivos = list(arquivos)

    documento = repository.buscar_avanco(identificador)

    if documento is None:
        raise ErroAvanco(
            "Avanço não encontrado",
            404,
            ["avanco_id"],
        )

    if (
        documento.get("estado") != "rascunho"
        or "publicacao" in documento
    ):
        raise ErroAvanco(
            "Somente rascunhos sem publicação podem ser editados "
            "por este fluxo",
            409,
            ["estado"],
        )

    erro = validar_edicao(
        dados,
        possui_novas_midias=bool(arquivos),
    )

    if erro is not None:
        mensagem, campos = erro
        raise ErroAvanco(mensagem, 422, campos)

    normalizados = normalizar_edicao(dados)

    midias_anteriores = repository.consultar_midias(
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

    if not ids_manter and not arquivos:
        raise ErroAvanco(
            "O avanço precisa manter pelo menos uma mídia",
            422,
            ["midias_manter"],
        )

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

def editar_rascunho(
    avanco_id,
    dados,
    arquivos=(),
    *,
    servico_midias=None,
):
    preparacao = _preparar_edicao(
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

        return repository.salvar_edicao(
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

    _limpar_apos_edicao(servico_midias, removidas)

    return resposta

def _limpar_apos_edicao(servico_midias, removidas):
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

            em_uso = repository.referencia_em_uso(
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
            repository.concluir_limpeza(midia["_id"])
        except PyMongoError:
            logger.warning(
                "Arquivo removido, mas a tarefa de limpeza "
                "continua pendente. midia_id=%s",
                midia["_id"],
            )
