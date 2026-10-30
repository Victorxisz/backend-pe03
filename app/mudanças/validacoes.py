"""Contrato UC-12; valores de prazo e estado usam as regras dos seus módulos."""

from app.dominio.comum import ErroDominio, exigir_motivo


def validar_mudanca(dados):
    obrigatorios = {"alvo", "campo", "novo_valor", "motivo", "versao"}
    if not isinstance(dados, dict):
        raise ErroDominio("Envie um objeto JSON", ["corpo"])
    invalidos = (obrigatorios - set(dados)) | (set(dados) - obrigatorios - {"confirmar_dependencias"})
    if invalidos:
        raise ErroDominio("Envie os campos previstos para a mudança", sorted(invalidos))
    alvo = dados["alvo"]
    if (not isinstance(alvo, dict) or set(alvo) != {"tipo", "id"}
            or alvo["tipo"] not in ("obra", "marco")):
        raise ErroDominio("Informe alvo com tipo obra/marco e id", ["alvo"])
    campos = ("entrega", "estado") if alvo["tipo"] == "obra" else ("periodo_previsto", "estado")
    if dados["campo"] not in campos:
        raise ErroDominio("Campo não editável para este alvo", ["campo"])
    if type(dados["versao"]) is not int or dados["versao"] < 0:
        raise ErroDominio("Informe uma versão inteira não negativa", ["versao"])
    if "confirmar_dependencias" in dados:
        if alvo["tipo"] != "marco" or dados["campo"] != "estado":
            raise ErroDominio("Confirmação se aplica somente ao estado do marco", ["confirmar_dependencias"])
        if type(dados["confirmar_dependencias"]) is not bool:
            raise ErroDominio("A confirmação deve ser booleana", ["confirmar_dependencias"])
    exigir_motivo(dados["motivo"])
