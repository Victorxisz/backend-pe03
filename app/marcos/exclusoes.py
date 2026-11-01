"""Cascata de exclusão de um marco (UC-17, F-19, RN-09, CA-09).

O marco leva seus avanços, publicações, versões, mídias, a trilha de mudanças
de estado e os exemplos simulados desses avanços. A obra e os outros marcos
permanecem: deles sai apenas o vínculo de dependência que apontava para o alvo.

Política pendente de confirmação (ver `docs/07-plano-e-decisoes.md`, P-08): a
ocorrência vinculada ao marco é removida com ele. É a proposta implementada,
não uma decisão já aprovada pelo grupo; alterá-la troca `OCORRENCIAS_NA_CASCATA`
e o trecho correspondente de CT-82.
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
from app.simulados.repository import RepositorioSimulados

from . import repository

TIPO = "marco"
OCORRENCIAS_NA_CASCATA = True


class ServicoExclusaoMarco:
    def __init__(self, repositorio=None, avancos=None, ocorrencias=None, historico=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.avancos = avancos if avancos is not None else avancos_repository
        self.ocorrencias = ocorrencias if ocorrencias is not None else RepositorioOcorrencias()
        self.historico = historico if historico is not None else RepositorioHistorico()

    def excluir(self, marco_id, dados, autor):
        """Valida sessão, alvo, vínculo com a obra e confirmação antes de remover."""
        identificador = self._identificar(marco_id)
        marco = self.repositorio.buscar_marco_por_id(identificador)
        if marco is None:
            # Repetir o DELETE retoma uma limpeza externa ainda pendente.
            if retomar_pendencia(TIPO, identificador):
                return
            raise self._ausente()
        obra = self.repositorio.buscar_obra_por_id(marco.get("obra_id"))
        if obra is None or (obra.get("autor") and str(obra["autor"]) != autor):
            raise self._ausente()
        conjunto = self.mapear(marco, obra)
        exigir_confirmacao(dados, conjunto.alvo, conjunto.perda)
        aplicar(conjunto)

    def mapear(self, marco, obra):
        """Descreve o conjunto dependente e a extensão da perda."""
        marco_id, obra_id = marco["_id"], obra["_id"]
        avancos = self.avancos.listar_avancos_de_marcos([marco_id])
        ids_avancos = [avanco["_id"] for avanco in avancos]
        midias = self.avancos.consultar_midias_de_avancos(ids_avancos)
        ocorrencias = (self.ocorrencias.listar_do_conjunto({"marco_id": marco_id})
                       if OCORRENCIAS_NA_CASCATA else [])
        ids_ocorrencias = [item["_id"] for item in ocorrencias]
        evidencias = [midia for item in ocorrencias for midia in item.get("midias", [])]
        eventos = self.historico.listar_eventos_dos_alvos([marco_id])
        vinculos = [
            elo for elo in obra.get("dependencias_marcos", [])
            if marco_id in (elo.get("marco_id"), elo.get("depende_de_id"))
        ]

        perda = {
            **resumo_dos_avancos(avancos),
            **resumo_das_ocorrencias(ocorrencias),
            "midias": len(midias) + len(evidencias),
            "historico": len(eventos),
            "dependencias": len(vinculos),
        }
        perda["exemplos_simulados"] += RepositorioSimulados().contar({"marco_id": marco_id})
        ids = (marco_id, *ids_avancos, *ids_ocorrencias,
               *(midia["_id"] for midia in midias),
               *(midia["_id"] for midia in evidencias))

        def remover(sessao):
            RepositorioSimulados().remover({"marco_id": marco_id}, session=sessao)
            # Relê os avanços na transação: remove o que pertence ao marco no
            # instante do commit, não só o que o mapeamento tinha visto.
            pendentes = self.avancos.listar_avancos_de_marcos([marco_id], session=sessao)
            self.avancos.remover_avancos(
                [avanco["_id"] for avanco in pendentes], session=sessao)
            if OCORRENCIAS_NA_CASCATA:
                self.ocorrencias.remover(
                    [item["_id"] for item in self.ocorrencias.listar_do_conjunto(
                        {"marco_id": marco_id}, session=sessao)], session=sessao)
            else:
                # Sem a cascata, o vínculo precisa sair para não restar órfão.
                self.ocorrencias.desvincular_marco(marco_id, session=sessao)
            self.historico.remover_eventos_dos_alvos([marco_id], session=sessao)
            # Os outros marcos continuam; só a relação com o alvo desaparece.
            self.repositorio.desvincular_marco(obra_id, marco_id, session=sessao)
            self.repositorio.remover_marco(marco_id, session=sessao)

        def relistar(sessao):
            pendentes = self.avancos.listar_avancos_de_marcos([marco_id], session=sessao)
            encontradas = self.avancos.consultar_midias_de_avancos(
                [avanco["_id"] for avanco in pendentes], session=sessao)
            atualizadas = (self.ocorrencias.listar_do_conjunto(
                {"marco_id": marco_id}, session=sessao) if OCORRENCIAS_NA_CASCATA else [])
            return encontradas + [
                midia for item in atualizadas for midia in item.get("midias", [])
            ]

        return Conjunto(
            alvo={"tipo": TIPO, "id": marco_id, "nome": marco.get("nome", "Marco"),
                  "obra_id": obra_id},
            perda=perda,
            ids=ids,
            midias=tuple(midias + evidencias),
            remover=remover,
            relistar=relistar,
        )

    def _ausente(self):
        return ErroExclusao("Marco não encontrado", 404, ["marco_id"],
                            codigo="MARCO_NAO_ENCONTRADO")

    def _identificar(self, valor):
        try:
            if not isinstance(valor, (str, ObjectId)):
                raise TypeError
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroExclusao("ID do marco inválido", 400, ["marco_id"],
                               codigo="ID_INVALIDO") from None


_servico = ServicoExclusaoMarco()

excluir_marco = _servico.excluir
mapear_conjunto = _servico.mapear
