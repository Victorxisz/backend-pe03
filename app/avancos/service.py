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
    if documento is None:
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    return _representar(documento)


def consultar_avancos(marco_id):
    marco = _marco(marco_id)
    return [_representar(item) for item in repository.listar_avancos(marco)]
