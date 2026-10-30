"""Validação dos campos de um avanço em rascunho."""

from datetime import date


class ErroAvanco(Exception):
    def __init__(self, mensagem, status=422, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


def validar_campos(formulario, arquivos):
    if not isinstance(formulario, dict):
        raise ErroAvanco("Envie multipart/form-data", 422, ["corpo"])
    desconhecidos = sorted(set(formulario) - {"data", "descricao"})
    if desconhecidos:
        raise ErroAvanco("Campos não permitidos", 422, desconhecidos)
    data = formulario.get("data")
    try:
        if not isinstance(data, str) or date.fromisoformat(data).isoformat() != data:
            raise ValueError
    except ValueError:
        raise ErroAvanco(
            "Informe uma data válida no formato AAAA-MM-DD", 422, ["data"]
        ) from None
    descricao = formulario.get("descricao")
    if not isinstance(descricao, str) or not descricao.strip():
        raise ErroAvanco("Informe a descrição do avanço", 422, ["descricao"])
    if not arquivos:
        raise ErroAvanco("Envie ao menos uma mídia", 422, ["midias"])
    return {"data": data, "descricao": descricao.strip()}
