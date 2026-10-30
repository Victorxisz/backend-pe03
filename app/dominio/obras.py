"""Prazo e ciclo de vida de uma obra residencial."""

from dataclasses import dataclass
from datetime import date

from .comum import ErroDominio, Mudanca, exigir_motivo, ler_data

ESTADOS_OBRA = ("planejada", "em andamento", "concluída", "suspensa")


@dataclass(frozen=True)
class PrazoEntrega:
    modalidade: str
    data: date | None = None
    inicio: date | None = None
    fim: date | None = None

    def __post_init__(self):
        if self.modalidade == "data_exata":
            if type(self.data) is not date or self.inicio is not None or self.fim is not None:
                raise ErroDominio("Informe somente a data exata de entrega", ["entrega"])
        elif self.modalidade == "intervalo_estimado":
            if self.data is not None or type(self.inicio) is not date or type(self.fim) is not date:
                raise ErroDominio("Informe início e fim do intervalo de entrega", ["entrega"])
            if self.fim < self.inicio:
                raise ErroDominio("O fim do intervalo não pode ser anterior ao início", ["entrega.fim"])
        else:
            raise ErroDominio("Informe 'data_exata' ou 'intervalo_estimado'", ["entrega.modalidade"])

    @classmethod
    def de_dados(cls, dados):
        if not isinstance(dados, dict):
            raise ErroDominio("Informe os dados de entrega como um objeto JSON", ["entrega"])
        modalidade = dados.get("modalidade")
        if modalidade == "data_exata":
            if set(dados) - {"modalidade", "data"}:
                raise ErroDominio("Informe somente os campos da modalidade escolhida", ["entrega"])
            return cls(modalidade, data=ler_data(dados.get("data"), "entrega.data"))
        if modalidade == "intervalo_estimado":
            if set(dados) - {"modalidade", "inicio", "fim"}:
                raise ErroDominio("Informe somente os campos da modalidade escolhida", ["entrega"])
            return cls(modalidade, inicio=ler_data(dados.get("inicio"), "entrega.inicio"),
                       fim=ler_data(dados.get("fim"), "entrega.fim"))
        raise ErroDominio("Informe 'data_exata' ou 'intervalo_estimado'", ["entrega.modalidade"])

    @property
    def limite(self):
        return self.data if self.modalidade == "data_exata" else self.fim

    def vencido_em(self, referencia):
        return referencia > self.limite

    def para_dict(self):
        if self.modalidade == "data_exata":
            return {"modalidade": self.modalidade, "data": self.data.isoformat()}
        return {"modalidade": self.modalidade, "inicio": self.inicio.isoformat(), "fim": self.fim.isoformat()}


@dataclass
class Obra:
    id: object
    entrega: PrazoEntrega
    estado: str = "planejada"
    data_conclusao: date | None = None

    def __post_init__(self):
        if self.estado not in ESTADOS_OBRA:
            raise ErroDominio("Estado da obra inválido", ["estado"])

    @classmethod
    def de_documento(cls, documento):
        conclusao = documento.get("data_conclusao")
        return cls(documento.get("_id"), PrazoEntrega.de_dados(documento.get("entrega")),
                   documento.get("estado", "planejada"),
                   ler_data(conclusao, "data_conclusao") if conclusao else None)

    def alertas(self, hoje):
        referencia = self.data_conclusao if self.estado == "concluída" else hoje
        # Registros antigos sem conclusão não recebem uma data inventada na leitura.
        return ["atrasada"] if referencia and self.entrega.vencido_em(referencia) else []

    def alterar_estado(self, novo_estado, motivo, autor, instante):
        motivo = exigir_motivo(motivo)
        if novo_estado not in ESTADOS_OBRA:
            raise ErroDominio("Estado da obra inválido", ["estado"])
        if novo_estado == self.estado:
            return None
        anterior = {"estado": self.estado, "data_conclusao": self._conclusao_textual()}
        self.estado = novo_estado
        self.data_conclusao = instante.date() if novo_estado == "concluída" else None
        return Mudanca("obra", self.id, "estado", anterior,
                       {"estado": self.estado, "data_conclusao": self._conclusao_textual()},
                       motivo, autor, instante)

    def _conclusao_textual(self):
        return self.data_conclusao.isoformat() if self.data_conclusao else None

