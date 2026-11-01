"""UC-03/D-13: alerta derivado pode ser filtrado junto ao ciclo de vida."""

from unittest.mock import patch

import pytest

from support import snapshot


def test_filtro_atrasada_combina_estado_e_conclusao_historica(client, headers, database, obra):
    ids = []
    for nome, entrega, estado, conclusao in [
        ("Casa atrasada", {"modalidade": "data_exata", "data": "2030-10-19"}, "em andamento", None),
        ("Casa no prazo", {"modalidade": "data_exata", "data": "2030-10-20"}, "em andamento", None),
        ("Casa suspensa", {"modalidade": "intervalo_estimado", "inicio": "2030-10-01", "fim": "2030-10-19"}, "suspensa", None),
        ("Casa entregue tarde", {"modalidade": "data_exata", "data": "2030-10-10"}, "concluída", "2030-10-11"),
        ("Casa entregue no prazo", {"modalidade": "data_exata", "data": "2030-10-10"}, "concluída", "2030-10-09"),
    ]:
        documento = {**obra, "nome": nome, "entrega": entrega, "estado": estado}
        if conclusao:
            documento["data_conclusao"] = conclusao
        ids.append(str(database.tbl_obras.insert_one(documento).inserted_id))
    antes = snapshot(database)
    resposta = client.get("/obras?alerta=atrasada", headers=headers)
    assert resposta.status_code == 200
    assert [item["id"] for item in resposta.json["obras"]] == [ids[i] for i in (0, 2, 3)]
    combinada = client.get("/obras?alerta=atrasada&estado=em%20andamento&nome=Casa", headers=headers)
    assert combinada.status_code == 200
    assert [item["id"] for item in combinada.json["obras"]] == [ids[0]]
    assert combinada.json["filtros_aplicados"] == {"alerta": "atrasada", "estado": "em andamento", "nome": "Casa"}
    assert snapshot(database) == antes


@pytest.mark.parametrize("query", ["alerta=critica", "alerta=", "nome=A&nome=B", "estado=planejada&estado=suspensa",
                                   "entregaDe=2030-01-01&entregaDe=invalida", "alerta=atrasada&alerta=critica"])
def test_filtro_invalido_ou_ambiguo_rejeitado_antes_de_consultar(client, headers, query):
    with patch("app.obras.repository.consultar_obras") as consultar:
        resposta = client.get("/obras?" + query, headers=headers)
    assert resposta.status_code == 422
    consultar.assert_not_called()


def test_filtro_alerta_sem_resultados(client, headers):
    resposta = client.get("/obras?alerta=atrasada", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json == {"obras": [], "situacao": "sem_resultados", "filtros_aplicados": {"alerta": "atrasada"}}
