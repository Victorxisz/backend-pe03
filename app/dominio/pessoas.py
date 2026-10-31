"""Pessoas cadastradas e a conta da construtora."""

from dataclasses import dataclass, field
from datetime import datetime

from .comum import ErroDominio


@dataclass
class Construtora:
    id: object
    nome: str
    email: str
    ativo: bool
    telefone: str | None = None

    @classmethod
    def de_documento(cls, documento):
        return cls(documento["_id"], documento.get("nome", ""), documento.get("email", ""),
                   documento.get("ativo") is True, documento.get("telefone"))

    def para_dict(self):
        return {"id": str(self.id), "nome": self.nome, "email": self.email, "telefone": self.telefone}


@dataclass
class Trabalhador:
    nome: str
    email: str
    telefone: str
    cargo: str
    construtora_id: str
    data_cadastro: datetime
    obras: list[str] = field(default_factory=list)
    ativo: bool = True

    def __post_init__(self):
        if not self.construtora_id:
            raise ErroDominio("O trabalhador deve pertencer a uma construtora", ["construtora_id"])

    def vincular_obra(self, obra_id):
        identificador = str(obra_id)
        if identificador not in self.obras:
            self.obras.append(identificador)

    def para_documento(self):
        return {"nome": self.nome, "email": self.email, "telefone": self.telefone,
                "cargo": self.cargo, "construtora_id": self.construtora_id,
                "data_cadastro": self.data_cadastro, "obras": list(self.obras), "ativo": self.ativo}
