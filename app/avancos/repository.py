"""Persistência de avanços, revisões e limpeza de mídias."""

from bson import ObjectId
from pymongo import ReturnDocument

import db
import logging

logger = logging.getLogger(__name__)

from .revisoes import ConflitoRascunho, filtro_revisao, registrar_alteracao
from .rascunhos_repository import RepositorioRascunhos, diarios_de_limpeza

ESTADO_EXCLUSAO = "exclusao_pendente"


def avanco_existe(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one(
        {"_id": avanco_id, "estado": {"$ne": ESTADO_EXCLUSAO}},
        {"_id": 1},
    ) is not None


def marco_existe(marco_id):
    return db.colecao_marcos.find_one({"_id": marco_id}, {"_id": 1}) is not None


def inserir_avanco(documento):
    return db.banco_dados["tbl_avancos"].insert_one(documento).inserted_id


def inserir_avanco_com_midias(documento, midias):
    return RepositorioRascunhos().inserir_com_midias(documento, midias)


def buscar_avanco(avanco_id):
    return db.banco_dados["tbl_avancos"].find_one({"_id": avanco_id})


def salvar_correcao_publicada(documento, correcao, conteudo, novas_midias=(), operacao_id=None, midias_validadas=()):
    """Aplica conteúdo e snapshot juntos; revisão impede duas correções concorrentes."""
    revisao = filtro_revisao(documento)

    def gravar(sessao):
        # A leitura e a validação do provedor ocorrem antes da transação. Esta
        # escrita detecta remoções/alterações dos metadados nesse intervalo.
        for midia in midias_validadas:
            resultado = db.banco_dados["tbl_midias"].update_one(
                midia, {"$inc": {"_versao_correcao": 1}}, session=sessao,
            )
            if resultado.matched_count != 1:
                raise ConflitoRascunho("Uma mídia foi alterada durante a correção")
        if novas_midias:
            db.banco_dados["tbl_midias"].insert_many(list(novas_midias), session=sessao)
        resultado = db.banco_dados["tbl_avancos"].update_one(
            {"_id": documento["_id"], "estado": "publicado", **revisao,
             **{campo: documento[campo] if campo in documento else {"$exists": False}
                for campo in ("publicacao", "correcoes", "data", "descricao", "midias",
                              "autor", "origem_simulada")}},
            {"$set": {"data": conteudo["data"], "descricao": conteudo["descricao"],
                      "midias": conteudo["midias"], "editado": True},
             "$push": {"correcoes": correcao}, "$inc": {"revisao": 1}},
            session=sessao,
        )
        if resultado.matched_count != 1:
            raise ConflitoRascunho("A publicação foi alterada durante a correção")
        if operacao_id is not None:
            confirmado = db.banco_dados["tbl_uploads_pendentes"].update_one(
                {"_id": operacao_id, "estado": "pendente"},
                {"$set": {"estado": "concluida"}}, session=sessao,
            )
            if confirmado.matched_count != 1:
                raise ConflitoRascunho("Operação de upload indisponível")

    confirmado = False
    try:
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(gravar)
            confirmado = True
    except Exception:
        if not confirmado:
            raise
        logger.warning("Correção confirmada; falha ao encerrar sessão do MongoDB")


def consultar_midias(avanco_id):
    return list(db.banco_dados["tbl_midias"].find({"avanco_id": avanco_id}).sort("_id", 1))


def consultar_midias_retidas(avanco_id, identificadores):
    """Identifica referências ainda no acervo sem carregar dados do provedor."""
    return {str(item["_id"]) for item in db.banco_dados["tbl_midias"].find(
        {"avanco_id": avanco_id, "_id": {"$in": list(identificadores)}}, {"_id": 1}
    )}


def buscar_midia_por_id(midia_id):
    return db.banco_dados["tbl_midias"].find_one({"_id": midia_id})





def midia_tem_publicacao(midia_id, *, sessao=None):
    documento = db.banco_dados["tbl_avancos"].find_one(
        {
            "publicacao.midias.id": {
                "$in": [
                    str(midia_id),
                    midia_id,
                ]
            }
        },
        {"_id": 1},
        session=sessao,
    )

    return documento is not None



def iniciar_exclusao(documento, arquivos, token, agora, ate):
    validar_referencias_das_midias(
        documento["_id"], consultar_midias(documento["_id"])
    )
    # O mesmo CAS usado pela publicação impede a disputa publicar/excluir.
    return db.banco_dados["tbl_avancos"].find_one_and_update(
        {"_id": documento["_id"], "estado": "rascunho", "publicacao": {"$exists": False},
         **filtro_revisao(documento)},
        {"$set": {"estado": ESTADO_EXCLUSAO, "exclusao": {
            "arquivos": arquivos, "pendentes": arquivos, "token": token,
            "iniciada_em": agora, "ate": ate, "tentativas": 1,
        }}, "$inc": {"revisao": 1}},
        return_document=ReturnDocument.AFTER,
    )


def retomar_exclusao(avanco_id, token, agora, ate):
    return db.banco_dados["tbl_avancos"].find_one_and_update(
        {"_id": avanco_id, "estado": ESTADO_EXCLUSAO, "publicacao": {"$exists": False},
         "$or": [{"exclusao.token": None}, {"exclusao.ate": {"$lte": agora}}]},
        {"$set": {"exclusao.token": token, "exclusao.ate": ate},
         "$inc": {"exclusao.tentativas": 1}}, return_document=ReturnDocument.AFTER,
    )


def _operacao(avanco_id, token):
    return {"_id": avanco_id, "estado": ESTADO_EXCLUSAO, "exclusao.token": token}


def renovar_exclusao(avanco_id, token, ate):
    return db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$set": {"exclusao.ate": ate}}).matched_count == 1


def concluir_arquivo(avanco_id, token, chave):
    return db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$pull": {"exclusao.pendentes": {"chave": chave}}}).matched_count == 1


def liberar_exclusao(avanco_id, token):
    db.banco_dados["tbl_avancos"].update_one(_operacao(avanco_id, token), {"$set": {"exclusao.token": None, "exclusao.ate": None}})


def registrar_falha_limpeza(avanco_id, token, agora):
    db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$set": {"exclusao.ultima_falha_em": agora, "exclusao.ultimo_erro": "Não foi possível remover um arquivo no provedor"}},
    )



def consultar_midias_para_limpeza(avanco_id):
    """Inclui arquivos removidos por edições cuja limpeza ainda não terminou."""
    atuais = consultar_midias(avanco_id)
    anteriores = [
        tarefa["midia"]
        for tarefa in db.banco_dados["tbl_limpezas_midias"].find(
            {"avanco_id": avanco_id}
        )
    ]
    return atuais + anteriores


def acrescentar_pendencias(avanco_id, token, arquivos):
    return db.banco_dados["tbl_avancos"].update_one(
        _operacao(avanco_id, token),
        {"$push": {"exclusao.arquivos": {"$each": arquivos},
                   "exclusao.pendentes": {"$each": arquivos}}},
    ).matched_count == 1


def finalizar_exclusao(avanco_id, token):
    filtro = {**_operacao(avanco_id, token), "exclusao.pendentes": {"$size": 0}}
    if db.banco_dados["tbl_avancos"].find_one(filtro, {"_id": 1}) is None:
        return False
    validar_referencias_das_midias(avanco_id, consultar_midias(avanco_id))
    # O diário permanece até concluir todas as etapas e permite retentativa
    # se alguma escrita falhar, inclusive depois de remover os metadados.
    db.banco_dados["tbl_midias"].delete_many({"avanco_id": avanco_id})
    db.banco_dados["tbl_limpezas_midias"].delete_many({"avanco_id": avanco_id})
    return db.banco_dados["tbl_avancos"].delete_one(filtro).deleted_count == 1


def _outros_documentos(avanco_id):
    """Tarefas de limpeza e diários de exclusão não consomem os arquivos."""
    banco = db.banco_dados
    diarios = diarios_de_limpeza()
    for nome in banco.list_collection_names():
        if nome in diarios:
            continue
        for documento in banco[nome].find():
            if nome == "tbl_uploads_pendentes" and documento.get("estado") in {"concluida", "limpa"}:
                continue
            if nome == "tbl_avancos":
                if documento["_id"] == avanco_id or documento.get("estado") == ESTADO_EXCLUSAO:
                    continue
            if nome == "tbl_midias":
                dono = documento.get("avanco_id")
                if dono == avanco_id:
                    continue
                pai = buscar_avanco(dono) if dono is not None else None
                if pai is not None and pai.get("estado") == ESTADO_EXCLUSAO:
                    continue
            yield documento


def _contem_id(valor, ids, textos):
    if isinstance(valor, dict):
        return any(_contem_id(item, ids, textos) for item in valor.values())
    if isinstance(valor, list):
        return any(_contem_id(item, ids, textos) for item in valor)
    if isinstance(valor, str):
        return valor in textos
    return isinstance(valor, ObjectId) and valor in ids


def validar_referencias_das_midias(avanco_id, midias):
    """Não remove metadados cujo ID ainda é usado fora do rascunho."""
    ids = {midia["_id"] for midia in midias}
    if not ids:
        return
    textos = {str(valor) for valor in ids}
    if any(_contem_id(doc, ids, textos) for doc in _outros_documentos(avanco_id)):
        raise ConflitoRascunho(
            "Uma mídia está referenciada por outro registro"
        )


def arquivo_tem_outras_referencias(avanco_id, arquivo):
    """Preserva arquivos usados por outras mídias ou snapshots históricos."""
    from .midias import chave_arquivo, ErroMidia
    identidade = chave_arquivo(arquivo["referencia"])
    ids = set(arquivo["midia_ids"])
    textos = {str(valor) for valor in ids}

    def contem(valor):
        if isinstance(valor, dict):
            try:
                if chave_arquivo(valor) == identidade:
                    return True
            except ErroMidia:
                pass
            return any(contem(item) for item in valor.values())
        if isinstance(valor, list):
            return any(contem(item) for item in valor)
        return _contem_id(valor, ids, textos)

    return any(contem(doc) for doc in _outros_documentos(avanco_id))


# Fachada da persistência orientada a objetos, preservada após integrar a main.


def salvar_edicao(documento, alteracoes, midias_anteriores, ids_manter, novas_midias, operacao_id=None):
    return RepositorioRascunhos().salvar_edicao(documento, alteracoes, midias_anteriores, ids_manter, novas_midias, operacao_id)


def referencia_em_uso(referencia, *, ids_midias=(), operacao_ignorada=None):
    return RepositorioRascunhos().referencia_em_uso(referencia, ids_midias, operacao_ignorada)


def concluir_limpeza(midia_id):
    return RepositorioRascunhos().concluir_limpeza(midia_id)


def listar_avancos(marco_id):
    return list(db.banco_dados["tbl_avancos"].find(
        {"marco_id": marco_id, "estado": {"$ne": ESTADO_EXCLUSAO}}
    ).sort([("data", 1), ("_id", 1)]))

def listar_avancos_de_marcos(marcos, *, session=None):
    """Inclui rascunhos e avanços reservados para exclusão individual."""
    return list(db.banco_dados["tbl_avancos"].find(
        {"marco_id": {"$in": list(marcos)}}, session=session
    ).sort("_id", 1))


def consultar_midias_de_avancos(avancos, *, session=None):
    """Mídias atuais e as retiradas por edição cuja limpeza não terminou."""
    ids = list(avancos)
    atuais = list(db.banco_dados["tbl_midias"].find(
        {"avanco_id": {"$in": ids}}, session=session
    ).sort("_id", 1))
    anteriores = [
        tarefa["midia"]
        for tarefa in db.banco_dados["tbl_limpezas_midias"].find(
            {"avanco_id": {"$in": ids}}, session=session
        ).sort("_id", 1)
    ]
    return atuais + anteriores


def remover_avancos(avancos, *, session=None):
    """Remove avanços com mídias, tarefas de limpeza e diários de upload."""
    ids = list(avancos)
    if not ids:
        return
    for colecao, filtro in (
        ("tbl_midias", {"avanco_id": {"$in": ids}}),
        ("tbl_limpezas_midias", {"avanco_id": {"$in": ids}}),
        ("tbl_uploads_pendentes", {"avanco_id": {"$in": ids}}),
        ("tbl_avancos", {"_id": {"$in": ids}}),
    ):
        db.banco_dados[colecao].delete_many(filtro, session=session)


def buscar_obra(obra_id):
    return db.colecao_obras.find_one({"_id": obra_id}, {"_id": 1})


def consultar_publicados(obra_id):
    marcos = [item["_id"] for item in db.colecao_marcos.find({"obra_id": obra_id}, {"_id": 1})]
    return list(db.banco_dados["tbl_avancos"].find(
        {"marco_id": {"$in": marcos}, "estado": "publicado", "publicacao": {"$type": "object"}}
    ).sort([("publicacao.instante", -1), ("_id", 1)]))


class MarcoRemovido(Exception):
    pass


def salvar_com_midias(documento, midias, operacao_id):
    """Salva documentos e verifica vínculo em transação MongoDB."""

    def gravar(sessao):
        # A escrita no marco detecta exclusão concorrente antes do commit.
        atualizado = db.colecao_marcos.update_one(
            {"_id": documento["marco_id"]},
            {"$inc": {"_versao_avancos": 1}},
            session=sessao,
        )
        if atualizado.matched_count != 1:
            raise MarcoRemovido()
        db.banco_dados["tbl_avancos"].insert_one(documento, session=sessao)
        db.banco_dados["tbl_midias"].insert_many(midias, session=sessao)
        operacao = db.banco_dados["tbl_uploads_pendentes"].update_one(
            {"_id": operacao_id, "estado": "pendente"},
            {"$set": {"estado": "concluida"}},
            session=sessao,
        )
        if operacao.matched_count != 1:
            raise RuntimeError("Operação de upload indisponível")

    confirmado = False
    try:
        with db.cliente_mongo.start_session() as sessao:
            sessao.with_transaction(gravar)
            confirmado = True
    except Exception:
        if not confirmado:
            raise
        # A transação já confirmou: um erro no encerramento da sessão não deve
        # acionar a compensação e apagar mídias efetivamente referenciadas.
        logger.warning("Transação confirmada; falha ao encerrar sessão do MongoDB")


def criar_operacao(documento):
    db.banco_dados["tbl_uploads_pendentes"].insert_one(documento)


def buscar_operacao(operacao_id):
    return db.banco_dados["tbl_uploads_pendentes"].find_one({"_id": operacao_id})


def registrar_referencia(operacao_id, referencia):
    resultado = db.banco_dados["tbl_uploads_pendentes"].update_one(
        {"_id": operacao_id, "estado": "pendente"},
        {"$push": {"referencias": referencia}},
    )
    if resultado.matched_count != 1:
        raise RuntimeError("Operação de upload indisponível")


def remover_operacao_pendente(operacao_id):
    db.banco_dados["tbl_uploads_pendentes"].delete_one(
        {"_id": operacao_id, "estado": "pendente"}
    )
