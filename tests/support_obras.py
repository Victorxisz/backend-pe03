"""Preparação e verificações compartilhadas dos contratos de obras."""

from copy import deepcopy
from datetime import datetime, timezone
import pytest
from bson import ObjectId

BASE = "/obras"
ID = "507f1f77bcf86cd799439011"
DETAIL = BASE + "/" + ID
routes = pytest.mark.routes


def assert_error(response, status, field=None):
    assert response.status_code == status, response.get_data(as_text=True)
    body = response.get_json()
    assert isinstance(body, dict), "Erro deve retornar objeto JSON"
    assert isinstance(body.get("mensagem"), str) and body["mensagem"].strip(), body
    if field:
        assert field in body.get("campos", []), body



def seed(database, obra, **changes):
    doc = deepcopy(obra)
    doc.update(
        _id=ObjectId(ID),
        estado="em andamento",
        autor="construtora_teste",
        data_registro=datetime(2030, 10, 10, 15, tzinfo=timezone.utc),
    )
    doc.update(changes)
    database.tbl_obras.insert_one(doc)
    return doc



def assert_created(response, database, payload):
    assert response.status_code == 201, response.get_data(as_text=True)
    body = response.get_json()
    identifier = body["id"]
    assert response.headers["Location"].endswith(BASE + "/" + identifier)
    saved = database.tbl_obras.find_one({"_id": ObjectId(identifier)})
    assert saved is not None, "201 sem documento persistido"
    for field, value in payload.items():
        assert saved[field] == value, f"Campo salvo incorreto: {field}"
        assert body[field] == value, f"Campo retornado incorreto: {field}"
    account = database.tbl_construtora.find_one({"email": "construtora@example.com"})
    assert saved["autor"] == body["autor"] == str(account["_id"])
    instant = datetime.fromisoformat(body["data_registro"].replace("Z", "+00:00"))
    assert instant.tzinfo is not None
    assert instant == datetime(2030, 10, 20, 12, tzinfo=timezone.utc)
    assert saved["data_registro"].replace(tzinfo=timezone.utc) == instant
    return body

