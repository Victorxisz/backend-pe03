"""Cenário compartilhado de publicação e histórico."""
from io import BytesIO
from unittest.mock import Mock

import pytest
from bson import ObjectId

from support import isolated_app, snapshot


from support_avancos import transacao_local

@pytest.fixture
def cenario(app, database, account, monkeypatch, transacao_local):
    for chave, valor in {"CLOUDINARY_CLOUD_NAME": "teste", "CLOUDINARY_API_KEY": "teste",
                         "CLOUDINARY_API_SECRET": "segredo-ficticio", "CLOUDINARY_FOLDER": "pe03/evidencias"}.items():
        monkeypatch.setenv(chave, valor)
    obra = ObjectId()
    marco = ObjectId()
    avanco = ObjectId()
    midia = ObjectId()
    database.tbl_obras.insert_one({"_id": obra, "nome": "Casa teste"})
    database.tbl_marcos.insert_one({"_id": marco, "obra_id": obra, "nome": "Fundação"})
    database.tbl_avancos.insert_one({"_id": avanco, "marco_id": marco, "data": "2030-10-19",
                                    "descricao": "Fundação concretada", "estado": "rascunho"})
    referencia = {"provedor": "cloudinary", "public_id": "pe03/evidencias/" + "a" * 32,
                  "resource_type": "image", "delivery_type": "authenticated", "formato": "png"}
    database.tbl_midias.insert_one({"_id": midia, "avanco_id": avanco, "tipo": "foto",
                                   "nome": "fundacao.png", "mime": "image/png", "tamanho": 3,
                                   "referencia_externa": referencia})
    resource = Mock(return_value={"public_id": referencia["public_id"]})
    download = Mock(side_effect=lambda *args, **kwargs: BytesIO(b"png"))
    monkeypatch.setattr("cloudinary.api.resource", resource)
    monkeypatch.setattr("app.integracoes.armazenamento.urlopen", download)
    monkeypatch.setattr("urllib.request.urlopen", download)
    return {"obra": obra, "marco": marco, "avanco": avanco, "midia": midia,
            "resource": resource, "download": download,
            "publicar": f"/avancos/{avanco}/publicacoes", "previa": f"/obras/{obra}/previa"}
