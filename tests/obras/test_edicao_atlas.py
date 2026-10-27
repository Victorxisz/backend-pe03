"""Integração UC-04 com MONGO_URI e coleções temporárias, sem depender do GET."""

import pytest
from bson import ObjectId

from mongo_support import BancoDaExecucao, conectar_mongo
from support import snapshot

ID = "507f1f77bcf86cd799439011"
PATH = "/obras/" + ID
pytestmark = [pytest.mark.atlas, pytest.mark.routes(("PATCH", PATH))]


@pytest.mark.parametrize(
    "changes,status,campos",
    [
        pytest.param(
            {"nome": "Nome corrigido", "cliente": "Cliente corrigido"},
            200,
            [],
            id="ct16-correcao",
        ),
        pytest.param(
            {
                "nome": "Não deve mudar",
                "entrega": {"modalidade": "data_exata", "data": "2031-01-01"},
            },
            422,
            ["entrega"],
            id="ct17-prazo",
        ),
        pytest.param({"estado": "concluída"}, 422, ["estado"], id="ct17-conclusao"),
    ],
)
def test_ct16_ct17_persistencia_atlas(
    client, headers, database, obra, changes, status, campos
):
    # Preparação
    database.tbl_obras.insert_one(
        {**obra, "_id": ObjectId(ID), "estado": "em andamento"}
    )
    before = snapshot(database)
    expected = (
        {**before["tbl_obras"][0], **changes}
        if status == 200
        else before["tbl_obras"][0]
    )

    # Execução
    response = client.patch(PATH, json=changes, headers=headers)
    # Conexão independente: nenhuma coleção/memória compartilhada com a aplicação.
    with conectar_mongo() as fresh:
        after = snapshot(BancoDaExecucao(fresh[database.name], database.prefixo))

    # Verificação
    assert response.status_code == status
    assert after["tbl_obras"] == [expected]
    if status == 422:
        assert response.get_json()["campos"] == campos
        assert response.get_json()["mensagem"]
        assert after == before
    else:
        assert response.get_json()["id"] == ID
        for field, value in changes.items():
            assert response.get_json()[field] == value
        assert {k: v for k, v in after.items() if k != "tbl_obras"} == {
            k: v for k, v in before.items() if k != "tbl_obras"
        }
