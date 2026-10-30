"""Transições de marco e grafo de pré-requisitos."""

from dataclasses import dataclass

from .comum import ErroDominio, Mudanca, exigir_motivo

ESTADOS_MARCO = ("a iniciar", "em andamento", "concluído")


class DependenciasPendentes(ErroDominio):
    def __init__(self, dependencias):
        super().__init__("Há dependências pendentes")
        self.dependencias = dependencias


@dataclass
class Marco:
    id: object
    obra_id: object
    estado: str = "a iniciar"

    @classmethod
    def de_documento(cls, documento):
        return cls(documento.get("_id"), documento["obra_id"], documento.get("estado", "a iniciar"))

    def alterar_estado(self, novo_estado, motivo, autor, instante, *, pendentes=(), confirmar=False):
        motivo = exigir_motivo(motivo)
        if novo_estado not in ESTADOS_MARCO:
            raise ErroDominio("Estado do marco inválido", ["estado"])
        if novo_estado == self.estado:
            return None
        if novo_estado == "concluído" and pendentes and not confirmar:
            raise DependenciasPendentes(list(pendentes))
        mudanca = Mudanca("marco", self.id, "estado", self.estado, novo_estado, motivo, autor, instante)
        self.estado = novo_estado
        return mudanca


@dataclass(frozen=True)
class Dependencia:
    marco_id: object
    depende_de_id: object


class GrafoDependencias:
    def __init__(self, vinculos):
        self._grafo = {}
        for vinculo in vinculos:
            self._grafo.setdefault(vinculo["marco_id"], set()).add(vinculo["depende_de_id"])

    def cria_ciclo(self, dependencia):
        pendentes, visitados = [dependencia.depende_de_id], set()
        while pendentes:
            atual = pendentes.pop()
            if atual == dependencia.marco_id:
                return True
            if atual not in visitados:
                visitados.add(atual)
                pendentes.extend(self._grafo.get(atual, ()))
        return False

