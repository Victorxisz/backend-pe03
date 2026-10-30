"""Exclusão retomável de rascunhos, sem excluir avanços publicados."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
"""Regras de negócio da edição de avanços em rascunho."""

from bson import ObjectId
from bson.errors import InvalidId

from app.integracoes.armazenamento import ErroArmazenamento
from . import midias, repository
from .revisoes import ConflitoRascunho

TEMPO_BLOQUEIO = timedelta(minutes=5)


class ErroExclusao(Exception):
    def __init__(self, mensagem, status, codigo, campos=(), pendentes=None):
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo
        self.campos, self.pendentes = list(campos), pendentes


def _conflito():
    return ErroExclusao("O avanço foi alterado ou há uma exclusão em andamento. Tente novamente",
                      409, "CONFLITO_EXCLUSAO", ["avanco_id"])


def excluir_rascunho(avanco_id):
    try:
        if not isinstance(avanco_id, (str, ObjectId)):
            raise TypeError
        identificador = ObjectId(avanco_id)
    except (InvalidId, TypeError):
        raise ErroExclusao("ID do avanço inválido", 400, "ID_INVALIDO", ["avanco_id"]) from None
    documento = repository.buscar_avanco(identificador)
    if documento is None:
        raise ErroExclusao("Avanço não encontrado", 404, "AVANCO_NAO_ENCONTRADO", ["avanco_id"])
    if "publicacao" in documento or documento.get("estado") not in {"rascunho", repository.ESTADO_EXCLUSAO}:
        raise ErroExclusao("Somente rascunhos podem ser excluídos por esta rota", 409,
                         "AVANCO_NAO_E_RASCUNHO", ["estado"])
    token, agora = uuid4().hex, datetime.now(timezone.utc)
    if documento["estado"] == "rascunho":
        arquivos = midias.preparar_limpeza(repository.consultar_midias(identificador))
        try:
            operacao = repository.iniciar_exclusao(documento, arquivos, token, agora, agora + TEMPO_BLOQUEIO)
        except ConflitoRascunho:
            raise _conflito() from None
    else:
        operacao = repository.retomar_exclusao(identificador, token, agora, agora + TEMPO_BLOQUEIO)
    if operacao is None:
        raise _conflito()

    concluido = False
    try:
        for arquivo in operacao["exclusao"]["pendentes"]:
            if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
                raise _conflito()
            if not repository.arquivo_tem_outras_referencias(identificador, arquivo):
                if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
                    raise _conflito()
                try:
                    midias.remover_arquivo(arquivo["referencia"])
                except (ErroArmazenamento, ValueError):
                    repository.registrar_falha_limpeza(identificador, token, datetime.now(timezone.utc))
                    continue
            if not repository.concluir_arquivo(identificador, token, arquivo["chave"]):
                raise _conflito()

        atual = repository.buscar_avanco(identificador)
        if atual is None or atual.get("exclusao", {}).get("token") != token:
            raise _conflito()
        # Escritores de rascunho devem usar revisoes.registrar_alteracao. Além
        # disso, não descartamos mídias novas que apareceram durante a limpeza.
        conhecidas = {item["chave"] for item in atual["exclusao"]["arquivos"]}
        novas = [item for item in midias.preparar_limpeza(repository.consultar_midias(identificador))
                 if item["chave"] not in conhecidas]
        if novas:
            repository.acrescentar_pendencias(identificador, token, novas)
        quantidade = len(atual["exclusao"]["pendentes"]) + len(novas)
        if quantidade:
            raise ErroExclusao("Exclusão ainda não concluída. Repita a requisição para retomar a limpeza",
                             503, "LIMPEZA_PENDENTE", ["midias"], quantidade)
        if not repository.renovar_exclusao(identificador, token, datetime.now(timezone.utc) + TEMPO_BLOQUEIO):
            raise _conflito()
        if not repository.finalizar_exclusao(identificador, token):
            raise _conflito()
        concluido = True
    finally:
        if not concluido:
            repository.liberar_exclusao(identificador, token)
