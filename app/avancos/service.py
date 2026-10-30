"""Registro e leitura de avanços de marcos."""

from datetime import datetime, timezone
import logging
import hashlib
import json
import re
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza

from . import repository
from .acesso_midias import midia_para_dict
from .midias import ResultadoPersistenciaIndeterminado, ServicoMidias
from .validacoes import ErroAvanco, validar_campos

logger = logging.getLogger(__name__)


def _id(valor, campo):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroAvanco("Identificador inválido", 400, [campo]) from None


def _marco(valor):
    identificador = _id(valor, "marco_id")
    if repository.buscar_marco(identificador) is None:
        raise ErroAvanco("Marco não encontrado", 404, ["marco_id"])
    return identificador


def _representar(documento, documentos_midias=None):
    instante = documento["instante_registro"]
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    midias = []
    if documentos_midias is None:
        documentos_midias = repository.consultar_midias(documento["_id"])
    for item in documentos_midias:
        midia = midia_para_dict(item)
        midia["conteudo"] = f"/midias/{midia['id']}/conteudo"
        midias.append(midia)
    return {
        "id": str(documento["_id"]),
        "marco_id": str(documento["marco_id"]),
        "data": documento["data"],
        "descricao": documento["descricao"],
        "estado": documento["estado"],
        "autor": documento["autor"],
        "instante_registro": instante.isoformat(),
        "midias": midias,
    }


class AvancoReutilizado(Exception):
    def __init__(self, avanco_id):
        self.avanco_id = avanco_id


def criar_avanco(marco_id, formulario, arquivos, autor, chave=None):
    if chave is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", chave):
        raise ErroAvanco("Idempotency-Key inválida", 422, ["Idempotency-Key"])
    marco = _marco(marco_id)
    campos = validar_campos(formulario, arquivos)
    instante = datetime.now(timezone.utc)
    instante = instante.replace(microsecond=instante.microsecond // 1000 * 1000)
    documento = {
        "_id": ObjectId(),
        "marco_id": marco,
        **campos,
        "estado": "rascunho",
        "autor": autor,
        "instante_registro": instante,
    }
    operacao_id = hashlib.sha256(f"{autor}:{chave or uuid4().hex}".encode()).hexdigest()
    operacao_criada = False

    def reservar(validados):
        nonlocal operacao_criada
        assinatura = {
            "marco": str(marco),
            **campos,
            "arquivos": [
                {
                    "nome": item.nome,
                    "tipo": item.tipo,
                    "conteudo": hashlib.sha256(item.conteudo).hexdigest(),
                }
                for item in validados
            ],
        }
        impressao = hashlib.sha256(
            json.dumps(assinatura, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        try:
            repository.criar_operacao(
                {
                    "_id": operacao_id,
                    "avanco_id": documento["_id"],
                    "estado": "pendente",
                    "referencias": [],
                    "impressao": impressao,
                    "iniciado_em": instante,
                }
            )
            operacao_criada = True
        except DuplicateKeyError:
            anterior = repository.buscar_operacao(operacao_id)
            if anterior is None or anterior.get("impressao") != impressao:
                raise ErroAvanco(
                    "Chave já usada com outros dados", 409, ["Idempotency-Key"]
                ) from None
            if anterior.get("estado") == "concluida":
                raise AvancoReutilizado(anterior["avanco_id"]) from None
            raise ErroAvanco(
                "Operação pendente de verificação; não repita com outra chave",
                409,
                ["Idempotency-Key"],
            ) from None

    def salvar(enviados):
        midias = [
            {
                **item,
                "_id": ObjectId(),
                "avanco_id": documento["_id"],
                "data_envio": instante,
            }
            for item in enviados
        ]
        try:
            repository.salvar_com_midias(documento, midias, operacao_id)
        except repository.MarcoRemovido:
            raise ErroAvanco("Marco não encontrado", 404, ["marco_id"]) from None
        except PyMongoError as erro:
            if erro.has_error_label("UnknownTransactionCommitResult"):
                referencias = [item["referencia_externa"] for item in midias]
                logger.error(
                    "Commit indeterminado para avanço %s; referências para reconciliação: %s",
                    documento["_id"],
                    referencias,
                )
                raise ResultadoPersistenciaIndeterminado(referencias) from None
            raise
        return documento, midias

    try:
        servico_midias = ServicoMidias()
    except ValueError:
        raise ErroArmazenamento(
            "O armazenamento não está configurado corretamente"
        ) from None
    try:
        resultado, midias = servico_midias.executar_com_midias(
            arquivos,
            salvar,
            antes_envio=reservar,
            registrar_referencia=lambda referencia: repository.registrar_referencia(
                operacao_id, referencia
            ),
        )
    except AvancoReutilizado as anterior:
        return consultar_avanco(str(anterior.avanco_id))
    except (ResultadoPersistenciaIndeterminado, ErroLimpeza):
        raise
    except Exception:
        if operacao_criada:
            try:
                repository.remover_operacao_pendente(operacao_id)
            except PyMongoError:
                logger.error("Operação pendente de reconciliação: %s", operacao_id)
        raise
    return _representar(resultado, midias)


def consultar_avanco(avanco_id):
    documento = repository.buscar_avanco(_id(avanco_id, "avanco_id"))
    if documento is None or documento.get("estado") == repository.ESTADO_EXCLUSAO:
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    return _representar(documento)


def consultar_avancos(marco_id):
    marco = _marco(marco_id)
    return [_representar(item) for item in repository.listar_avancos(marco)]

from .validacoes import normalizar_edicao, validar_edicao
from .revisoes import ConflitoRascunho
from app.mudanças.ocorrencias.historico.validacoes import validar_midias


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
