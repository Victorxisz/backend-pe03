"""Carga repetível dos exemplos simulados de UC-21 (F-17, F-18, RN-10, CA-08).

Procedimento de demonstração, não formulário do produto: o MVP não cria conta,
login ou endpoint de envio para comprador e engenheiro. A carga só escreve
exemplos fictícios e nunca remove dados alheios ao cenário.

Repetir a execução não duplica nada: cada exemplo tem chave natural
``(obra_id, exemplo)`` e o avanço do engenheiro é reconhecido por
``origem_simulada.exemplo``. Um avanço já corrigido pela construtora é
preservado como está, com autoria original e versões intactas.

Uso::

    python scripts/carregar_dados_demonstracao.py --obra <obraId>
    python scripts/carregar_dados_demonstracao.py --obra <obraId> --avanco <avancoId>
    python scripts/carregar_dados_demonstracao.py --obra <obraId> --sem-midia --json

A obra e o marco precisam existir: são criados pelo produto (UC-02 e UC-05).
Sem ``--avanco``, o exemplo do engenheiro é criado com uma foto de placeholder
enviada ao provedor configurado; ``--sem-midia`` dispensa o envio, mas o avanço
resultante não pode ser corrigido por UC-11, que exige ao menos uma mídia.
"""

import argparse
import json
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

CARGA = "demonstracao-uc21"
VERSAO_CARGA = 1

# Identidade fictícia do comprador de referência. Não há login deste perfil.
COMPRADOR = {
    "simulado": True,
    "perfil": "comprador",
    "nome": "Helena Marques",
    "identidade": "ficticia",
    "autenticado": False,
    "procedencia": "carga_demonstracao",
    "observacao": ("Pessoa fictícia. O MVP não cria conta, login ou formulário "
                   "de envio para o comprador."),
}

# Identidade fictícia do engenheiro a quem o avanço de exemplo é atribuído.
ENGENHEIRO = {
    "simulado": True,
    "perfil": "engenheiro",
    "nome": "Rafael Nogueira",
    "identidade": "ficticia",
    "registro_profissional": "CREA-SP 000000/F (fictício)",
    "autenticado": False,
    "procedencia": "carga_demonstracao",
    "exemplo": "avanco-engenheiro",
    "observacao": ("Exemplo pré-carregado. Não existe login nem criação de "
                   "avanço pelo perfil de engenheiro no MVP."),
}

AUTOR_ENGENHEIRO = "simulado:engenheiro:rafael-nogueira"

ROTULOS_DE_ALVO = {"obra": "obra", "marco": "marco", "atualizacao": "atualização"}

AVANCO_ENGENHEIRO = {
    "dias": 7,
    "descricao": ("Concretagem da laje do segundo pavimento concluída e cura "
                  "acompanhada por três dias. Próxima etapa: alvenaria interna."),
    "nome_midia": "exemplo-simulado-engenheiro.png",
}

# Cada exemplo aparece somente no alvo indicado (CT-102, CT-103).
EXEMPLOS = (
    {
        "exemplo": "avaliacao-obra",
        "tipo": "avaliacao",
        "alvo": "obra",
        "dias": 12,
        "conteudo": {
            "nota": 4,
            "escala": 5,
            "comentario": ("Acompanhar a obra por marcos deixou claro o que já "
                           "foi entregue. Senti falta de uma data provável para "
                           "a etapa seguinte."),
        },
    },
    {
        "exemplo": "compreensao-obra",
        "tipo": "compreensao",
        "alvo": "obra",
        "dias": 11,
        "conteudo": {
            "nivel": "claro",
            "comentario": ("Entendi o estágio geral da obra e o significado de "
                           "cada estado de marco apresentado."),
        },
    },
    {
        "exemplo": "duvida-obra",
        "tipo": "duvida",
        "alvo": "obra",
        "dias": 9,
        "conteudo": {
            "pergunta": ("A data de entrega combinada muda quando um marco "
                         "atrasa?"),
            "respondida": False,
        },
    },
    {
        "exemplo": "compreensao-marco",
        "tipo": "compreensao",
        "alvo": "marco",
        "dias": 6,
        "conteudo": {
            "nivel": "parcial",
            "comentario": ("Vi que esta etapa foi concluída, mas não sei o que "
                           "depende dela para começar."),
        },
    },
    {
        "exemplo": "duvida-atualizacao",
        "tipo": "duvida",
        "alvo": "atualizacao",
        "dias": 3,
        "conteudo": {
            "pergunta": ("A área mostrada nesta atualização já inclui a "
                         "impermeabilização da garagem?"),
            "respondida": False,
        },
    },
)


class ErroCarga(RuntimeError):
    """Impedimento do cenário: nada é escrito e a mensagem orienta o operador."""


def _identificar(valor, campo):
    try:
        if not isinstance(valor, (str, ObjectId)):
            raise TypeError
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise ErroCarga("Identificador inválido em " + campo + ": " + str(valor)) from None


def _resolver_obra(banco, obra_id):
    if obra_id is not None:
        obra = banco["tbl_obras"].find_one({"_id": _identificar(obra_id, "--obra")})
        if obra is None:
            raise ErroCarga("Obra não encontrada: " + str(obra_id))
        return obra
    obras = list(banco["tbl_obras"].find().sort("_id", 1))
    if not obras:
        raise ErroCarga("Nenhuma obra cadastrada. Crie a obra pelo produto (UC-02) "
                        "antes de carregar os exemplos.")
    if len(obras) > 1:
        candidatas = ", ".join(str(obra["_id"]) + " (" + str(obra.get("nome")) + ")"
                               for obra in obras)
        raise ErroCarga("Informe --obra; há mais de uma obra cadastrada: " + candidatas)
    return obras[0]


def _resolver_marco(banco, obra, marco_id):
    if marco_id is not None:
        identificador = _identificar(marco_id, "--marco")
        marco = banco["tbl_marcos"].find_one({"_id": identificador,
                                              "obra_id": obra["_id"]})
        if marco is None:
            raise ErroCarga("Marco não encontrado nesta obra: " + str(marco_id))
        return marco
    return banco["tbl_marcos"].find_one({"obra_id": obra["_id"]}, sort=[("_id", 1)])


def _ids_dos_marcos(banco, obra_id):
    return [documento["_id"] for documento in
            banco["tbl_marcos"].find({"obra_id": obra_id}, {"_id": 1}).sort("_id", 1)]


def _imagem_de_exemplo():
    """Placeholder gerado localmente, rotulado como exemplo simulado."""
    from PIL import Image, ImageDraw

    pequena = Image.new("RGB", (280, 158), (28, 42, 58))
    desenho = ImageDraw.Draw(pequena)
    desenho.rectangle((6, 6, 273, 151), outline=(242, 193, 78))
    for posicao, texto in ((14, "EXEMPLO SIMULADO"),
                           (34, "Avanco atribuido a"),
                           (46, "engenheiro ficticio"),
                           (70, "UC-21 / F-18 - carga de"),
                           (82, "demonstracao, nao e um"),
                           (94, "registro real de obra")):
        desenho.text((18, posicao), texto, fill=(255, 255, 255))
    arquivo = BytesIO()
    pequena.resize((840, 474), Image.NEAREST).save(arquivo, format="PNG")
    return arquivo.getvalue()


def _enviar_imagem(armazenamento, nome):
    from app.avancos.midias import ArquivoValidado
    from app.integracoes.armazenamento import ErroArmazenamento

    conteudo = _imagem_de_exemplo()
    arquivo = ArquivoValidado(conteudo=conteudo, tipo="foto", nome=nome,
                              mime="image/png", formato="png")
    try:
        return armazenamento.enviar(arquivo)
    except (ErroArmazenamento, ValueError) as erro:
        raise ErroCarga("Não foi possível enviar a foto do exemplo: " + str(erro)) from None


def _armazenamento_do_ambiente():
    from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento

    try:
        return ArmazenamentoCloudinary()
    except (ErroArmazenamento, ValueError):
        return None


def _snapshot_da_midia(midia):
    from app.avancos.acesso_midias import midia_para_dict

    publica = midia_para_dict(midia)
    publica["conteudo"] = "/midias/" + str(midia["_id"]) + "/conteudo"
    return publica


def _avanco_simulado_existente(banco, ids_marcos):
    return banco["tbl_avancos"].find_one({
        "origem_simulada.exemplo": ENGENHEIRO["exemplo"],
        "marco_id": {"$in": list(ids_marcos)},
    })


def _adotar_avanco(banco, obra, ids_marcos, avanco_id):
    """Marca um avanço publicado já existente como exemplo do engenheiro.

    A autoria anterior fica guardada em ``origem_simulada.autor_anterior``: a
    carga não apaga informação do registro que adota.
    """
    identificador = _identificar(avanco_id, "--avanco")
    documento = banco["tbl_avancos"].find_one({"_id": identificador})
    if documento is None or documento.get("marco_id") not in ids_marcos:
        raise ErroCarga("Avanço não encontrado nesta obra: " + str(avanco_id))
    if "origem_simulada" in documento:
        return documento, "mantido"
    if documento.get("estado") != "publicado" or not documento.get("publicacao"):
        raise ErroCarga("Somente um avanço publicado pode receber a origem "
                        "simulada do engenheiro: " + str(avanco_id))
    origem = dict(ENGENHEIRO, autor_anterior=documento.get("autor"))
    banco["tbl_avancos"].update_one(
        {"_id": identificador},
        {"$set": {"origem_simulada": origem, "autor": AUTOR_ENGENHEIRO,
                  "publicacao.autor": AUTOR_ENGENHEIRO}},
    )
    return banco["tbl_avancos"].find_one({"_id": identificador}), "adotado"


def _criar_avanco(banco, marco, instante, sem_midia, armazenamento):
    """Cria o avanço publicado do engenheiro simulado, com vínculos válidos."""
    data = (instante - timedelta(days=AVANCO_ENGENHEIRO["dias"])).date().isoformat()
    identificador = ObjectId()
    midias, enviada = [], None
    if not sem_midia:
        enviada = _enviar_imagem(armazenamento, AVANCO_ENGENHEIRO["nome_midia"])
        midias = [{"_id": ObjectId(), "avanco_id": identificador,
                   "data_envio": instante, **enviada}]
    documento = {
        "_id": identificador,
        "marco_id": marco["_id"],
        "data": data,
        "descricao": AVANCO_ENGENHEIRO["descricao"],
        "estado": "publicado",
        "autor": AUTOR_ENGENHEIRO,
        "data_registro": instante,
        "revisao": 1,
        "origem_simulada": dict(ENGENHEIRO),
        "publicacao": {
            "autor": AUTOR_ENGENHEIRO,
            "instante": instante,
            "data": data,
            "descricao": AVANCO_ENGENHEIRO["descricao"],
            "marco": {"id": marco["_id"], "nome": marco.get("nome", "Marco")},
            "midias": [_snapshot_da_midia(midia) for midia in midias],
        },
    }
    try:
        if midias:
            banco["tbl_midias"].insert_many(midias)
        banco["tbl_avancos"].insert_one(documento)
    except Exception:
        # Sem o avanço, nem metadados nem arquivo devem permanecer no acervo.
        banco["tbl_midias"].delete_many({"avanco_id": identificador})
        if enviada is not None:
            try:
                armazenamento.remover(enviada["referencia_externa"])
            except Exception:
                pass
        raise
    return documento, "criado"


def _preparar_engenheiro(banco, obra, marco, instante, *, avanco_id=None,
                         sem_midia=False, armazenamento=None):
    """Devolve (documento, situação, motivo) do exemplo atribuído ao engenheiro."""
    ids_marcos = _ids_dos_marcos(banco, obra["_id"])
    existente = _avanco_simulado_existente(banco, ids_marcos)
    if existente is not None:
        # Preserva correções da construtora e a autoria original do exemplo.
        return existente, "mantido", None
    if avanco_id is not None:
        documento, situacao = _adotar_avanco(banco, obra, ids_marcos, avanco_id)
        return documento, situacao, None
    if marco is None:
        return None, "ignorado", ("a obra não tem marco; crie o marco pelo "
                                  "produto (UC-05) ou use --marco")
    if not sem_midia:
        armazenamento = armazenamento or _armazenamento_do_ambiente()
        if armazenamento is None:
            return None, "ignorado", ("provedor de mídia não configurado; use "
                                      "--avanco para adotar um avanço publicado "
                                      "ou --sem-midia")
    documento, situacao = _criar_avanco(banco, marco, instante, sem_midia, armazenamento)
    return documento, situacao, None


def _alvos(obra, marco, avanco):
    return {
        "obra": {"id": obra["_id"], "obra_id": obra["_id"],
                 "marco_id": None, "avanco_id": None},
        "marco": None if marco is None else {
            "id": marco["_id"], "obra_id": obra["_id"],
            "marco_id": marco["_id"], "avanco_id": None},
        "atualizacao": None if avanco is None else {
            "id": avanco["_id"], "obra_id": obra["_id"],
            "marco_id": avanco.get("marco_id"), "avanco_id": avanco["_id"]},
    }


def _carregar_feedbacks(banco, obra, alvos, instante):
    from app.simulados.repository import COLECAO

    colecao = banco[COLECAO]
    # A chave natural impede duplicar o exemplo em uma segunda execução.
    colecao.create_index([("obra_id", 1), ("exemplo", 1)], unique=True)
    origem = dict(COMPRADOR, cliente_referencia=obra.get("cliente"))
    resultados = []
    for exemplo in EXEMPLOS:
        alvo = alvos[exemplo["alvo"]]
        if alvo is None:
            resultados.append({
                "exemplo": exemplo["exemplo"], "situacao": "ignorado",
                "motivo": "não há " + ROTULOS_DE_ALVO[exemplo["alvo"]] + " vinculável"})
            continue
        chave = {"obra_id": obra["_id"], "exemplo": exemplo["exemplo"]}
        conteudo = {
            "simulado": True,
            "tipo": exemplo["tipo"],
            "origem": origem,
            "alvo": {"tipo": exemplo["alvo"], "id": alvo["id"]},
            "marco_id": alvo["marco_id"],
            "avanco_id": alvo["avanco_id"],
            "conteudo": dict(exemplo["conteudo"]),
            "carga": {"nome": CARGA, "versao": VERSAO_CARGA},
        }
        existente = colecao.find_one(chave, {"_id": 1})
        if existente is None:
            documento = {
                "_id": ObjectId(), **chave, **conteudo,
                "registrado_em": instante - timedelta(days=exemplo["dias"]),
            }
            colecao.insert_one(documento)
            situacao, identificador = "criado", documento["_id"]
        else:
            # Reexecutar atualiza o conteúdo do exemplo, sem criar outro nem
            # alterar o instante com que ele foi registrado na primeira carga.
            colecao.update_one(chave, {"$set": conteudo})
            situacao, identificador = "mantido", existente["_id"]
        resultados.append({"exemplo": exemplo["exemplo"], "situacao": situacao,
                           "id": str(identificador), "tipo": exemplo["tipo"],
                           "alvo": exemplo["alvo"], "alvo_id": str(alvo["id"])})
    return resultados


def carregar(banco=None, *, obra_id=None, marco_id=None, avanco_id=None,
             sem_midia=False, armazenamento=None, relogio=None):
    """Executa a carga e devolve o relatório do que foi criado ou mantido."""
    if banco is None:
        import db

        banco = db.banco_dados
    if relogio is None:
        from app.dominio.comum import Relogio

        relogio = Relogio()
    instante = relogio.agora()

    obra = _resolver_obra(banco, obra_id)
    marco = _resolver_marco(banco, obra, marco_id)
    avanco, situacao, motivo = _preparar_engenheiro(
        banco, obra, marco, instante, avanco_id=avanco_id, sem_midia=sem_midia,
        armazenamento=armazenamento)
    feedbacks = _carregar_feedbacks(banco, obra, _alvos(obra, marco, avanco), instante)

    engenheiro = {"situacao": situacao}
    if avanco is not None:
        engenheiro.update(
            id=str(avanco["_id"]),
            marco_id=str(avanco.get("marco_id")),
            autor_original=avanco.get("autor"),
            midias=len(avanco.get("publicacao", {}).get("midias", [])),
            versoes=1 + len(avanco.get("correcoes") or []),
            corrigido_pela_construtora=bool(avanco.get("correcoes")),
        )
    if motivo:
        engenheiro["motivo"] = motivo
    return {
        "carga": CARGA,
        "obra": {"id": str(obra["_id"]), "nome": obra.get("nome"),
                 "cliente": obra.get("cliente")},
        "marco": None if marco is None else {"id": str(marco["_id"]),
                                             "nome": marco.get("nome")},
        "feedbacks": feedbacks,
        "avanco_simulado": engenheiro,
        "consulta": "/obras/" + str(obra["_id"]) + "/feedback-simulado",
    }


def _imprimir(relatorio):
    print("Carga " + relatorio["carga"])
    print("Obra: " + str(relatorio["obra"]["nome"]) + " (" + relatorio["obra"]["id"] + ")")
    if relatorio["marco"]:
        print("Marco: " + str(relatorio["marco"]["nome"]) + " (" + relatorio["marco"]["id"] + ")")
    for item in relatorio["feedbacks"]:
        linha = "  " + item["situacao"].ljust(9) + item["exemplo"]
        if item["situacao"] == "ignorado":
            linha += " - " + item["motivo"]
        else:
            linha += " -> " + item["alvo"] + " " + item["alvo_id"]
        print(linha)
    avanco = relatorio["avanco_simulado"]
    linha = "  " + avanco["situacao"].ljust(9) + "avanco-engenheiro"
    if "id" in avanco:
        linha += " -> " + avanco["id"] + " (midias: " + str(avanco["midias"]) + ")"
    if "motivo" in avanco:
        linha += " - " + avanco["motivo"]
    print(linha)
    print("Consulte em GET " + relatorio["consulta"])


def main(argv=None):
    analisador = argparse.ArgumentParser(
        description="Carga repetível dos exemplos simulados de UC-21.")
    analisador.add_argument("--obra", help="ID da obra que receberá os exemplos")
    analisador.add_argument("--marco", help="ID do marco usado como alvo e do avanço")
    analisador.add_argument("--avanco", help="adota um avanço publicado como exemplo "
                                             "do engenheiro, em vez de criar um")
    analisador.add_argument("--sem-midia", action="store_true",
                            help="cria o avanço simulado sem foto; UC-11 não "
                                 "corrige publicação sem mídia")
    analisador.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    argumentos = analisador.parse_args(argv)
    try:
        relatorio = carregar(obra_id=argumentos.obra, marco_id=argumentos.marco,
                             avanco_id=argumentos.avanco, sem_midia=argumentos.sem_midia)
    except ErroCarga as erro:
        print("Carga não executada: " + str(erro), file=sys.stderr)
        return 1
    if argumentos.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    else:
        _imprimir(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
