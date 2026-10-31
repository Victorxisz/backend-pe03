"""Unifica decisões e correções já persistidas, sem produzir novos eventos."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.serializacao import serializar
from .repository import RepositorioHistorico


class ErroHistorico(Exception):
    def __init__(self, mensagem, status, campo):
        super().__init__(mensagem)
        self.status = status
        self.campos = [campo]


def _id(valor, campo):
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroHistorico("Identificador inválido", 400, campo) from None


def _instante(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor).isoformat()
    return valor


def _campos(evento):
    if "campo" in evento:
        return [evento["campo"]]
    if "estado_anterior" in evento:
        return ["estado"]
    return [campo for campo in ("data", "descricao", "midias")
            if evento["antes"].get(campo) != evento["depois"].get(campo)]


def _normalizar(identificador, obra_id, tipo, alvo, evento, *, comparacao=None):
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
            for indice, evento in enumerate(obra.get(campo, [])):
                alvo = evento.get("alvo", {})
                if alvo.get("tipo") != "obra" or alvo.get("id") != oid:
                    continue
                identificador = f"obra:{oid}:{campo}:{indice}"
                eventos.append(_normalizar(identificador, oid, evento["tipo"],
                                            evento["alvo"], evento))
        marcos = [item["_id"] for item in self.repositorio.listar_marcos(oid)]
        for evento in self.repositorio.listar_eventos_marcos(marcos):
            eventos.append(_normalizar(str(evento["_id"]), oid, evento["tipo"],
                                        evento["alvo"], evento))
        for avanco in self.repositorio.listar_avancos_publicados(marcos):
            for indice, correcao in enumerate(avanco.get("correcoes", []), 2):
                identificador = f"publicacao:{avanco['_id']}:{indice}"
                eventos.append(_normalizar(
                    identificador, oid, "correcao_publicacao",
                    {"tipo": "avanco", "id": avanco["_id"]}, correcao,
                    comparacao=f"/avancos/{avanco['_id']}/versoes",
                ))
        eventos.sort(key=lambda item: (item["instante"], item["id"]))
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
        except ErroHistorico:
            raise ErroHistorico("Mudança não encontrada", 404, "mudanca_id") from None
        for evento in eventos:
            if evento["id"] == mudanca_id:
                return evento
        raise ErroHistorico("Mudança não encontrada", 404, "mudanca_id")


_servico = ServicoHistorico()
listar_mudancas = _servico.listar
consultar_mudanca = _servico.consultar
