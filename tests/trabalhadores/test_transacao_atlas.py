"""Rollback real: exige --atlas e TEST_MONGO_URI de um banco tests_ separado."""

import pytest
from pymongo.errors import PyMongoError

from support import snapshot


pytestmark = pytest.mark.atlas


@pytest.mark.parametrize("collection,operation", [
    ("colecao_trabalhadores", "insert_one"), ("colecao_obras", "update_one"),
])
def test_falha_apos_gravacao_reverte_transacao_real(
    client, headers, database, trabalhador, obra_existente,
    modulo_trabalhadores, monkeypatch, collection, operation
):
    """Escreve na transação real antes de provocar o erro e conferir o rollback."""
    colecao = getattr(modulo_trabalhadores, collection)
    original = getattr(colecao, operation)
    before = snapshot(database)
    gravacoes = []

    def gravar_e_falhar(*args, **kwargs):
        assert kwargs["session"].in_transaction
        resultado = original(*args, **kwargs)
        gravacoes.append(resultado)
        raise PyMongoError("Falha provocada depois de gravar na transação")

    with monkeypatch.context() as context:
        context.setattr(colecao, operation, gravar_e_falhar)
        response = client.post(
            f"/trabalhadores/obra/{obra_existente['_id']}/", json=trabalhador, headers=headers
        )

    assert len(gravacoes) == 1
    assert response.status_code == 500
    # Consulta fora da sessão: nenhuma das duas coleções pode manter a escrita.
    assert snapshot(database) == before
