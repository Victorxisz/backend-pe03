"""Registro e consulta de ocorrências: a obra é obrigatória, o resto é opcional."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app

from app.avancos.acesso_midias import midia_para_dict
from app.avancos.midias import ErroMidia, ServicoMidias
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from . import repository
from .validacoes import validar_registro


class ErroOcorrencia(Exception):
    def __init__(self, mensagem, status, campos=(), codigo="OCORRENCIA_INVALIDA"):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.codigo = codigo


def registrar_ocorrencia(obra_id, dados, arquivos, autor):
    identificador_obra = _identificador(obra_id, "obra_id")
    erro = validar_registro(dados)
    if erro:
        mensagem, campos = erro
        raise ErroOcorrencia(mensagem, 422, campos)
    if repository.buscar_obra(identificador_obra) is None:
        raise ErroOcorrencia("Obra não encontrada", 404, ["obra_id"], "OBRA_NAO_ENCONTRADA")

    documento = {
        "_id": ObjectId(),
        "obra_id": identificador_obra,
        "titulo": dados["titulo"].strip(),
        "descricao": dados["descricao"].strip(),
        "estado": dados["estado"],
        # Marco e responsável são verificados aqui e novamente na gravação.
        "marco_id": _marco_da_obra(dados, identificador_obra),
        "responsavel_id": _responsavel_da_obra(dados, identificador_obra),
        "autor": autor,
        "data_registro": _instante(),
    }

    arquivos = list(arquivos)
    if not arquivos:
        _gravar(documento, [])
        return _representar(documento)

    def salvar(metadados):
        # Chamado apenas depois de todos os envios confirmados pelo provedor.
        midias = [
            {
                **item,
                "_id": ObjectId(),
                "ocorrencia_id": documento["_id"],
                "data_envio": documento["data_registro"],
            }
            for item in metadados
        ]
        _gravar(documento, midias)
        return midias

    try:
        ServicoMidias().executar_com_midias(arquivos, salvar)
    except ErroMidia as erro:
        raise ErroOcorrencia(str(erro), erro.status, erro.campos, erro.codigo) from None
    except ErroLimpeza as erro:
        # Arquivos enviados que ficaram sem uso: a pendência precisa ser rastreável.
        current_app.logger.error(
            "Ocorrência não registrada e %s arquivo(s) pendente(s) de remoção no armazenamento",
            len(erro.pendentes),
        )
        raise ErroOcorrencia(
            "A ocorrência não foi registrada e há arquivos pendentes de remoção",
            503,
            ["midias"],
            "LIMPEZA_PENDENTE",
        ) from None
    except ErroArmazenamento:
        raise ErroOcorrencia(
            "Não foi possível guardar as mídias da ocorrência agora",
            503,
            ["midias"],
            "ARMAZENAMENTO_INDISPONIVEL",
        ) from None
    except ValueError:
        raise ErroOcorrencia(
            "O armazenamento não está configurado corretamente",
            503,
            ["midias"],
            "ARMAZENAMENTO_NAO_CONFIGURADO",
        ) from None
    return _representar(documento)


def consultar_ocorrencias(obra_id):
    identificador = _identificador(obra_id, "obra_id")
    if repository.buscar_obra(identificador) is None:
        raise ErroOcorrencia("Obra não encontrada", 404, ["obra_id"], "OBRA_NAO_ENCONTRADA")
    # Obra sem ocorrências devolve lista vazia; obra inexistente não chega aqui.
    return [_representar(documento) for documento in repository.consultar_por_obra(identificador)]


def consultar_ocorrencia(ocorrencia_id):
    identificador = _identificador(ocorrencia_id, "ocorrencia_id")
    documento = repository.buscar_ocorrencia(identificador)
    # Sem a obra não há contexto: uma ocorrência órfã não é devolvida como válida.
    if (documento is None or not isinstance(documento.get("obra_id"), ObjectId)
            or repository.buscar_obra(documento["obra_id"]) is None):
        raise ErroOcorrencia(
            "Ocorrência não encontrada", 404, ["ocorrencia_id"], "OCORRENCIA_NAO_ENCONTRADA"
        )
    return _representar(documento)


def _gravar(documento, midias):
    try:
        repository.salvar(documento, midias)
    except repository.VinculoAlterado:
        raise ErroOcorrencia(
            "Obra, marco ou responsável foi alterado; refaça o registro",
            409,
            ["obra_id"],
            "VINCULO_ALTERADO",
        ) from None


def _identificador(valor, campo):
    try:
        if not isinstance(valor, (str, ObjectId)):
            raise TypeError
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroOcorrencia("Identificador inválido", 400, [campo], "ID_INVALIDO") from None


def _instante():
    # BSON guarda milissegundos; POST e consulta devem devolver o mesmo instante.
    agora = datetime.now(timezone.utc)
    return agora.replace(microsecond=agora.microsecond // 1000 * 1000)


def _marco_da_obra(dados, obra_id):
    valor = dados.get("marco_id")
    if valor is None:
        return None
    identificador = _identificador(valor, "marco_id")
    marco = repository.buscar_marco(identificador)
    if marco is None or marco.get("obra_id") != obra_id:
        raise ErroOcorrencia(
            "Marco não encontrado nesta obra", 422, ["marco_id"], "MARCO_DE_OUTRA_OBRA"
        )
    return identificador


def _responsavel_da_obra(dados, obra_id):
    """Responsável é um trabalhador do cadastro, sem perfil autenticável próprio."""
    valor = dados.get("responsavel_id")
    if valor is None:
        return None
    identificador = _identificador(valor, "responsavel_id")
    trabalhador = repository.buscar_trabalhador(identificador)
    if trabalhador is None or str(obra_id) not in (trabalhador.get("obras") or []):
        raise ErroOcorrencia(
            "Responsável não encontrado entre os trabalhadores desta obra",
            422,
            ["responsavel_id"],
            "RESPONSAVEL_SEM_VINCULO",
        )
    return identificador


def _representar(documento):
    return {
        "id": str(documento["_id"]),
        "obra_id": str(documento["obra_id"]),
        "titulo": documento.get("titulo"),
        "descricao": documento.get("descricao"),
        "estado": documento.get("estado"),
        "autor": documento.get("autor"),
        "data_registro": _data_registro(documento),
        "marco": _marco_representado(documento),
        "responsavel": _responsavel_representado(documento),
        "midias": _midias_representadas(documento),
        # Registrar como "sem solução" não é aceitação: quem aceita é a UC-16.
        "aceita": documento.get("aceitacao") is not None,
    }


def _data_registro(documento):
    registro = documento.get("data_registro")
    if not isinstance(registro, datetime):
        return None
    if registro.tzinfo is None:
        registro = registro.replace(tzinfo=timezone.utc)
    return registro.isoformat()


def _marco_representado(documento):
    identificador = documento.get("marco_id")
    if not isinstance(identificador, ObjectId):
        return None
    marco = repository.buscar_marco(identificador)
    # Referência preservada, nome nulo: não afirma um vínculo que deixou de existir.
    if marco is None or marco.get("obra_id") != documento.get("obra_id"):
        return {"id": str(identificador), "nome": None}
    return {"id": str(identificador), "nome": marco.get("nome")}


def _responsavel_representado(documento):
    identificador = documento.get("responsavel_id")
    if not isinstance(identificador, ObjectId):
        return None
    trabalhador = repository.buscar_trabalhador(identificador)
    if trabalhador is None:
        return {"id": str(identificador), "nome": None, "cargo": None}
    return {
        "id": str(identificador),
        "nome": trabalhador.get("nome"),
        "cargo": trabalhador.get("cargo"),
    }


def _midias_representadas(documento):
    representadas = []
    for midia in repository.consultar_midias(documento["_id"]):
        item = midia_para_dict(midia)
        item["conteudo"] = f"/midias/{item['id']}/conteudo"
        representadas.append(item)
    return representadas
