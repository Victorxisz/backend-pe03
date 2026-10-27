"""Regras de negócio do cadastro de marcos."""

from bson import ObjectId
from bson.errors import InvalidId
from .dependencias import cria_ciclo

from . import repository
from .validacoes import validar_marco

MAX_TENTATIVAS_DEPENDENCIA = 5

class ErroMarco(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def criar_marco(obra_id, dados):
    try:
        object_id_obra = ObjectId(obra_id)
    except (InvalidId, TypeError):
        raise ErroMarco("ID da obra inválido", 400, ["obra_id"])

    erro = validar_marco(dados)
    if erro:
        mensagem, campos = erro
        raise ErroMarco(mensagem, 422, campos)

    if not repository.obra_existe(object_id_obra):
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

    documento = {
        "obra_id": object_id_obra,
        "nome": dados["nome"].strip(),
        "descricao": dados["descricao"].strip(),
        "inicio_previsto": dados["inicio_previsto"],
        "fim_previsto": dados["fim_previsto"],
        "estado": "a iniciar",
    }
    identifier = repository.inserir_marco(documento)
    return {"id": str(identifier), **{k: v for k, v in documento.items() if k not in ("obra_id", "_id")},
            "obra_id": str(object_id_obra)}

def _converter_id(valor, campo):
    if not isinstance(valor, str):
        raise ErroMarco("Identificador inválido", 400, [campo])

    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroMarco("Identificador inválido", 400, [campo])


def _buscar_marco(marco_id, campo="marco_id"):
    marco = repository.buscar_marco_por_id(marco_id)

    if marco is None:
        raise ErroMarco("Marco não encontrado", 404, [campo])

    return marco


def _buscar_contexto_dependencias(marco_id):
    marco = _buscar_marco(marco_id)
    obra = repository.buscar_obra_por_id(marco["obra_id"])

    if obra is None:
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

    return obra, obra.get("dependencias_marcos", [])


def _serializar_dependencia(vinculo):
    return {
        "id": str(vinculo["_id"]),
        "marco_id": str(vinculo["marco_id"]),
        "depende_de_id": str(vinculo["depende_de_id"]),
    }


def listar_dependencias(marco_id):
    object_id_marco = _converter_id(marco_id, "marco_id")
    obra, vinculos = _buscar_contexto_dependencias(object_id_marco)

    vinculos_do_marco = [
        vinculo
        for vinculo in vinculos
        if vinculo["marco_id"] == object_id_marco
    ]

    if not vinculos_do_marco:
        return []

    marcos = repository.buscar_marcos_da_obra(obra["_id"])

    nomes = {
        marco["_id"]: marco["nome"]
        for marco in marcos
    }

    return [
        {
            **_serializar_dependencia(vinculo),
            "marco_nome": nomes.get(vinculo["marco_id"]),
            "depende_de_nome": nomes.get(vinculo["depende_de_id"]),
        }
        for vinculo in vinculos_do_marco
    ]


def criar_dependencia(marco_id, dados):
    object_id_marco = _converter_id(marco_id, "marco_id")

    if not isinstance(dados, dict):
        raise ErroMarco(
            "Informe um objeto JSON com depende_de_id",
            422,
            ["depende_de_id"],
        )

    depende_de_id = dados.get("depende_de_id")

    if not isinstance(depende_de_id, str) or not depende_de_id.strip():
        raise ErroMarco(
            "Informe o marco do qual este marco depende",
            422,
            ["depende_de_id"],
        )

    object_id_destino = _converter_id(depende_de_id, "depende_de_id")

    for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
        obra, vinculos = _buscar_contexto_dependencias(object_id_marco)
        destino = _buscar_marco(object_id_destino, "depende_de_id")

        if destino["obra_id"] != obra["_id"]:
            raise ErroMarco(
                "Os marcos devem pertencer à mesma obra",
                409,
                ["depende_de_id"],
            )

        if object_id_marco == object_id_destino:
            raise ErroMarco(
                "Um marco não pode depender de si mesmo",
                409,
                ["depende_de_id"],
            )

        duplicada = any(
            vinculo["marco_id"] == object_id_marco
            and vinculo["depende_de_id"] == object_id_destino
            for vinculo in vinculos
        )

        if duplicada:
            raise ErroMarco(
                "Esta dependência já existe",
                409,
                ["depende_de_id"],
            )

        if cria_ciclo(vinculos, object_id_marco, object_id_destino):
            raise ErroMarco(
                "Esta dependência criaria um ciclo",
                409,
                ["depende_de_id"],
            )

        novo_vinculo = {
            "_id": ObjectId(),
            "marco_id": object_id_marco,
            "depende_de_id": object_id_destino,
        }

        if repository.substituir_dependencias(
            obra,
            [*vinculos, novo_vinculo],
        ):
            return _serializar_dependencia(novo_vinculo)

    raise ErroMarco(
        "As dependências foram alteradas por outra requisição. Tente novamente",
        409,
    )


def remover_dependencia(marco_id, dependencia_id):
    object_id_marco = _converter_id(marco_id, "marco_id")
    object_id_dependencia = _converter_id(dependencia_id, "dependencia_id")

    for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
        obra, vinculos = _buscar_contexto_dependencias(object_id_marco)

        vinculo = next(
            (
                item
                for item in vinculos
                if item["_id"] == object_id_dependencia
                and item["marco_id"] == object_id_marco
            ),
            None,
        )

        if vinculo is None:
            raise ErroMarco(
                "Dependência não encontrada neste marco",
                404,
                ["dependencia_id"],
            )

        restantes = [
            item
            for item in vinculos
            if item["_id"] != object_id_dependencia
        ]

        if repository.substituir_dependencias(obra, restantes):
            return

    raise ErroMarco(
        "As dependências foram alteradas por outra requisição. Tente novamente",
        409,
    )

def listar_marcos_da_obra(obra_id):
    object_id_obra = _converter_id(obra_id, "obra_id")

    if not repository.obra_existe(object_id_obra):
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

    marcos = repository.buscar_marcos_da_obra(object_id_obra)

    return [
        {
            "id": str(marco["_id"]),
            "nome": marco["nome"],
            "estado": marco["estado"],
        }
        for marco in marcos
    ]