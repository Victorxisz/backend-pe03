"""Estado de edição e publicação de avanços."""

from dataclasses import dataclass

from .comum import ErroDominio

TIPOS_MIDIA = {
    "foto": {"image/jpeg", "image/png"},
    "video": {"video/mp4"},
    "documento": {"application/pdf"},
}


@dataclass(frozen=True)
class Midia:
    tipo: str
    nome: str
    tamanho: int
    mime: str

    def __post_init__(self):
        if (not isinstance(self.tipo, str) or self.tipo not in TIPOS_MIDIA
                or not isinstance(self.mime, str) or self.mime not in TIPOS_MIDIA[self.tipo]
                or not isinstance(self.nome, str) or not self.nome.strip()
                or type(self.tamanho) is not int or self.tamanho <= 0):
            raise ErroDominio("Metadados de mídia inválidos", ["midias"])

    @classmethod
    def de_documento(cls, documento):
        return cls(documento.get("tipo"), documento.get("nome"),
                   documento.get("tamanho"), documento.get("mime"))


@dataclass
class Avanco:
    id: object
    estado: str
    tem_publicacao: bool = False

    @classmethod
    def de_documento(cls, documento):
        return cls(documento.get("_id"), documento.get("estado"), "publicacao" in documento)

    def exigir_rascunho(self):
        if self.estado != "rascunho" or self.tem_publicacao:
            raise ErroDominio("Somente rascunhos sem publicação podem ser editados por este fluxo", ["estado"])

    def validar_midias_finais(self, quantidade):
        self.exigir_rascunho()
        if quantidade < 1:
            raise ErroDominio("O avanço precisa manter pelo menos uma mídia", ["midias_manter"])

    def publicar(self):
        self.exigir_rascunho()
        self.estado, self.tem_publicacao = "publicado", True

