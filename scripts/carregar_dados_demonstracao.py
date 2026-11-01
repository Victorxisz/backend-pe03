"""Carga UC-21, explícita e repetível, sem endpoint de escrita no produto.

Usa obra/marco já existentes e envia uma evidência fictícia pelo serviço normal.
Nunca apaga dados nem sobrescreve exemplos ou correções após a primeira carga.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId


ENGENHEIRO = "Engenheiro fictício — demonstração UC-21"
CLIENTE = {"nome": "Comprador fictício — demonstração UC-21", "ficticio": True}


def carregar(obra_id, marco_id, autor, arquivo, *, data):
    import db
    from app.simulados.service import ServicoSimulados, ErroSimulado
    from app.avancos.service import criar_avanco
    from app.publicacoes.service import publicar_avanco

    obra_id, _, marco_id = ServicoSimulados().contexto(obra_id, autor, marco_id=marco_id)
    chave = f"uc21-{obra_id}-{marco_id}"
    origem = {"simulado": True, "perfil": "engenheiro", "nome": ENGENHEIRO, "ficticio": True}
    criado = criar_avanco(str(marco_id), {
        "data": data, "descricao": "Exemplo simulado: execução da etapa registrada pelo engenheiro fictício.",
    }, [arquivo], ENGENHEIRO, chave=chave, origem_simulada=origem)
    avanco_id = ObjectId(criado["id"])

    # A repetição não reescreve conteúdo, autoria, publicação ou correções.
    publicado, _ = publicar_avanco(str(avanco_id), ENGENHEIRO)

    exemplos = [
        ("obra", obra_id, "avaliacao", "Exemplo: estou satisfeito com as informações apresentadas."),
        ("obra", obra_id, "compreensao", "Exemplo: compreendi a sequência prevista para a obra."),
        ("obra", obra_id, "duvida", "Exemplo: quando será apresentada a próxima atualização?"),
        ("marco", marco_id, "duvida", "Exemplo: quais atividades faltam para concluir este marco?"),
        ("atualizacao", avanco_id, "compreensao", "Exemplo: a evidência ajudou a entender este avanço."),
    ]

    def gravar(sessao):
        # Escritas nos pais conflitam com exclusões concorrentes. Todos os
        # exemplos são inseridos juntos, ou nenhum deles é persistido.
        for colecao, filtro in (
            ("tbl_obras", {"_id": obra_id}),
            ("tbl_marcos", {"_id": marco_id, "obra_id": obra_id}),
            ("tbl_avancos", {"_id": avanco_id, "marco_id": marco_id, "estado": "publicado"}),
        ):
            resultado = db.banco_dados[colecao].update_one(
                filtro, {"$inc": {"_versao_simulados": 1}}, session=sessao)
            if resultado.matched_count != 1:
                raise ErroSimulado("Alvo removido durante a carga; execute novamente", 409)
        for tipo_alvo, alvo_id, tipo, texto in exemplos:
            identificador = ObjectId(hashlib.sha256(
                f"uc21:{obra_id}:{tipo_alvo}:{alvo_id}:{tipo}".encode()).hexdigest()[:24])
            documento = {
                "_id": identificador, "obra_id": obra_id,
                "alvo": {"tipo": tipo_alvo, "id": alvo_id}, "tipo": tipo,
                "texto": texto, "cliente": CLIENTE, "origem": "simulado",
            }
            if tipo_alvo != "obra":
                documento["marco_id"] = marco_id
            if tipo_alvo == "atualizacao":
                documento["atualizacao_id"] = avanco_id
            db.banco_dados["tbl_feedback_simulado"].update_one(
                {"_id": identificador}, {"$setOnInsert": documento}, upsert=True, session=sessao)

    with db.cliente_mongo.start_session() as sessao:
        sessao.with_transaction(gravar)
    return {"obra_id": str(obra_id), "marco_id": str(marco_id),
            "avanco_id": publicado["id"], "exemplos": len(exemplos), "simulado": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obra-id", required=True)
    parser.add_argument("--marco-id", required=True)
    parser.add_argument("--construtora-id", required=True)
    parser.add_argument("--arquivo", required=True, type=Path, help="Evidência fictícia: foto, vídeo ou documento")
    parser.add_argument("--data", required=True, help="Data do trabalho YYYY-MM-DD; mantenha igual nas repetições")
    args = parser.parse_args()
    from app import create_app
    from werkzeug.datastructures import FileStorage
    from app.simulados.service import ErroSimulado
    from app.avancos.service import ErroAvanco
    from app.publicacoes.service import ErroPublicacao
    from app.avancos.midias import ErroMidia, ResultadoPersistenciaIndeterminado
    from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
    from pymongo.errors import PyMongoError

    try:
        with create_app().app_context(), args.arquivo.open("rb") as stream:
            resultado = carregar(args.obra_id, args.marco_id, args.construtora_id,
                                 FileStorage(stream=stream, filename=args.arquivo.name), data=args.data)
        print(json.dumps(resultado, ensure_ascii=False))
    except (ErroSimulado, ErroAvanco, ErroPublicacao, ErroMidia,
            ErroArmazenamento, ErroLimpeza) as erro:
        parser.exit(1, f"Carga não concluída: {erro}\n")
    except (PyMongoError, ResultadoPersistenciaIndeterminado):
        parser.exit(1, "Carga não confirmada no banco. Verifique a conexão e os diários de upload antes de repetir.\n")
    except (OSError, ValueError):
        parser.exit(1, "Verifique o arquivo de evidência e a configuração do ambiente.\n")


if __name__ == "__main__":
    main()
