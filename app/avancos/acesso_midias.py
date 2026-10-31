"""Acesso autenticado às referências geradas pelo serviço de envio de mídia."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
from .midias import ErroMidia
from . import repository


TIPOS = {
    "foto": {"image/jpeg", "image/png"},
    "video": {"video/mp4"},
    "documento": {"application/pdf"},
}


def _identificador(valor, campo):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroMidia("ID inválido", 400, "ID_INVALIDO", [campo]) from None


def vinculo_da_midia(documento):
    """Qual registro de negócio guarda a mídia: avanço ou ocorrência, nunca ambos."""
    for campo in repository.COLECAO_DO_VINCULO:
        valor = documento.get(campo)
        if isinstance(valor, ObjectId):
            return campo, valor
    return None, None


def midia_para_dict(documento):
    # Lista fechada: nunca devolve referência externa, URL ou credenciais.
    midia = {campo: documento.get(campo) for campo in ("tipo", "nome", "tamanho")}
    campo_vinculo, vinculo = vinculo_da_midia(documento)
    midia.update(id=str(documento["_id"]),
                 mime=documento.get("mime") or documento.get("formato"), visibilidade="privada")
    if campo_vinculo is not None:
        midia[campo_vinculo] = str(vinculo)
    # Compatibilidade com a representação MIME usada pelas rotas de acesso anteriores.
    midia["formato"] = midia["mime"]
    envio = documento.get("data_envio")
    if isinstance(envio, datetime):
        if envio.tzinfo is None:
            envio = envio.replace(tzinfo=timezone.utc)
        midia["data_envio"] = envio.isoformat()
    return midia


def listar_midias(avanco_id):
    identificador = _identificador(avanco_id, "avanco_id")
    if not repository.avanco_existe(identificador):
        raise ErroMidia("Avanço não encontrado", 404, "AVANCO_NAO_ENCONTRADO", ["avanco_id"])
    return [midia_para_dict(documento) for documento in repository.consultar_midias(identificador)]


def _midia_vinculada(midia_id):
    identificador = _identificador(midia_id, "midia_id")
    documento = repository.buscar_midia_por_id(identificador)
    if documento is not None:
        campo_vinculo, vinculo = vinculo_da_midia(documento)
        if campo_vinculo is not None and repository.vinculo_existe(campo_vinculo, vinculo):
            return documento
    raise ErroMidia("Mídia não encontrada", 404, "MIDIA_NAO_ENCONTRADA", ["midia_id"])


def buscar_midia(midia_id):
    return midia_para_dict(_midia_vinculada(midia_id))


def formato_para_resposta(documento):
    mime = documento.get("mime") or documento.get("formato")
    if mime in TIPOS.get(documento.get("tipo"), set()):
        return mime, documento.get("tipo") in {"foto", "video"}
    return "application/octet-stream", False


def nome_para_resposta(documento):
    nome = documento.get("nome")
    return nome if isinstance(nome, str) and nome.strip() else str(documento["_id"])


def abrir_conteudo(midia_id):
    documento = _midia_vinculada(midia_id)
    referencia = documento.get("referencia_externa")
    if not isinstance(referencia, dict) or referencia.get("provedor") != "cloudinary":
        raise ErroMidia("Referência de armazenamento inválida", 502, "REFERENCIA_INVALIDA", ["midia_id"])
    try:
        conteudo = ArmazenamentoCloudinary().obter_conteudo(referencia, documento.get("tamanho"))
    except ErroArmazenamento as erro:
        if erro.status == 422:
            raise ErroMidia("Referência de armazenamento inválida", 502,
                           "REFERENCIA_INVALIDA", ["midia_id"]) from None
        if erro.status == 404:
            raise ErroMidia("O arquivo desta mídia não está disponível no armazenamento", 502,
                           "CONTEUDO_AUSENTE_NO_PROVEDOR", ["midia_id"]) from None
        raise ErroMidia("Não foi possível acessar o armazenamento de mídias agora", 502,
                       "PROVEDOR_INDISPONIVEL", ["midia_id"]) from None
    except ValueError:
        raise ErroMidia("O armazenamento não está configurado corretamente", 502,
                       "PROVEDOR_NAO_CONFIGURADO", ["midia_id"]) from None
    return documento, conteudo
