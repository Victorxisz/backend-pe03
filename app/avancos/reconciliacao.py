"""Reconciliação operacional com a aplicação parada e sem uploads em andamento."""

import argparse
import re

import db
from app.integracoes.armazenamento import ArmazenamentoCloudinary
from .midias import chave_arquivo
from .rascunhos_repository import RepositorioRascunhos


def _exigir_parada(aplicacao_parada):
    if not aplicacao_parada:
        raise ValueError("Pare a aplicação e aguarde uploads em andamento")


class ServicoReconciliacao:
    def __init__(self, armazenamento, banco=None, repositorio=None):
        self.armazenamento = armazenamento
        self.banco = banco if banco is not None else db.banco_dados
        self.repositorio = repositorio if repositorio is not None else RepositorioRascunhos(banco=self.banco)

    def reconciliar(self, operacao_id, aplicacao_parada=False):
        _exigir_parada(aplicacao_parada)
        # Compatibilidade com UUIDs de correções criadas antes da padronização.
        if not isinstance(operacao_id, str) or not re.fullmatch(r"(?:[0-9a-f]{32}|[0-9a-f]{64})", operacao_id):
            raise ValueError("Identificador de operação inválido")
        operacoes = self.banco["tbl_uploads_pendentes"]
        operacao = operacoes.find_one({"_id": operacao_id})
        if operacao is None:
            raise ValueError("Operação não encontrada")
        if operacao["estado"] in {"concluida", "limpa"}:
            return operacao["estado"]
        if operacao["estado"] != "pendente":
            raise ValueError("Estado de operação desconhecido")
        ocorrencia = operacao.get("tipo") == "ocorrencia"
        avanco = None if ocorrencia else self.banco["tbl_avancos"].find_one({"_id": operacao["avanco_id"]})
        atualizacao = operacao.get("tipo") in {"edicao", "correcao"}
        legado_correcao = len(operacao_id) == 32 and avanco and avanco.get("estado") == "publicado"
        if avanco and not (atualizacao or legado_correcao):
            raise ValueError("Avanço encontrado com operação pendente; revise manualmente")
        referencias = operacao.get("referencias", [])
        # Valida o lote inteiro antes da primeira remoção.
        for referencia in referencias:
            chave_arquivo(referencia)
        preservadas = []
        for referencia in referencias:
            if self.repositorio.referencia_em_uso(referencia, operacao_ignorada=operacao_id):
                preservadas.append(referencia)
            else:
                self.armazenamento.remover(referencia)
        resultado = operacoes.update_one(
            {"_id": operacao_id, "estado": "pendente"},
            {"$set": {"estado": "limpa", "preservadas": preservadas}},
        )
        if resultado.matched_count != 1:
            raise ValueError("Operação alterada durante reconciliação")
        return "limpa"

    def limpar_removidas(self, aplicacao_parada=False):
        """Retoma as tarefas de mídias retiradas de rascunhos por edição."""
        _exigir_parada(aplicacao_parada)
        concluidas = 0
        for tarefa in self.banco["tbl_limpezas_midias"].find():
            midia = tarefa["midia"]
            referencia = midia["referencia_externa"]
            chave_arquivo(referencia)
            if self.repositorio.referencia_em_uso(referencia, ids_midias=[midia["_id"]]):
                continue
            self.armazenamento.remover(referencia)
            self.banco["tbl_limpezas_midias"].delete_one({"_id": tarefa["_id"]})
            concluidas += 1
        return concluidas


def reconciliar(operacao_id, armazenamento, aplicacao_parada=False):
    return ServicoReconciliacao(armazenamento).reconciliar(operacao_id, aplicacao_parada)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--listar", action="store_true")
    grupo.add_argument("--operacao")
    grupo.add_argument("--limpezas", action="store_true")
    parser.add_argument("--servico-parado", action="store_true")
    args = parser.parse_args()
    if args.listar:
        for item in db.banco_dados["tbl_uploads_pendentes"].find(
            {"estado": "pendente"}
        ):
            print(item["_id"], str(item.get("ocorrencia_id", item.get("avanco_id"))), item["iniciado_em"])
        return
    if not args.servico_parado:
        parser.error("Pare a aplicação e informe --servico-parado")
    servico = ServicoReconciliacao(ArmazenamentoCloudinary())
    if args.limpezas:
        print(servico.limpar_removidas(aplicacao_parada=True))
    else:
        print(servico.reconciliar(args.operacao, aplicacao_parada=True))


if __name__ == "__main__":
    main()
