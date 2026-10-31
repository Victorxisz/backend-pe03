"""Reconciliação operacional com a aplicação parada e sem uploads em andamento."""

import argparse
import re

import db
from app.integracoes.armazenamento import ArmazenamentoCloudinary


def reconciliar(operacao_id, armazenamento, aplicacao_parada=False):
    if not aplicacao_parada:
        raise ValueError("Pare a aplicação e aguarde uploads em andamento")
    if not re.fullmatch(r"[0-9a-f]{64}", operacao_id):
        raise ValueError("Identificador de operação inválido")
    operacoes = db.banco_dados["tbl_uploads_pendentes"]
    operacao = operacoes.find_one({"_id": operacao_id})
    if operacao is None:
        raise ValueError("Operação não encontrada")
    if operacao["estado"] == "concluida":
        return "concluida"
    if operacao["estado"] == "limpa":
        return "limpa"
    if operacao["estado"] != "pendente":
        raise ValueError("Estado de operação desconhecido")
    # Uma inconsistência nunca autoriza apagar referências potencialmente ativas.
    if db.banco_dados["tbl_avancos"].find_one({"_id": operacao["avanco_id"]}):
        raise ValueError("Avanço encontrado com operação pendente; revise manualmente")
    for referencia in operacao.get("referencias", []):
        armazenamento.remover(
            referencia
        )  # Remoção idempotente; se falhar, permanece pendente.
    resultado = operacoes.update_one(
        {"_id": operacao_id, "estado": "pendente"}, {"$set": {"estado": "limpa"}}
    )
    if resultado.matched_count != 1:
        raise ValueError("Operação alterada durante reconciliação")
    return "limpa"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--listar", action="store_true")
    grupo.add_argument("--operacao")
    parser.add_argument("--servico-parado", action="store_true")
    args = parser.parse_args()
    if args.listar:
        for item in db.banco_dados["tbl_uploads_pendentes"].find(
            {"estado": "pendente"}
        ):
            print(item["_id"], str(item["avanco_id"]), item["iniciado_em"])
        return
    if not args.servico_parado:
        parser.error("Pare a aplicação e informe --servico-parado")
    print(reconciliar(args.operacao, ArmazenamentoCloudinary(), aplicacao_parada=True))


if __name__ == "__main__":
    main()
