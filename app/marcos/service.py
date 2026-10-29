"""Regras de negócio de marcos e suas dependências."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .dependencias import cria_ciclo
from .validacoes import validar_alteracao_estado, validar_marco

MAX_TENTATIVAS_DEPENDENCIA = 5


class ErroMarco(Exception):
    def __init__(self, mensagem, status, campos=(), detalhes=None):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.detalhes = detalhes or {}


def criar_marco(obra_id, dados):
    object_id_obra = _identificar_id(obra_id, "obra_id")
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
    return {
        "id": str(identifier),
        "obra_id": str(object_id_obra),
        **{
            key: documento[key]
            for key in (
                "nome", "descricao", "inicio_previsto", "fim_previsto", "estado"
            )
        },
    }


def alterar_estado_marco(marco_id, dados, autor):
    object_id = _identificar_id(marco_id, "marco_id")
    erro = validar_alteracao_estado(dados)
    if erro:
        mensagem, campos = erro
        raise ErroMarco(mensagem, 422, campos)

    marco = repository.buscar_marco(object_id)
    if not marco:
        raise ErroMarco("Marco não encontrado", 404, ["marco_id"])

    novo_estado = dados["estado"]
    anterior = marco.get("estado", "a iniciar")
    if anterior == novo_estado:
        return {"id": str(object_id), "estado": anterior}

    try:
        pendentes = (
            repository.dependencias_pendentes(marco)
            if novo_estado == "concluído"
            else []
        )
    except repository.DependenciaInconsistente as erro:
        raise ErroMarco(
            "As dependências do marco precisam ser corrigidas",
            409,
            detalhes={"codigo": "DEPENDENCIA_INCONSISTENTE"},
        ) from erro
    
    if pendentes and dados.get("confirmar_dependencias") is not True:
        raise ErroMarco("Há dependências pendentes", 409, [], {
            "codigo": "DEPENDENCIAS_PENDENTES", "dependencias": pendentes
        })

    evento = {
        "tipo": "estado_marco",
        "alvo": {"tipo": "marco", "id": object_id},
        "estado_anterior": anterior,
        "estado_novo": novo_estado,
        "motivo": dados["motivo"].strip(),
        "autor": autor,
        "instante": datetime.now(timezone.utc),
        "confirmou_dependencias_pendentes": bool(
            pendentes and dados.get("confirmar_dependencias") is True
        ),
        "dependencias_pendentes": pendentes,
    }
    try:
        repository.salvar_estado_com_historico(object_id, anterior, novo_estado, evento)
    except repository.EstadoMarcoAlterado:
        raise ErroMarco(
            "O estado do marco foi alterado por outra requisição; atualize os dados e tente novamente",
            409,
            [],
            {"codigo": "MARCO_ALTERADO_CONCORRENTEMENTE"},
        )
    return {"id": str(object_id), "estado": novo_estado}


def listar_dependencias(marco_id):
    object_id = _identificar_id(marco_id, "marco_id")
    marco, obra = _obter_marco_e_obra(object_id)
    dependencias = []
    for vinculo in obra.get("dependencias_marcos", []):
        if vinculo["marco_id"] != object_id:
            continue
        destino = repository.buscar_marco_por_id(vinculo["depende_de_id"])
        if destino is None:
            continue
        dependencias.append(_serializar_dependencia(vinculo, marco, destino))
    dependencias.sort(key=lambda item: item["id"])
    return dependencias


def criar_dependencia(marco_id, dados):
    object_id = _identificar_id(marco_id, "marco_id")
    if not isinstance(dados, dict) or set(dados) != {"depende_de_id"}:
        raise ErroMarco("Envie somente o campo 'depende_de_id'", 422, ["depende_de_id"])
    destino_id = _identificar_id(dados["depende_de_id"], "depende_de_id")

    marco, obra = _obter_marco_e_obra(object_id)
    destino = repository.buscar_marco_por_id(destino_id)
    if destino is None:
        raise ErroMarco("Marco de dependência não encontrado", 404, ["depende_de_id"])
    if destino.get("obra_id") != marco.get("obra_id"):
        raise ErroMarco("A dependência deve pertencer à mesma obra", 409, ["depende_de_id"])

    for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
        vinculos = list(obra.get("dependencias_marcos", []))
        if any(
            item["marco_id"] == object_id and item["depende_de_id"] == destino_id
            for item in vinculos
        ):
            raise ErroMarco("Esta dependência já existe", 409, ["depende_de_id"])
        if cria_ciclo(vinculos, object_id, destino_id):
            raise ErroMarco("A dependência formaria um ciclo", 409, ["depende_de_id"])

        vinculo = {
            "_id": ObjectId(),
            "marco_id": object_id,
            "depende_de_id": destino_id,
        }
        novos_vinculos = vinculos + [vinculo]
        if repository.substituir_dependencias(obra, novos_vinculos):
            return _serializar_dependencia(vinculo, marco, destino)

        marco, obra = _obter_marco_e_obra(object_id)
        if repository.buscar_marco_por_id(destino_id) is None:
            raise ErroMarco("Marco de dependência não encontrado", 404, ["depende_de_id"])

    raise ErroMarco("As dependências foram alteradas por outra requisição; tente novamente", 409)


def remover_dependencia(marco_id, dependencia_id):
    object_id = _identificar_id(marco_id, "marco_id")
    vinculo_id = _identificar_id(dependencia_id, "dependencia_id")
    _, obra = _obter_marco_e_obra(object_id)

    for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
        vinculos = list(obra.get("dependencias_marcos", []))
        novos_vinculos = [
            item for item in vinculos
            if not (item["_id"] == vinculo_id and item["marco_id"] == object_id)
        ]
        if len(novos_vinculos) == len(vinculos):
            raise ErroMarco("Dependência não encontrada", 404, ["dependencia_id"])
        if repository.substituir_dependencias(obra, novos_vinculos):
            return
        _, obra = _obter_marco_e_obra(object_id)

    raise ErroMarco("As dependências foram alteradas por outra requisição; tente novamente", 409)


def _identificar_id(value, campo):
    if not isinstance(value, (str, ObjectId)) or (isinstance(value, str) and not value.strip()):
        status = 422 if campo == "depende_de_id" else 400
        raise ErroMarco(f"ID inválido: {campo}", status, [campo])
    try:
        return value if isinstance(value, ObjectId) else ObjectId(value)
    except (InvalidId, TypeError):
        raise ErroMarco(f"ID inválido: {campo}", 400, [campo])


def _obter_marco_e_obra(marco_id):
    marco = repository.buscar_marco_por_id(marco_id)
    if marco is None:
        raise ErroMarco("Marco não encontrado", 404, ["marco_id"])
    obra = repository.buscar_obra_por_id(marco["obra_id"])
    if obra is None:
        raise ErroMarco("Obra não encontrada", 404, ["obra_id"])
    return marco, obra


def _serializar_dependencia(vinculo, origem, destino):
    return {
        "id": str(vinculo["_id"]),
        "marco_id": str(vinculo["marco_id"]),
        "depende_de_id": str(vinculo["depende_de_id"]),
        "marco_nome": origem.get("nome", "Marco"),
        "depende_de_nome": destino.get("nome", "Marco"),
    }
