"""Limpeza de vínculos antigos durante exclusões, sem API ou carga de exemplos.

Mantém compatibilidade com bancos já utilizados: a existência de um vínculo
antigo não pode bloquear a exclusão do alvo nem deixar referências órfãs.
"""

import db

COLECAO = "tbl_feedback_simulado"


def filtro_do_conjunto(*, obra_id=None, marcos=(), avancos=()):
    clausulas = []
    if obra_id is not None:
        clausulas.append({"obra_id": obra_id})
    ids_marcos, ids_avancos = list(marcos), list(avancos)
    if ids_marcos:
        clausulas.append({"marco_id": {"$in": ids_marcos}})
    if ids_avancos:
        clausulas.append({"avanco_id": {"$in": ids_avancos}})
    if not clausulas:
        return None
    return clausulas[0] if len(clausulas) == 1 else {"$or": clausulas}


class RepositorioFeedbackLegado:
    def __init__(self, banco=None):
        self._banco = banco

    @property
    def banco(self):
        return self._banco if self._banco is not None else db.banco_dados

    @property
    def colecao(self):
        return self.banco[COLECAO]

    def listar_do_conjunto(self, filtro, *, session=None):
        if filtro is None:
            return []
        return list(self.colecao.find(filtro, session=session).sort("_id", 1))

    def contar(self, filtro):
        return self.colecao.count_documents(filtro)

    def remover_do_conjunto(self, filtro, *, session=None):
        if filtro is None:
            return 0
        return self.colecao.delete_many(filtro, session=session).deleted_count


def remover_dos_avancos(avancos, *, session=None, banco=None):
    return RepositorioFeedbackLegado(banco).remover_do_conjunto(
        filtro_do_conjunto(avancos=avancos), session=session)
