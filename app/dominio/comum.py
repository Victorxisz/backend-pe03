"""Tipos compartilhados pelo domínio."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone


class ErroDominio(ValueError):
    def __init__(self, mensagem, campos=()):
        super().__init__(mensagem)
        self.campos = list(campos)


class Relogio:
    def agora(self):
        instante = datetime.now(timezone.utc)
        # Mesma precisão dos instantes persistidos em BSON.
        return instante.replace(microsecond=instante.microsecond // 1000 * 1000)


def ler_data(valor, campo):
    try:
        if not isinstance(valor, str):
            raise ValueError
        data = date.fromisoformat(valor)
        if data.isoformat() != valor:
            raise ValueError
        return data
    except ValueError:
        raise ErroDominio("Informe uma data válida no formato AAAA-MM-DD", [campo]) from None


def exigir_motivo(motivo):
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErroDominio("Informe o motivo da alteração", ["motivo"])
    return motivo.strip()


@dataclass(frozen=True)
class Mudanca:
    alvo_tipo: str
    alvo_id: object
    campo: str
    anterior: object
    novo: object
    motivo: str
    autor: str
    instante: datetime

    def __post_init__(self):
        object.__setattr__(self, "motivo", exigir_motivo(self.motivo))

    def para_documento(self):
        return deepcopy({
            "tipo": f"{self.campo}_{self.alvo_tipo}",
            "alvo": {"tipo": self.alvo_tipo, "id": self.alvo_id},
            "campo": self.campo,
            "valor_anterior": self.anterior,
            "valor_novo": self.novo,
            "motivo": self.motivo,
            "autor": self.autor,
            "instante": self.instante,
        })

