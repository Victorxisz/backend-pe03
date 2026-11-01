"""UC-17 / CT-79 a CT-85 e CT-100: exclusão em cascata de obra e de marco.

O MongoDB é simulado por padrão e o provedor de mídia é sempre simulado: estes
casos não comprovam a remoção real no Cloudinary nem o isolamento do Atlas.
`--atlas` habilita os cenários marcados, inclusive a releitura em outro processo.
"""

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bson import ObjectId

from support import isolated_app, snapshot
from support_avancos import transacao_local  # noqa: F401 - fixture de rollback local
from support_midias import config  # noqa: F401 - credenciais fictícias do provedor

OBRAS = "/obras/"
MARCOS = "/marcos/"
INSTANTE = datetime(2030, 10, 10, 15, tzinfo=timezone.utc)
routes = pytest.mark.routes


def _referencia(pasta, tipo="foto"):
    recurso, formato = {"foto": ("image", "png"), "video": ("video", "mp4"),
                        "documento": ("raw", "pdf")}[tipo]
    sufixo = ".pdf" if recurso == "raw" else ""
    return {"provedor": "cloudinary",
            "public_id": f"{pasta}/{ObjectId()}{'a' * 8}{sufixo}",
            "resource_type": recurso, "delivery_type": "authenticated",
            "formato": formato}


@pytest.fixture
def provedor(monkeypatch, config):
    """Objetos do provedor em memória; `falhas` injeta erro em um arquivo."""
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": config.cloud_name,
                         "CLOUDINARY_API_KEY": config.api_key,
                         "CLOUDINARY_API_SECRET": config.api_secret,
                         "CLOUDINARY_FOLDER": config.pasta}.items():
        monkeypatch.setenv(chave, valor)
    objetos, falhas = {}, set()

    def remover(public_id, resource_type, **opcoes):
        chave = (resource_type, public_id)
        if chave in falhas:
            raise TimeoutError("detalhe privado do provedor")
        existia = objetos.pop(chave, None) is not None
        return {"result": "ok" if existia else "not found"}

    destroy = Mock(side_effect=remover)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    return SimpleNamespace(objetos=objetos, falhas=falhas, destroy=destroy,
                           pasta=config.pasta)


def chave(referencia):
    return referencia["resource_type"], referencia["public_id"]


@pytest.fixture
def cenario(app, database, account, provedor):
    """Obra A completa, obra B preservada e um trabalhador nas duas."""
    autor = str(account["_id"])

    def midia(dono, tipo="foto", campo="avanco_id", referencia=None):
        ref = deepcopy(referencia) if referencia is not None else _referencia(provedor.pasta, tipo)
        provedor.objetos[chave(ref)] = b"arquivo-existente"
        return {"_id": ObjectId(), campo: dono, "tipo": tipo, "nome": "evidencia",
                "mime": {"foto": "image/png", "video": "video/mp4",
                         "documento": "application/pdf"}[tipo],
                "tamanho": 18, "data_envio": INSTANTE, "referencia_externa": ref}

    obra_a, obra_b = ObjectId(), ObjectId()
    m1, m2, m_b = ObjectId(), ObjectId(), ObjectId()
    vinculo = {"_id": ObjectId(), "marco_id": m2, "depende_de_id": m1}
    database.tbl_obras.insert_many([
        {"_id": obra_a, "nome": "Residencial Aurora", "tipo": "apartamentos",
         "cliente": "Cliente de referência", "localizacao": "Campinas, SP",
         "descricao": "Construção residencial", "inicio": "2030-01-15",
         "entrega": {"modalidade": "data_exata", "data": "2030-12-20"},
         "estado": "em andamento", "autor": autor, "data_registro": INSTANTE,
         "versao": 2, "revisao_estado": 1,
         "historico_estados": [{"tipo": "estado_obra", "alvo": {"tipo": "obra", "id": obra_a},
                                "campo": "estado", "valor_anterior": {"estado": "planejada"},
                                "valor_novo": {"estado": "em andamento"},
                                "motivo": "Início das obras", "autor": autor, "instante": INSTANTE}],
         "historico_mudancas": [{"tipo": "entrega_obra", "alvo": {"tipo": "obra", "id": obra_a},
                                 "campo": "entrega", "valor_anterior": {"entrega": {}},
                                 "valor_novo": {"entrega": {"modalidade": "data_exata",
                                                            "data": "2030-12-20"}},
                                 "motivo": "Replanejamento", "autor": autor, "instante": INSTANTE}],
         "dependencias_marcos": [vinculo]},
        {"_id": obra_b, "nome": "Obra preservada", "tipo": "casa",
         "cliente": "Outro cliente", "localizacao": "Valinhos, SP",
         "descricao": "Obra que não entra na cascata", "inicio": "2030-04-01",
         "entrega": {"modalidade": "data_exata", "data": "2031-01-10"},
         "estado": "planejada", "autor": autor, "data_registro": INSTANTE},
    ])
    database.tbl_marcos.insert_many([
        {"_id": m1, "obra_id": obra_a, "nome": "Fundação", "descricao": "Base",
         "inicio_previsto": "2030-02-01", "fim_previsto": "2030-03-01", "estado": "concluído",
         "versao": 1},
        {"_id": m2, "obra_id": obra_a, "nome": "Alvenaria", "descricao": "Paredes",
         "inicio_previsto": "2030-03-01", "fim_previsto": "2030-05-01", "estado": "a iniciar",
         "dependencias": [m1]},
        {"_id": m_b, "obra_id": obra_b, "nome": "Marco de outra obra", "estado": "a iniciar"},
    ])

    rascunho, publicado, avanco_b = ObjectId(), ObjectId(), ObjectId()
    midias_rascunho = [midia(rascunho, tipo) for tipo in ("foto", "video", "documento")]
    midia_publicada = midia(publicado)
    midia_retirada = midia(publicado)
    midia_outra_obra = midia(avanco_b)
    snapshot_publicacao = [{"id": str(midia_publicada["_id"]), "avanco_id": str(publicado),
                            "tipo": "foto", "nome": "evidencia", "tamanho": 18,
                            "mime": "image/png", "visibilidade": "privada"}]

    def fato(data, descricao, marco_id, nome, midias):
        return {"autor": autor, "instante": INSTANTE, "data": data, "descricao": descricao,
                "marco": {"id": marco_id, "nome": nome}, "midias": midias}

    database.tbl_avancos.insert_many([
        {"_id": rascunho, "marco_id": m1, "data": "2030-02-10", "descricao": "Rascunho",
         "estado": "rascunho", "autor": autor, "data_registro": INSTANTE, "revisao": 0},
        {"_id": publicado, "marco_id": m1, "data": "2030-02-20", "descricao": "Concretagem",
         "estado": "publicado", "autor": autor, "data_registro": INSTANTE, "revisao": 2,
         "editado": True, "origem_simulada": {"perfil": "engenheiro", "nome": "Engenheira exemplo"},
         "publicacao": fato("2030-02-20", "Concretagem da base", m1, "Fundação",
                            snapshot_publicacao),
         "correcoes": [{"motivo": "Correção da descrição", "autor": autor, "instante": INSTANTE,
                        "antes": {"data": "2030-02-20", "descricao": "Concretagem da base",
                                  "midias": snapshot_publicacao},
                        "depois": {"data": "2030-02-20", "descricao": "Concretagem",
                                   "midias": snapshot_publicacao}}]},
        {"_id": avanco_b, "marco_id": m_b, "data": "2030-02-20", "descricao": "Outra obra",
         "estado": "publicado", "autor": autor, "data_registro": INSTANTE,
         "publicacao": fato("2030-02-20", "Outra obra", m_b, "Marco de outra obra", [])},
    ])
    database.tbl_midias.insert_many(
        deepcopy(midias_rascunho + [midia_publicada, midia_outra_obra]))
    # Tarefa de limpeza pendente de uma edição anterior do mesmo avanço.
    database.tbl_limpezas_midias.insert_one(
        {"_id": midia_retirada["_id"], "avanco_id": publicado, "midia": deepcopy(midia_retirada)})
    database.tbl_uploads_pendentes.insert_one(
        {"_id": "a" * 64, "avanco_id": rascunho, "tipo": "edicao", "estado": "pendente",
         "referencias": [], "iniciado_em": INSTANTE})

    ocorrencia = ObjectId()
    evidencia = midia(ocorrencia, campo="ocorrencia_id")
    database.tbl_ocorrencias.insert_one(
        {"_id": ocorrencia, "obra_id": obra_a, "marco_id": m1, "autor": autor,
         "titulo": "Infiltração", "descricao": "Parede úmida", "estado": "sem solução",
         "responsavel_id": None, "data_registro": INSTANTE,
         "midias": [deepcopy(evidencia)],
         "aceitacoes": [{"justificativa": "Sem solução viável", "autor": autor, "data": INSTANTE}]})
    database.tbl_historico.insert_many([
        {"_id": ObjectId(), "tipo": "estado_marco", "alvo": {"tipo": "marco", "id": m1},
         "campo": "estado", "valor_anterior": {"estado": "em andamento"},
         "valor_novo": {"estado": "concluído"}, "motivo": "Etapa concluída",
         "autor": autor, "instante": INSTANTE},
        {"_id": ObjectId(), "tipo": "fim_previsto_marco", "alvo": {"tipo": "marco", "id": m2},
         "campo": "fim_previsto", "valor_anterior": {"fim_previsto": "2030-04-01"},
         "valor_novo": {"fim_previsto": "2030-05-01"}, "motivo": "Replanejamento",
         "autor": autor, "instante": INSTANTE},
    ])

    trabalhador_duplo, trabalhador_b = ObjectId(), ObjectId()
    database.tbl_trabalhadores.insert_many([
        {"_id": trabalhador_duplo, "nome": "Pessoa nas duas obras",
         "email": "duplo@example.com", "telefone": "19999990000", "cargo": "mestre de obras",
         "construtora_id": autor, "data_cadastro": INSTANTE, "ativo": True,
         "obras": [str(obra_a), str(obra_b)]},
        {"_id": trabalhador_b, "nome": "Somente na obra preservada",
         "email": "outro@example.com", "telefone": "19999990001", "cargo": "pedreiro",
         "construtora_id": autor, "data_cadastro": INSTANTE, "ativo": True,
         "obras": [str(obra_b)]},
    ])

    return SimpleNamespace(
        autor=autor, obra=obra_a, obra_b=obra_b, marco=m1, marco_dependente=m2, marco_b=m_b,
        vinculo=vinculo, rascunho=rascunho, publicado=publicado, avanco_b=avanco_b,
        ocorrencia=ocorrencia, evidencia=evidencia, midias_rascunho=midias_rascunho,
        midia_publicada=midia_publicada, midia_retirada=midia_retirada,
        midia_outra_obra=midia_outra_obra, trabalhador=trabalhador_duplo,
        trabalhador_b=trabalhador_b, midia=midia,
        caminho=OBRAS + str(obra_a), caminho_marco=MARCOS + str(m1),
        objetos=provedor.objetos, falhas=provedor.falhas, destroy=provedor.destroy,
    )


def ids_do_conjunto(cenario):
    return {cenario.obra, cenario.marco, cenario.marco_dependente, cenario.rascunho,
            cenario.publicado, cenario.ocorrencia, cenario.evidencia["_id"],
            cenario.midia_publicada["_id"], cenario.midia_retirada["_id"],
            *(midia["_id"] for midia in cenario.midias_rascunho)}


def arquivos_do_conjunto(cenario):
    return {chave(midia["referencia_externa"]) for midia in
            [*cenario.midias_rascunho, cenario.midia_publicada,
             cenario.midia_retirada, cenario.evidencia]}


def menciona(valor, identificadores):
    if isinstance(valor, dict):
        return any(menciona(item, identificadores) for item in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(menciona(item, identificadores) for item in valor)
    return isinstance(valor, (ObjectId, str)) and str(valor) in identificadores


def referencias_restantes(database, identificadores):
    textos = {str(valor) for valor in identificadores}
    achados = []
    for nome in database.list_collection_names():
        for documento in database[nome].find():
            if menciona(documento, textos):
                achados.append((nome, documento["_id"]))
    return achados
