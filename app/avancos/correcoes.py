"""Correção versionada de publicações com compensação de uploads."""

from datetime import date, datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError
from uuid import uuid4

from . import repository
from .acesso_midias import midia_para_dict
from .service import ErroAvanco
from .versoes import _conteudo, consultar_versoes
from .revisoes import ConflitoRascunho
from .midias import ServicoMidias, ResultadoPersistenciaIndeterminado
from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
from app.publicacoes.validacoes import validar_midias


def corrigir_publicacao(avanco_id, dados, autor, arquivos=(), *, servico_midias=None):
    arquivos = list(arquivos)
    try:
        identificador = ObjectId(avanco_id)
    except (InvalidId, TypeError):
        raise ErroAvanco("Identificador inválido", 400, ["avanco_id"]) from None
    if not isinstance(dados, dict):
        raise ErroAvanco("Envie um objeto JSON", 422, ["corpo"])
    extras = set(dados) - {"motivo", "descricao", "data", "midias_manter"}
    if extras:
        raise ErroAvanco("Campos não permitidos", 422, sorted(extras))
    motivo = dados.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErroAvanco("Informe o motivo", 422, ["motivo"])
    if not arquivos and not any(campo in dados for campo in ("descricao", "data", "midias_manter")):
        raise ErroAvanco("Informe uma alteração", 422, ["corpo"])
    for campo in ("descricao", "data"):
        if campo in dados and (not isinstance(dados[campo], str) or not dados[campo].strip()):
            raise ErroAvanco("Informe um texto válido", 422, [campo])
    if "data" in dados:
        try:
            data = date.fromisoformat(dados["data"])
        except ValueError:
            raise ErroAvanco("Informe uma data válida no formato AAAA-MM-DD", 422, ["data"]) from None
        if data.isoformat() != dados["data"]:
            raise ErroAvanco("Informe uma data válida no formato AAAA-MM-DD", 422, ["data"])
    documento = repository.buscar_avanco(identificador)
    if documento is None:
        raise ErroAvanco("Avanço não encontrado", 404, ["avanco_id"])
    if documento.get("estado") != "publicado" or not documento.get("publicacao"):
        raise ErroAvanco("Somente publicações podem ser corrigidas", 409, ["estado"])
    cadeia = consultar_versoes(avanco_id)["versoes"]
    antes = cadeia[-1]["conteudo"]
    depois = {**antes, "midias": list(antes["midias"])}
    for campo in ("descricao", "data"):
        if campo in dados:
            depois[campo] = dados[campo].strip()
    if "midias_manter" in dados:
        ids = dados["midias_manter"]
        if (not isinstance(ids, list) or (not ids and not arquivos) or
                any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids)):
            raise ErroAvanco("Informe uma lista não vazia de mídias", 422, ["midias_manter"])
        disponiveis = {str(item["_id"]): item for item in repository.consultar_midias(identificador)}
        if any(item not in disponiveis for item in ids):
            raise ErroAvanco("A mídia não pertence ao avanço", 422, ["midias_manter"])
        selecionadas = [disponiveis[item] for item in ids]
        if selecionadas:
            if not validar_midias(selecionadas):
                raise ErroAvanco("Uma mídia selecionada é inválida", 422, ["midias_manter"])
            try:
                servico_midias = servico_midias or ServicoMidias()
                for midia in selecionadas:
                    servico_midias.armazenamento.obter_conteudo(
                        midia["referencia_externa"], midia["tamanho"]
                    )
            except ErroArmazenamento as erro:
                status = 422 if erro.status in (404, 422) else 503
                raise ErroAvanco("Mídia selecionada indisponível", status, ["midias_manter"]) from None
            except ValueError:
                raise ErroAvanco("Armazenamento indisponível", 503, ["midias_manter"]) from None
        depois["midias"] = [_conteudo({"data": antes["data"], "descricao": antes["descricao"],
                            "midias": [midia_para_dict(disponiveis[item])]})["midias"][0]
                            for item in ids]
        for item in depois["midias"]:
            item["conteudo"] = f"/midias/{item['id']}/conteudo"
    if not depois["midias"] and not arquivos and (antes["midias"] or "midias_manter" in dados):
        raise ErroAvanco("Mantenha ao menos uma mídia", 422, ["midias_manter"])
    instante = datetime.now(timezone.utc)
    operacao_id = uuid4().hex if arquivos else None

    def salvar(enviadas):
        novas = [{**item, "_id": ObjectId(), "avanco_id": identificador,
                  "data_envio": instante} for item in enviadas]
        for midia in novas:
            item = midia_para_dict(midia)
            item["conteudo"] = f"/midias/{item['id']}/conteudo"
            depois["midias"].append(item)
        if depois == antes:
            raise ErroAvanco("A correção precisa modificar a publicação", 422, ["corpo"])
        correcao = {"antes": antes, "depois": depois, "motivo": motivo.strip(),
                    "autor": autor, "instante": instante}
        try:
            repository.salvar_correcao_publicada(documento, correcao, depois, novas, operacao_id)
        except PyMongoError as erro:
            if erro.has_error_label("UnknownTransactionCommitResult"):
                raise ResultadoPersistenciaIndeterminado(
                    [item["referencia_externa"] for item in novas]
                ) from None
            raise

    try:
        if arquivos:
            servico_midias = servico_midias or ServicoMidias()

            def reservar(_validados):
                repository.criar_operacao({"_id": operacao_id, "avanco_id": identificador,
                                           "estado": "pendente", "referencias": [],
                                           "iniciado_em": instante})

            try:
                servico_midias.executar_com_midias(
                    arquivos, salvar, antes_envio=reservar,
                    registrar_referencia=lambda referencia: repository.registrar_referencia(
                        operacao_id, referencia),
                )
            except (ResultadoPersistenciaIndeterminado,):
                raise
            except ErroLimpeza:
                # O diário guarda as referências cuja remoção não foi confirmada.
                raise
            except Exception:
                repository.remover_operacao_pendente(operacao_id)
                raise
        else:
            salvar([])
    except ConflitoRascunho:
        raise ErroAvanco("A publicação foi alterada; consulte novamente", 409, ["avanco_id"]) from None
    return consultar_versoes(avanco_id)
