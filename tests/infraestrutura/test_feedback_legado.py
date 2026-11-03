"""Compatibilidade das exclusões com vínculos de bancos antigos."""

from bson import ObjectId
import pytest

from app.feedback_legado import RepositorioFeedbackLegado, filtro_do_conjunto


@pytest.mark.parametrize("campo", ["obra_id", "marco_id", "avanco_id"])
def test_limpeza_remove_somente_os_vinculos_do_alvo(database, campo):
    alvo, outro = ObjectId(), ObjectId()
    colecao = database["tbl_feedback_simulado"]
    colecao.insert_many([{campo: alvo}, {campo: outro}])
    argumentos = {"obra_id": alvo} if campo == "obra_id" else {
        "marcos" if campo == "marco_id" else "avancos": [alvo]}
    filtro = filtro_do_conjunto(**argumentos)
    repo = RepositorioFeedbackLegado(database)
    assert len(repo.listar_do_conjunto(filtro)) == 1
    assert repo.remover_do_conjunto(filtro) == 1
    assert colecao.count_documents({campo: outro}) == 1


def test_sem_alvo_nao_remove_o_acervo(database):
    database["tbl_feedback_simulado"].insert_one({"obra_id": ObjectId()})
    repo = RepositorioFeedbackLegado(database)
    filtro = filtro_do_conjunto()
    assert repo.listar_do_conjunto(filtro) == []
    assert repo.remover_do_conjunto(filtro) == 0
    assert repo.colecao.count_documents({}) == 1
