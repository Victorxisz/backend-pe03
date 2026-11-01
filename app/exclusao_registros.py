"""UC-18: conjuntos individuais, contexto real e retomada autenticada."""

from bson import ObjectId
from bson.errors import InvalidId

import db
from app import exclusoes
from app.avancos import repository as avancos
from app.ocorrencias.repository import RepositorioOcorrencias
from app.historico.repository import RepositorioHistorico


def ler_contexto():
    """Aceita contexto no JSON ou query string, recusando ambiguidades."""
    from flask import request
    dados = request.get_json(silent=True)
    if request.data and (not request.is_json or not isinstance(dados, dict)):
        raise exclusoes.ErroExclusao("Envie um objeto JSON", 422, ["corpo"])
    if set(request.args) - {"obra_id", "marco_id"}:
        raise exclusoes.ErroExclusao("Parâmetros desconhecidos", 422, ["contexto"])
    for campo in request.args:
        if len(request.args.getlist(campo)) != 1 or isinstance(dados, dict) and campo in dados:
            raise exclusoes.ErroExclusao("Não repita o contexto", 422, [campo])
    return {**(dados or {}), **request.args.to_dict()} if dados is not None or request.args else None


def identificar(valor, campo):
    try:
        if not isinstance(valor, (str, ObjectId)):
            raise TypeError
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise exclusoes.ErroExclusao("ID inválido", 400, [campo], codigo="ID_INVALIDO") from None


def validar_contexto(alvo, dados, autor, sessao=None):
    """O contexto enviado só restringe o alvo; nunca escolhe seus dependentes."""
    obra = db.banco_dados["tbl_obras"].find_one({"_id": alvo.get("obra_id")}, session=sessao)
    if obra is None or (obra.get("autor") and str(obra["autor"]) != str(autor)):
        raise exclusoes.ErroExclusao("Obra não encontrada", 404, ["obra_id"])
    if alvo.get("marco_id") is not None:
        marco = db.banco_dados["tbl_marcos"].find_one({"_id": alvo["marco_id"]}, session=sessao)
        if marco is None or marco.get("obra_id") != obra["_id"]:
            raise exclusoes.ErroExclusao("Marco não encontrado nesta obra", 404, ["marco_id"])
    for campo in ("obra_id", "marco_id"):
        if isinstance(dados, dict) and campo in dados:
            if identificar(dados[campo], campo) != alvo.get(campo):
                raise exclusoes.ErroExclusao("Contexto não corresponde ao registro", 409, [campo],
                                            codigo="CONTEXTO_INCOMPATIVEL")


def confirmar(dados, alvo, perda):
    campos = {"obra_id", "marco_id"}
    corpo = ({k: v for k, v in dados.items() if k not in campos}
             if isinstance(dados, dict) else dados)
    exclusoes.exigir_confirmacao(corpo, alvo, perda)


def excluir_registro(tipo, valor, dados, autor, *, previa=False):
    identificador = identificar(valor, tipo + "_id")
    colecao = db.banco_dados["tbl_avancos" if tipo == "avanco" else "tbl_ocorrencias"]
    documento = colecao.find_one({"_id": identificador})
    if documento is None:
        pendencia = exclusoes._servico.pendencia_do_alvo(tipo, identificador)
        if pendencia is None:
            raise exclusoes.ErroExclusao("Registro não encontrado", 404, [tipo + "_id"],
                                        codigo="REGISTRO_NAO_ENCONTRADO")
        alvo = pendencia["alvo"]
        validar_contexto(alvo, dados, autor)
        if previa:
            return {"alvo": alvo, "perda": pendencia["perda"]}
        confirmar(dados, alvo, pendencia["perda"])
        exclusoes.retomar_pendencia(tipo, identificador)
        return

    if tipo == "avanco":
        estado = documento.get("estado")
        if (estado not in {"rascunho", "publicado", avancos.ESTADO_EXCLUSAO}
                or estado == "publicado" and not documento.get("publicacao")
                or estado != "publicado" and "publicacao" in documento):
            raise exclusoes.ErroExclusao("Estado do avanço incompatível", 409, ["estado"])
        marco = db.banco_dados["tbl_marcos"].find_one({"_id": documento.get("marco_id")})
        if marco is None:
            raise exclusoes.ErroExclusao("Marco não encontrado", 404, ["marco_id"])
        obra_id = marco.get("obra_id")
    else:
        obra_id = documento.get("obra_id")

    alvo = {"tipo": tipo, "id": identificador, "obra_id": obra_id,
            "marco_id": documento.get("marco_id"),
            "nome": documento.get("titulo", documento.get("descricao", "Registro"))}
    validar_contexto(alvo, dados, autor)
    # Mantém o contrato sem corpo e o diário de rascunho do UC-09.
    if tipo == "avanco" and documento["estado"] != "publicado":
        if previa:
            return {"alvo": alvo, "perda": {"avancos": 1, "midias": len(avancos.consultar_midias(identificador))}}
        if dados is not None:
            confirmar(dados, alvo, {"avancos": 1, "midias": len(avancos.consultar_midias(identificador))})
        from app.avancos.service import excluir_rascunho
        excluir_rascunho(valor)
        return

    ocorrencias = RepositorioOcorrencias()
    historico = RepositorioHistorico()

    def listar_midias(sessao=None):
        if tipo == "avanco":
            return avancos.consultar_midias_de_avancos([identificador], session=sessao)
        atual = colecao.find_one({"_id": identificador}, session=sessao)
        return atual.get("midias", []) if atual else []

    midias = listar_midias()
    eventos = historico.listar_eventos_dos_alvos([identificador])
    perda = (exclusoes.resumo_dos_avancos([documento]) if tipo == "avanco"
             else exclusoes.resumo_das_ocorrencias([documento]))
    if tipo == "avanco":
        from app.simulados.repository import RepositorioSimulados
        perda["exemplos_simulados"] += RepositorioSimulados().contar({"atualizacao_id": identificador})
    perda.update(midias=len(midias), historico=len(eventos) + len(documento.get("historico_estados", [])))
    if previa:
        return {"alvo": alvo, "perda": perda}
    confirmar(dados, alvo, perda)

    def remover(sessao):
        # A releitura completa também detecta correção, aceitação ou troca de
        # vínculo entre o aviso e a transação, sem apagar conteúdo novo em silêncio.
        atual = colecao.find_one({"_id": identificador}, session=sessao)
        if atual != documento or listar_midias(sessao) != midias:
            raise exclusoes.ConflitoExclusao("Registro alterado; consulte novamente")
        repositorio = avancos if tipo == "avanco" else ocorrencias
        if repositorio.upload_em_andamento(identificador, session=sessao):
            raise exclusoes.ConflitoExclusao("Há um envio de mídia pendente; reconcilie antes de excluir")
        validar_contexto(alvo, dados, autor, sessao)
        if tipo == "avanco":
            avancos.remover_avancos([identificador], session=sessao)
        else:
            ocorrencias.remover([identificador], session=sessao)
        historico.remover_eventos_dos_alvos([identificador], session=sessao)

    exclusoes.aplicar(exclusoes.Conjunto(
        alvo=alvo, perda=perda,
        ids=(identificador, *(m["_id"] for m in midias)), midias=tuple(midias),
        remover=remover, relistar=listar_midias,
    ))
