"""Persistência dos exemplos simulados: leitura do painel e remoção em cascata.

Este módulo depende apenas de :mod:`db`. A carga de demonstração e as cascatas
de UC-17/UC-18 o importam sem criar ciclo com :mod:`app.avancos`.
"""

import db

COLECAO = "tbl_feedback_simulado"

# Tipos aceitos no acervo. `atualizacao` é o avanço publicado de um marco.
TIPOS = ("avaliacao", "compreensao", "duvida")
ALVOS = ("obra", "marco", "atualizacao")


def filtro_do_conjunto(*, obra_id=None, marcos=(), avancos=()):
    """Monta o filtro dos exemplos que dependem do que está sendo excluído.

    O vínculo é procurado nos três campos desnormalizados: um exemplo ligado a
    marco ou atualização também guarda a obra, mas a busca não depende disso.
    """
    clausulas = []
    if obra_id is not None:
        clausulas.append({"obra_id": obra_id})
    ids_marcos = list(marcos)
    if ids_marcos:
        clausulas.append({"marco_id": {"$in": ids_marcos}})
    ids_avancos = list(avancos)
    if ids_avancos:
        clausulas.append({"avanco_id": {"$in": ids_avancos}})
    if not clausulas:
        # Sem alvo não há conjunto: devolver ``None`` impede que uma chamada
        # sem vínculo se transforme em filtro vazio e apague o acervo.
        return None
    return clausulas[0] if len(clausulas) == 1 else {"$or": clausulas}


class RepositorioSimulados:
    def __init__(self, banco=None):
        self._banco = banco

    @property
    def banco(self):
        return self._banco if self._banco is not None else db.banco_dados

    @property
    def colecao(self):
        return self.banco[COLECAO]

    def buscar_obra(self, obra_id):
        return self.banco["tbl_obras"].find_one({"_id": obra_id})

    def listar_marcos(self, obra_id):
        return list(self.banco["tbl_marcos"].find({"obra_id": obra_id}).sort("_id", 1))

    def listar_avancos(self, marcos):
        """Avanços dos marcos informados, usados como contexto das atualizações."""
        ids = list(marcos)
        if not ids:
            return []
        return list(self.banco["tbl_avancos"].find({"marco_id": {"$in": ids}}).sort("_id", 1))

    def consultar_midias(self, avanco_id):
        """Evidências de um avanço que ainda não tem snapshot de publicação."""
        return list(self.banco["tbl_midias"].find(
            {"avanco_id": avanco_id}).sort("_id", 1))

    def listar_feedbacks(self, filtro):
        """Ordem estável pelo instante do exemplo, com o identificador no desempate."""
        return list(self.colecao.find(filtro).sort(
            [("registrado_em", 1), ("_id", 1)]))

    def listar_do_conjunto(self, filtro, *, session=None):
        if filtro is None:
            return []
        return list(self.colecao.find(filtro, session=session).sort("_id", 1))

    def remover_do_conjunto(self, filtro, *, session=None):
        """RN-09: o exemplo não sobrevive ao objeto que ele contextualiza."""
        if filtro is None:
            return 0
        return self.colecao.delete_many(filtro, session=session).deleted_count


_repositorio = RepositorioSimulados()


def remover_dos_avancos(avancos, *, session=None, banco=None):
    """Chamada pela exclusão individual de avanço (UC-18)."""
    repositorio = RepositorioSimulados(banco) if banco is not None else _repositorio
    return repositorio.remover_do_conjunto(
        filtro_do_conjunto(avancos=avancos), session=session)
