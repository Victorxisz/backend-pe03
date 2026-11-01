"""Cascata de exclusão de uma obra (UC-17, F-19, RN-09, CA-09).

A obra leva marcos, avanços, publicações, versões, mídias, mudanças,
ocorrências com históricos/aceitações e os exemplos simulados que só existem
nesses avanços. Trabalhador não é excluído: perde apenas o vínculo com esta
obra. A mecânica durável da remoção fica em :mod:`app.exclusoes`.
"""

from bson import ObjectId
from bson.errors import InvalidId

from app.avancos import repository as avancos_repository
from app.exclusoes import (
    Conjunto,
    ErroExclusao,
    aplicar,
    exigir_confirmacao,
    resumo_das_ocorrencias,
    resumo_dos_avancos,
    retomar_pendencia,
)
from app.historico.repository import RepositorioHistorico
from app.ocorrencias.repository import RepositorioOcorrencias
from app.trabalhadores.repository import RepositorioTrabalhadores

from . import repository

TIPO = "obra"


class ServicoExclusaoObra:
    def __init__(self, repositorio=None, avancos=None, ocorrencias=None,
                 historico=None, trabalhadores=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.avancos = avancos if avancos is not None else avancos_repository
        self.ocorrencias = ocorrencias if ocorrencias is not None else RepositorioOcorrencias()
        self.historico = historico if historico is not None else RepositorioHistorico()
        self.trabalhadores = trabalhadores if trabalhadores is not None else RepositorioTrabalhadores()

    def excluir(self, obra_id, dados, autor):
        """Valida sessão, alvo e confirmação antes de qualquer remoção."""
        identificador = self._identificar(obra_id)
        obra = self.repositorio.buscar_obra_por_id(identificador)
        if obra is None:
            # Repetir o DELETE retoma uma limpeza externa ainda pendente.
            if retomar_pendencia(TIPO, identificador):
                return
            raise ErroExclusao("Obra não encontrada", 404, ["obra_id"],
                               codigo="OBRA_NAO_ENCONTRADA")
        if obra.get("autor") and str(obra["autor"]) != autor:
            raise ErroExclusao("Obra não encontrada", 404, ["obra_id"],
                               codigo="OBRA_NAO_ENCONTRADA")
        conjunto = self.mapear(obra)
        exigir_confirmacao(dados, conjunto.alvo, conjunto.perda)
        aplicar(conjunto)

    def mapear(self, obra):
        """Descreve o conjunto dependente e a extensão da perda."""
        obra_id = obra["_id"]
        marcos = self.repositorio.ids_dos_marcos(obra_id)
        avancos = self.avancos.listar_avancos_de_marcos(marcos)
        ids_avancos = [avanco["_id"] for avanco in avancos]
        midias = self.avancos.consultar_midias_de_avancos(ids_avancos)
        ocorrencias = self.ocorrencias.listar_do_conjunto({"obra_id": obra_id})
        ids_ocorrencias = [item["_id"] for item in ocorrencias]
        evidencias = [midia for item in ocorrencias for midia in item.get("midias", [])]
        eventos = self.historico.listar_eventos_dos_alvos([obra_id, *marcos])
        vinculados = self.trabalhadores.vinculados_a_obra(obra_id)

        perda = {
            "marcos": len(marcos),
            **resumo_dos_avancos(avancos),
            **resumo_das_ocorrencias(ocorrencias),
            "midias": len(midias) + len(evidencias),
            "mudancas": len(obra.get("historico_mudancas", [])),
            "estados": len(obra.get("historico_estados", [])),
            "dependencias": len(obra.get("dependencias_marcos", [])),
            "historico": len(eventos),
            "trabalhadores_desvinculados": len(vinculados),
        }
        ids = (obra_id, *marcos, *ids_avancos, *ids_ocorrencias,
               *(midia["_id"] for midia in midias),
               *(midia["_id"] for midia in evidencias))

        def remover(sessao):
            # Relê o conjunto na transação: remove o que pertence à obra no
            # instante do commit, não só o que o mapeamento tinha visto.
            atuais = self.repositorio.ids_dos_marcos(obra_id, session=sessao)
            pendentes = self.avancos.listar_avancos_de_marcos(atuais, session=sessao)
            self.avancos.remover_avancos(
                [avanco["_id"] for avanco in pendentes], session=sessao)
            self.ocorrencias.remover(
                [item["_id"] for item in self.ocorrencias.listar_do_conjunto(
                    {"obra_id": obra_id}, session=sessao)], session=sessao)
            self.historico.remover_eventos_dos_alvos([obra_id, *atuais], session=sessao)
            self.trabalhadores.desvincular_obra(obra_id, session=sessao)
            self.repositorio.remover_obra(obra_id, session=sessao)

        def relistar(sessao):
            atuais = self.repositorio.ids_dos_marcos(obra_id, session=sessao)
            pendentes = self.avancos.listar_avancos_de_marcos(atuais, session=sessao)
            encontradas = self.avancos.consultar_midias_de_avancos(
                [avanco["_id"] for avanco in pendentes], session=sessao)
            atualizadas = self.ocorrencias.listar_do_conjunto(
                {"obra_id": obra_id}, session=sessao)
            return encontradas + [
                midia for item in atualizadas for midia in item.get("midias", [])
            ]

        return Conjunto(
            alvo={"tipo": TIPO, "id": obra_id, "nome": obra.get("nome", "Obra")},
            perda=perda,
            ids=ids,
            midias=tuple(midias + evidencias),
            remover=remover,
            relistar=relistar,
        )

    def _identificar(self, valor):
        try:
            if not isinstance(valor, (str, ObjectId)):
                raise TypeError
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroExclusao("ID da obra inválido", 400, ["obra_id"],
                               codigo="ID_INVALIDO") from None


_servico = ServicoExclusaoObra()

excluir_obra = _servico.excluir
mapear_conjunto = _servico.mapear
