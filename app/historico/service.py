"""Unifica decisões e correções já persistidas, sem produzir novos eventos."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.serializacao import serializar
from app.avancos.service import ErroAvanco
from app.avancos.versoes import reconstruir_versoes
from .repository import RepositorioHistorico


class ErroHistorico(Exception):
    def __init__(self, mensagem, status, campo, *, codigo=None):
        super().__init__(mensagem)
        self.status = status
        self.campos = [campo]
        self.codigo = codigo


def _id(valor, campo):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroHistorico("Identificador inválido", 400, campo) from None


def _instante(valor):
    try:
        if isinstance(valor, str):
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if not isinstance(valor, datetime):
            raise TypeError
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        _indisponivel()


def _indisponivel():
    raise ErroHistorico("Histórico indisponível ou inconsistente", 409, "historico",
                        codigo="HISTORICO_INDISPONIVEL")


def _ordem(evento):
    # Os IDs públicos continuam iguais. Apenas o desempate usa a posição como
    # número, preservando a cadeia quando os instantes têm a mesma precisão BSON.
    partes = evento["id"].split(":")
    if partes[0] == "obra":
        origem = (*partes[:3], int(partes[3]))
    elif partes[0] == "publicacao":
        origem = (*partes[:2], "", int(partes[2]))
    else:
        origem = (partes[0], "", "", 0)
    return datetime.fromisoformat(evento["instante"]), origem


def _campos(evento):
    if "campo" in evento:
        return [evento["campo"]]
    if "estado_anterior" in evento:
        return ["estado"]
    return [campo for campo in ("data", "descricao", "midias")
            if evento["antes"].get(campo) != evento["depois"].get(campo)]


def _normalizar(identificador, obra_id, tipo, alvo, evento, *, comparacao=None):
    try:
        if (not isinstance(tipo, str) or not tipo
                or not isinstance(evento["motivo"], str) or not evento["motivo"].strip()
                or not isinstance(evento["autor"], (str, ObjectId)) or not str(evento["autor"]).strip()):
            _indisponivel()
        return _representar(identificador, obra_id, tipo, alvo, evento, comparacao=comparacao)
    except (KeyError, TypeError, AttributeError):
        _indisponivel()


def _representar(identificador, obra_id, tipo, alvo, evento, *, comparacao=None):
    anterior = evento.get("valor_anterior", evento.get("estado_anterior", evento.get("antes")))
    novo = evento.get("valor_novo", evento.get("estado_novo", evento.get("depois")))
    return {
        "id": identificador, "obra_id": str(obra_id), "tipo": tipo,
        "alvo": {"tipo": alvo["tipo"], "id": str(alvo["id"])},
        "campos": _campos(evento), "antes": serializar(anterior),
        "depois": serializar(novo), "motivo": evento["motivo"],
        "autor": str(evento["autor"]), "instante": _instante(evento["instante"]),
        "consulta": f"/mudancas/{identificador}", "comparacao": comparacao,
    }


class ServicoHistorico:
    def __init__(self, repositorio=None):
        self.repositorio = repositorio if repositorio is not None else RepositorioHistorico()

    def listar(self, obra_id):
        oid = _id(obra_id, "obra_id")
        obra = self.repositorio.buscar_obra(oid)
        if obra is None:
            raise ErroHistorico("Obra não encontrada", 404, "obra_id")
        eventos = []
        for campo in ("historico_mudancas", "historico_estados"):
            historico = obra.get(campo, [])
            if not isinstance(historico, list):
                _indisponivel()
            for indice, evento in enumerate(historico):
                if not isinstance(evento, dict):
                    _indisponivel()
                alvo = evento.get("alvo", {})
                if not isinstance(alvo, dict):
                    _indisponivel()
                if alvo.get("tipo") != "obra" or alvo.get("id") != oid:
                    continue
                identificador = f"obra:{oid}:{campo}:{indice}"
                eventos.append(_normalizar(identificador, oid, evento.get("tipo"),
                                            evento["alvo"], evento))
        marcos = [item["_id"] for item in self.repositorio.listar_marcos(oid)]
        for evento in self.repositorio.listar_eventos_marcos(marcos):
            eventos.append(_normalizar(str(evento["_id"]), oid, evento.get("tipo"),
                                        evento["alvo"], evento))
        for avanco in self.repositorio.listar_avancos_publicados(marcos):
            try:
                versoes = reconstruir_versoes(avanco)["versoes"]
            except ErroAvanco as erro:
                raise ErroHistorico(str(erro), erro.status, "versoes", codigo=erro.codigo) from None
            for versao in versoes[1:]:
                indice = versao["numero"]
                correcao = versao["correcao"]
                identificador = f"publicacao:{avanco['_id']}:{indice}"
                eventos.append(_normalizar(
                    identificador, oid, "correcao_publicacao",
                    {"tipo": "avanco", "id": avanco["_id"]}, correcao,
                    comparacao=f"/avancos/{avanco['_id']}/versoes",
                ))
        eventos.sort(key=_ordem)
        return eventos

    def consultar(self, mudanca_id):
        partes = mudanca_id.split(":")
        if len(partes) == 4 and partes[0] == "obra":
            obra_id = _id(partes[1], "mudanca_id")
            return self._encontrar(str(obra_id), mudanca_id)
        if len(partes) == 3 and partes[0] == "publicacao":
            avanco_id = _id(partes[1], "mudanca_id")
            avanco = self.repositorio.buscar_avanco(avanco_id)
            marco = self.repositorio.buscar_marco(avanco.get("marco_id")) if avanco else None
            if marco:
                return self._encontrar(str(marco["obra_id"]), mudanca_id)
        if len(partes) == 1:
            evento = self.repositorio.buscar_evento_marco(_id(mudanca_id, "mudanca_id"))
            marco = self.repositorio.buscar_marco(evento["alvo"]["id"]) if evento else None
            if marco:
                return self._encontrar(str(marco["obra_id"]), mudanca_id)
        raise ErroHistorico("Mudança não encontrada", 404, "mudanca_id")

    def _encontrar(self, obra_id, mudanca_id):
        try:
            eventos = self.listar(obra_id)
        except ErroHistorico as erro:
            if erro.status == 404:
                raise ErroHistorico("Mudança não encontrada", 404, "mudanca_id") from None
            raise
        for evento in eventos:
            if evento["id"] == mudanca_id:
                return evento
        raise ErroHistorico("Mudança não encontrada", 404, "mudanca_id")


_servico = ServicoHistorico()
listar_mudancas = _servico.listar
consultar_mudanca = _servico.consultar
