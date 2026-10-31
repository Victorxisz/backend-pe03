"""Diário de uploads para operações de negócio com evidências."""

import hashlib
import logging
from datetime import datetime, timezone
from uuid import uuid4

from pymongo.errors import PyMongoError

from app.integracoes.armazenamento import ErroLimpeza
from .midias import ResultadoPersistenciaIndeterminado

logger = logging.getLogger(__name__)


class OperacaoUpload:
    def __init__(self, repositorio, alvo_id, tipo, *, campo_vinculo="avanco_id"):
        self.repositorio = repositorio
        self.alvo_id = alvo_id
        self.tipo = tipo
        self.campo_vinculo = campo_vinculo
        self.id = hashlib.sha256(uuid4().bytes).hexdigest()

    def executar(self, servico, arquivos, salvar):
        criada = False

        def reservar(_validados):
            nonlocal criada
            self.repositorio.criar_operacao({
                "_id": self.id, self.campo_vinculo: self.alvo_id, "tipo": self.tipo,
                "estado": "pendente", "referencias": [],
                "iniciado_em": datetime.now(timezone.utc),
            })
            criada = True

        try:
            return servico.executar_com_midias(
                arquivos, salvar, antes_envio=reservar,
                registrar_referencia=lambda ref: self.repositorio.registrar_referencia(self.id, ref),
            )
        except (ErroLimpeza, ResultadoPersistenciaIndeterminado):
            # Um processo novo poderá recuperar as referências antes dos uploads.
            raise
        except Exception as erro:
            if isinstance(erro, PyMongoError) and erro.has_error_label("UnknownTransactionCommitResult"):
                raise
            if criada:
                try:
                    self.repositorio.remover_operacao_pendente(self.id)
                except PyMongoError:
                    logger.error("Diário de upload mantido para reconciliação: %s", self.id)
            raise
