"""UC-20 / CT-96 a CT-99: manutenção do cadastro, dos vínculos e exclusão.

CT-100 fica em ``tests/test_exclusao_cascata.py``, junto da cascata de UC-17;
CT-101 exige conexão real e está em ``test_persistencia_atlas.py``. Aqui também
fica a política P-10: remover o cadastro não deixa a ocorrência apontando para
quem saiu nem apaga a autoria das decisões já registradas.
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_avancos import transacao_local  # noqa: F401 - fixture de rollback local

INSTANTE = datetime(2030, 10, 20, 12, tzinfo=timezone.utc)


@pytest.fixture
def ocorrencia(database, account, pessoa, obra_existente):
    """Ocorrência atribuída à pessoa, com autoria e aceitação da construtora."""
    documento = {
        "_id": ObjectId(), "obra_id": obra_existente["_id"], "marco_id": None,
        "titulo": "Infiltração", "descricao": "Água na parede", "estado": "sem solução",
        "responsavel_id": pessoa["_id"], "autor": str(account["_id"]),
        "data_registro": INSTANTE, "midias": [],
        "aceitacoes": [{"justificativa": "Decisão formal", "autor": str(account["_id"]),
                        "data": INSTANTE}],
    }
    database.tbl_ocorrencias.insert_one(documento)
    # Relê o que foi gravado: o armazenamento devolve os instantes sem fuso.
    return database.tbl_ocorrencias.find_one({"_id": documento["_id"]})


def cadastro(database, pessoa):
    return database.tbl_trabalhadores.find_one({"_id": pessoa["_id"]})


# --- CT-96: corrigir dados sem recriar a pessoa ---------------------------


def test_ct96_corrige_nome_cargo_e_telefone_preservando_o_resto(
    client, headers, database, pessoa
):
    # Preparação
    obras_antes = list(database.tbl_obras.find())

    # Execução
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"nome": "  Ana Silva  ", "cargo": "Mestre DE Obras",
              "telefone": "(16) 99173-6767"},
    )

    # Verificação: email, obras, ativo e data de cadastro ficam como estavam.
    assert resposta.status_code == 200
    assert cadastro(database, pessoa) == {
        **pessoa, "nome": "Ana Silva", "cargo": "mestre de obras",
        "telefone": "16991736767",
    }
    assert list(database.tbl_obras.find()) == obras_antes


@pytest.mark.parametrize("campo,enviado,gravado", [
    ("nome", " Carlos Lima ", "Carlos Lima"),
    ("email", " novo@example.com ", "novo@example.com"),
    ("telefone", "11 98888 7777", "11988887777"),
    ("cargo", " ELETRICISTA ", "eletricista"),
])
def test_ct96_cada_campo_isolado_nao_toca_nos_demais(
    client, headers, database, pessoa, campo, enviado, gravado
):
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={campo: enviado}
    )
    assert resposta.status_code == 200
    assert cadastro(database, pessoa) == {**pessoa, campo: gravado}


# --- CT-97: trocar e retirar vínculos de obra -----------------------------


def test_ct97_troca_obra_a_por_b_e_depois_aceita_lista_vazia(
    client, headers, database, pessoa, obra_existente, obra
):
    # Preparação
    obra_b = database.tbl_obras.insert_one(dict(obra)).inserted_id
    caminho = f"/trabalhadores/{pessoa['_id']}/"

    # Execução: substituição explícita e, em seguida, retirada de todos.
    troca = client.patch(caminho, headers=headers, json={"obras": [str(obra_b)]})
    em_a = client.get(f"/trabalhadores/obra/{obra_existente['_id']}/", headers=headers)
    em_b = client.get(f"/trabalhadores/obra/{obra_b}/", headers=headers)
    vazia = client.patch(caminho, headers=headers, json={"obras": []})
    detalhe = client.get(caminho, headers=headers)

    # Verificação
    assert troca.status_code == vazia.status_code == 200
    assert em_a.get_json() == []
    assert [item["id"] for item in em_b.get_json()] == [str(pessoa["_id"])]
    assert cadastro(database, pessoa) == {**pessoa, "obras": []}
    # Sem obra o cadastro continua existindo e consultável.
    assert detalhe.status_code == 200
    assert detalhe.get_json()["obras"] == []
    assert database.tbl_obras.count_documents({}) == 2


def test_ct97_lista_repetida_nao_duplica_vinculo(
    client, headers, database, pessoa, obra_existente
):
    identificador = str(obra_existente["_id"])
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"obras": [identificador, identificador.upper(), identificador]},
    )
    assert resposta.status_code == 200
    assert cadastro(database, pessoa)["obras"] == [identificador]


def test_ct97_uma_obra_inexistente_rejeita_a_lista_inteira(
    client, headers, database, pessoa, obra
):
    # Preparação
    obra_b = database.tbl_obras.insert_one(dict(obra)).inserted_id
    ausente = str(ObjectId())
    antes = snapshot(database)

    # Execução
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers,
        json={"cargo": "pintor", "obras": [str(obra_b), ausente]},
    )

    # Verificação: nem o vínculo válido nem o cargo são gravados.
    assert resposta.status_code == 422
    assert resposta.get_json()["obras"] == [ausente]
    assert snapshot(database) == antes


def test_ct97_obra_de_outra_construtora_nao_vira_vinculo(
    client, headers, database, pessoa, obra
):
    alheia = database.tbl_obras.insert_one(
        {**obra, "autor": str(ObjectId())}).inserted_id
    antes = snapshot(database)
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": [str(alheia)]}
    )
    assert resposta.status_code == 422
    assert resposta.get_json()["obras"] == [str(alheia)]
    assert snapshot(database) == antes


# --- CT-98: entradas inválidas não alteram o registro ---------------------


@pytest.mark.parametrize("payload", [
    {}, {"cargo": "pedreiro", "salario": 1500}, {"construtora_id": str(ObjectId())},
    {"id": str(ObjectId())}, {"data_cadastro": "2030-01-01"},
    {"obras": [str(ObjectId())[:-1]]},
])
def test_ct98_json_vazio_ou_campo_desconhecido(
    client, headers, database, pessoa, payload
):
    antes = snapshot(database)
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers, json=payload
    )
    assert resposta.status_code == 422
    assert "erro" in resposta.get_json()
    assert snapshot(database) == antes


@pytest.mark.parametrize("metodo", ["PATCH", "DELETE"])
@pytest.mark.parametrize("identificador,status", [
    ("123", 400), ("507f1f77bcf86cd79943901", 400), ("nao-e-id", 400),
    (str(ObjectId()), 404),
])
def test_ct98_id_invalido_ou_inexistente_preserva_o_cadastro(
    client, headers, database, pessoa, metodo, identificador, status
):
    antes = snapshot(database)
    resposta = client.open(
        f"/trabalhadores/{identificador}/", method=metodo,
        json={"cargo": "pintor"}, headers=headers,
    )
    assert resposta.status_code == status
    assert snapshot(database) == antes


# --- CT-99: a interface identifica a pessoa e confirma antes do DELETE ----


def test_ct99_consulta_para_o_aviso_nao_altera_nada_e_confirmar_remove(
    client, headers, database, pessoa, obra_existente
):
    """Cancelar é não enviar DELETE: a consulta que monta o aviso não grava."""
    # Preparação
    antes = snapshot(database)
    caminho = f"/trabalhadores/{pessoa['_id']}/"

    # Execução: a tela abre o detalhe para nomear quem será excluído.
    aviso = client.get(caminho, headers=headers)

    # Verificação do cancelamento: nenhuma escrita até aqui.
    assert aviso.status_code == 200
    assert aviso.get_json()["nome"] == pessoa["nome"]
    assert aviso.get_json()["cargo"] == pessoa["cargo"]
    assert aviso.get_json()["obras"] == [str(obra_existente["_id"])]
    assert snapshot(database) == antes

    # Execução da confirmação.
    exclusao = client.delete(caminho, headers=headers)

    # Verificação: cadastro some, obra permanece.
    assert exclusao.status_code == 200
    assert exclusao.get_json()["id"] == str(pessoa["_id"])
    assert cadastro(database, pessoa) is None
    assert client.get(caminho, headers=headers).status_code == 404
    assert database.tbl_obras.find_one({"_id": obra_existente["_id"]}) == obra_existente


def test_ct99_exclusao_repetida_responde_404_sem_novo_efeito(
    client, headers, database, pessoa
):
    caminho = f"/trabalhadores/{pessoa['_id']}/"
    assert client.delete(caminho, headers=headers).status_code == 200
    depois = snapshot(database)
    assert client.delete(caminho, headers=headers).status_code == 404
    assert snapshot(database) == depois


def test_ct99_exclusao_sem_sessao_nao_remove_o_cadastro(client, database, pessoa):
    antes = snapshot(database)
    assert client.delete(f"/trabalhadores/{pessoa['_id']}/").status_code == 401
    assert snapshot(database) == antes


# --- P-10: responsável de ocorrência quando o cadastro é removido ---------


def test_exclusao_desatribui_responsavel_e_preserva_a_ocorrencia(
    client, headers, database, pessoa, ocorrencia, transacao_local
):
    # Execução
    resposta = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)

    # Verificação: sem referência pendente e sem perder quem respondia.
    assert resposta.status_code == 200
    assert resposta.get_json()["ocorrencias_sem_responsavel"] == 1
    assert cadastro(database, pessoa) is None
    salva = database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]})
    assert salva["responsavel_id"] is None
    anterior = salva["responsavel_anterior"]
    assert anterior["id"] == str(pessoa["_id"])
    assert anterior["nome"] == pessoa["nome"] and anterior["cargo"] == pessoa["cargo"]
    assert isinstance(anterior["removido_em"], datetime)
    # A autoria das decisões e o restante da ocorrência ficam intactos.
    assert {campo: valor for campo, valor in salva.items()
            if campo not in ("responsavel_id", "responsavel_anterior")} == {
        campo: valor for campo, valor in ocorrencia.items() if campo != "responsavel_id"}


def test_ocorrencia_sem_responsavel_continua_legivel_pela_api(
    client, headers, database, pessoa, ocorrencia, transacao_local
):
    exclusao = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)
    assert exclusao.status_code == 200
    leitura = client.get(f"/ocorrencias/{ocorrencia['_id']}", headers=headers)
    assert leitura.status_code == 200
    corpo = leitura.get_json()
    assert corpo["responsavel_id"] is None
    assert corpo["responsavel_anterior"]["nome"] == pessoa["nome"]
    assert corpo["autor"] == ocorrencia["autor"]
    assert [item["autor"] for item in corpo["aceitacoes"]] == [ocorrencia["autor"]]


@pytest.mark.parametrize("colecao,operacao", [
    ("ocorrencias", "update_many"), ("trabalhadores", "delete_one"),
])
def test_falha_no_banco_nao_remove_nem_desatribui(
    client, headers, database, pessoa, ocorrencia, modulo_trabalhadores,
    monkeypatch, transacao_local, colecao, operacao
):
    # Preparação
    antes = snapshot(database)

    def falhar(*args, **kwargs):
        raise PyMongoError("detalhe interno simulado")

    # Execução
    with monkeypatch.context() as contexto:
        alvo = getattr(modulo_trabalhadores.servico.repositorio, colecao)
        contexto.setattr(alvo, operacao, falhar)
        resposta = client.delete(f"/trabalhadores/{pessoa['_id']}/", headers=headers)

    # Verificação: sem sucesso falso e sem exclusão parcial.
    assert resposta.status_code == 503
    assert "detalhe interno" not in resposta.get_data(as_text=True)
    assert snapshot(database) == antes


def test_retirar_o_vinculo_nao_desfaz_a_atribuicao(
    client, headers, database, pessoa, ocorrencia
):
    """Ausência temporária da obra não apaga quem responde pela ocorrência."""
    resposta = client.patch(
        f"/trabalhadores/{pessoa['_id']}/", headers=headers, json={"obras": []}
    )
    assert resposta.status_code == 200
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]}) == ocorrencia
    assert cadastro(database, pessoa) == {**pessoa, "obras": []}


def test_exclusao_de_outro_trabalhador_nao_toca_na_atribuicao(
    client, headers, database, pessoa, ocorrencia, trabalhador
):
    outro = database.tbl_trabalhadores.insert_one(
        {**trabalhador, "email": "outro@example.com", "obras": [], "ativo": True}).inserted_id
    resposta = client.delete(f"/trabalhadores/{outro}/", headers=headers)
    assert resposta.status_code == 200
    assert resposta.get_json()["ocorrencias_sem_responsavel"] == 0
    assert database.tbl_ocorrencias.find_one({"_id": ocorrencia["_id"]}) == ocorrencia
    assert cadastro(database, pessoa) == pessoa
