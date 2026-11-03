from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)
from db import colecao_construtora

def _autorizar_recursos(identidade):
    # Autorização baseada na obra, inclusive para recursos acessados por ID.
    import db
    from bson import ObjectId
    args = request.view_args or {}
    banco = db.banco_dados

    def obter(colecao, valor):
        if not ObjectId.is_valid(valor):
            return None
        return banco[colecao].find_one({"_id": ObjectId(valor)})

    def obra_de_marco(valor):
        marco = obter("tbl_marcos", valor)
        return marco.get("obra_id") if marco else None

    def obra_de_avanco(valor):
        avanco = obter("tbl_avancos", valor)
        return obra_de_marco(avanco.get("marco_id")) if avanco else None

    def obra_de_midia(valor):
        midia = obter("tbl_midias", valor)
        if midia and midia.get("avanco_id"):
            return obra_de_avanco(midia["avanco_id"])
        if ObjectId.is_valid(valor):
            ocorrencia = banco["tbl_ocorrencias"].find_one({"midias._id": ObjectId(valor)})
            return ocorrencia.get("obra_id") if ocorrencia else None
        return None

    def obra_de_mudanca(valor):
        partes = valor.split(":")
        if len(partes) == 4 and partes[0] == "obra":
            return partes[1]
        if len(partes) == 3 and partes[0] == "publicacao":
            return obra_de_avanco(partes[1])
        evento = obter("tbl_historico", valor)
        return obra_de_marco(evento.get("alvo", {}).get("id")) if evento else None

    # Uma exclusão confirmada pode ter removido o alvo, deixando apenas o diário.
    if request.method == "DELETE":
        tipos = (("obra_id", "obra"), ("marco_id", "marco"), ("avanco_id", "avanco"), ("ocorrencia_id", "ocorrencia"))
        for chave, tipo in tipos:
            if chave not in args or not ObjectId.is_valid(args[chave]):
                continue
            alvo_id = ObjectId(args[chave])
            colecao = {"obra": "tbl_obras", "marco": "tbl_marcos", "avanco": "tbl_avancos", "ocorrencia": "tbl_ocorrencias"}[tipo]
            if obter(colecao, alvo_id) is None:
                pendencia = banco["tbl_exclusoes_pendentes"].find_one({"alvo.tipo": tipo, "alvo.id": alvo_id})
                # Diários antigos não guardam o proprietário e não autorizam retomada.
                if pendencia and pendencia.get("proprietario_id") == identidade:
                    return None

    referencias = []
    for chave, valor in args.items():
        if chave in ("obra_id", "marco_id", "avanco_id", "ocorrencia_id", "ocorrenciaId", "midia_id") and not ObjectId.is_valid(valor):
            if request.blueprint == "midias":
                return jsonify(mensagem="Identificador inválido", campos=[chave], codigo="ID_INVALIDO"), 400
            if request.blueprint == "trabalhadores" and chave == "obra_id":
                return jsonify(erro="ID da obra inválido"), 400
            return jsonify(mensagem="Identificador inválido", campos=["id"] if chave == "obra_id" and (request.blueprint == "obras" or request.endpoint == "marcos.consultar_marcos") else [chave]), 400
        if chave == "mudanca_id":
            partes = valor.split(":")
            valido = (len(partes) == 1 and ObjectId.is_valid(valor)) or (len(partes) == 4 and partes[0] == "obra" and ObjectId.is_valid(partes[1])) or (len(partes) == 3 and partes[0] == "publicacao" and ObjectId.is_valid(partes[1]))
            if not valido:
                return jsonify(mensagem="Identificador inválido", campos=[chave]), 400
        if chave == "obra_id": referencias.append(valor)
        elif chave == "marco_id": referencias.append(obra_de_marco(valor))
        elif chave == "avanco_id": referencias.append(obra_de_avanco(valor))
        elif chave in ("ocorrencia_id", "ocorrenciaId"):
            item = obter("tbl_ocorrencias", valor)
            referencias.append(item.get("obra_id") if item else None)
        elif chave == "midia_id": referencias.append(obra_de_midia(valor))
        elif chave == "mudanca_id": referencias.append(obra_de_mudanca(valor))
    if request.method == "POST" and request.endpoint == "marcos.cadastrar_dependencia":
        dados = request.get_json(silent=True)
        destino = dados.get("depende_de_id") if isinstance(dados, dict) else None
        if isinstance(destino, str) and ObjectId.is_valid(destino):
            referencias.append(obra_de_marco(destino))
    for obra_id in referencias:
        obra = obter("tbl_obras", obra_id)
        if not obra or not obra.get("autor") or str(obra["autor"]) != identidade:
            if request.blueprint == "midias":
                codigo = "MIDIA_NAO_ENCONTRADA" if "midia_id" in args else "AVANCO_NAO_ENCONTRADO"
                return jsonify(mensagem="Registro não encontrado", codigo=codigo), 404
            if request.blueprint == "trabalhadores":
                return jsonify(erro="Obra não encontrada"), 404
            campo = next((k for k in args if k in ("obra_id", "marco_id", "avanco_id", "ocorrencia_id", "ocorrenciaId", "midia_id", "mudanca_id")), "id")
            return jsonify(mensagem="Registro não encontrado", campos=["id"] if campo == "obra_id" and (request.blueprint == "obras" or request.endpoint == "marcos.consultar_marcos") else [campo]), 404
    return None


def sessao_obrigatoria (funcao):
    @wraps(funcao)
    def verificar_sessao(*args, **kwargs):
        # O preflight CORS não executa a operação. JWT também isenta OPTIONS,
        # portanto não há claims para consultar nessa requisição do navegador.
        if request.method == "OPTIONS":
            return None
        # Verifica token, expiração e revogação.
        # Reutiliza a configuração do JWTManager em api.py
        verify_jwt_in_request()

        if get_jwt().get("tipo") != "construtora":
            return jsonify({
                "erro":"Você não tem permissão para realizar está ação"
            }), 403

        identidade = get_jwt_identity()

        if not isinstance(identidade, str):
            return jsonify({
                "erro":"Entre novamente em sua conta"
            }), 401

        try:
            construtora_id = ObjectId(identidade)
        except (InvalidId, TypeError):
            return jsonify({
                "erro":"Entre novamente em sua conta"
            }), 401

        construtora = colecao_construtora.find_one(
            {"_id":construtora_id},
            {"ativo":1},
        )

        if construtora is None or construtora.get("ativo") is not True:
            return jsonify({
                "erro":"Entre em uma conta ativa"
            }), 401

        negado = _autorizar_recursos(identidade)
        if negado is not None:
            return negado
        return funcao(*args, **kwargs)

    return verificar_sessao
