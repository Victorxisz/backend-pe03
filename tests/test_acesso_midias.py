"""CT-31/32/45, CT-03 e CT-109: recuperação protegida das mídias de um avanço."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from flask_jwt_extended import create_access_token
from pymongo.errors import PyMongoError

from support import isolated_app, snapshot

routes = pytest.mark.routes

AVANCO_ID = "507f1f77bcf86cd799439011"
MIDIA_ID = "507f1f77bcf86cd799439012"
LISTA = "/avancos/{}/midias"
DETALHE = "/midias/{}"
CONTEUDO = "/midias/{}/conteudo"

# Conteúdos fictícios, pequenos e reconhecíveis: nada de arquivo real no Git.
ARQUIVOS = {
    "foto": ("fundacao.jpg", "image/jpeg", b"\xff\xd8\xff\xe0 foto ficticia"),
    "video": ("concretagem.mp4", "video/mp4", b"\x00\x00\x00 video ficticio"),
    "documento": ("laudo.pdf", "application/pdf", b"%PDF-1.4 documento ficticio"),
}

# CT-109 só vale quando o provedor aprovado estiver configurado no ambiente.
PROVEDOR_EXTERNO = (os.getenv("MIDIA_PROVEDOR") or "local") != "local"


def assert_erro(resposta, status, codigo):
    assert resposta.status_code == status, resposta.get_data(as_text=True)
    corpo = resposta.get_json()
    assert isinstance(corpo, dict), "Erro deve retornar objeto JSON"
    assert corpo.get("codigo") == codigo, corpo
    assert isinstance(corpo.get("mensagem"), str) and corpo["mensagem"].strip(), corpo


@pytest.fixture
def armazenamento_local(app, tmp_path):
    """Diretório descartável: o teste nunca grava no armazenamento da demonstração."""
    app.config["MIDIA_PROVEDOR"] = "local"
    app.config["MIDIA_DIRETORIO"] = str(tmp_path / "midias")
    return app.config["MIDIA_DIRETORIO"]


@pytest.fixture
def avanco(database, obra):
    obra_id = database.tbl_obras.insert_one({**obra, "_id": ObjectId()}).inserted_id
    marco_id = database.tbl_marcos.insert_one(
        {"_id": ObjectId(), "obra_id": obra_id, "nome": "Fundação"}
    ).inserted_id
    documento = {
        "_id": ObjectId(AVANCO_ID),
        "marco_id": marco_id,
        "data_trabalho": "2030-10-18",
        "descricao": "Concretagem da sapata",
        "estado": "rascunho",
        "autor": "construtora_teste",
    }
    database.tbl_avancos.insert_one(documento)
    return documento


def enviar(app, database, avanco_id, tipo, **mudancas):
    """Grava o arquivo pelo provedor configurado e registra os metadados."""
    from app.avancos import midias

    nome, formato, conteudo = ARQUIVOS[tipo]
    with app.app_context():
        referencia = midias.armazenamento().enviar(conteudo, nome=nome, formato=formato)
    documento = {
        "_id": ObjectId(),
        "avanco_id": avanco_id,
        "tipo": tipo,
        "nome": nome,
        "formato": formato,
        "tamanho": len(conteudo),
        "visibilidade": "privada",
        "referencia_externa": referencia,
        "data_envio": datetime(2030, 10, 18, 13, tzinfo=timezone.utc),
    }
    documento.update(mudancas)
    database.tbl_midias.insert_one(documento)
    return documento


@routes(
    ("GET", LISTA.format(AVANCO_ID)),
    ("GET", DETALHE.format(MIDIA_ID)),
    ("GET", CONTEUDO.format(MIDIA_ID)),
)
def test_ct31_recupera_foto_com_vinculo_e_tipo(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    midia = enviar(app, database, avanco["_id"], "foto")
    antes = snapshot(database)

    # Execução
    lista = client.get(LISTA.format(avanco["_id"]), headers=headers)
    detalhe = client.get(DETALHE.format(midia["_id"]), headers=headers)
    conteudo = client.get(CONTEUDO.format(midia["_id"]), headers=headers)

    # Verificação
    assert lista.status_code == 200
    (item,) = lista.get_json()["midias"]
    assert item["id"] == str(midia["_id"])
    assert item["avanco_id"] == str(avanco["_id"])
    assert item["tipo"] == "foto"
    assert item["formato"] == "image/jpeg"
    assert item["nome"] == "fundacao.jpg"
    assert item["tamanho"] == len(ARQUIVOS["foto"][2])
    assert item["data_envio"] == "2030-10-18T13:00:00+00:00"
    assert item["conteudo"] == CONTEUDO.format(midia["_id"])
    assert detalhe.status_code == 200
    assert detalhe.get_json() == item
    assert conteudo.status_code == 200
    assert conteudo.data == ARQUIVOS["foto"][2]
    assert conteudo.headers["Content-Type"].startswith("image/jpeg")
    assert conteudo.headers["Content-Disposition"].startswith("inline")
    assert conteudo.headers["Cache-Control"] == "private, no-store"
    assert snapshot(database) == antes


@pytest.mark.parametrize("tipo", ["video", "documento"])
@routes(("GET", DETALHE.format(MIDIA_ID)), ("GET", CONTEUDO.format(MIDIA_ID)))
def test_ct32_recupera_video_e_documento_tipados(
    app, client, headers, database, avanco, armazenamento_local, tipo
):
    # Preparação
    nome, formato, bytes_esperados = ARQUIVOS[tipo]
    midia = enviar(app, database, avanco["_id"], tipo)

    # Execução
    detalhe = client.get(DETALHE.format(midia["_id"]), headers=headers)
    conteudo = client.get(CONTEUDO.format(midia["_id"]), headers=headers)

    # Verificação
    assert detalhe.status_code == 200
    assert detalhe.get_json()["tipo"] == tipo
    assert detalhe.get_json()["formato"] == formato
    assert detalhe.get_json()["nome"] == nome
    assert conteudo.status_code == 200
    assert conteudo.data == bytes_esperados
    assert conteudo.headers["Content-Type"].startswith(formato)
    assert nome in conteudo.headers["Content-Disposition"]


@routes(("GET", LISTA.format(AVANCO_ID)))
def test_ct31_lista_traz_os_tres_tipos_do_mesmo_avanco(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    enviados = {tipo: enviar(app, database, avanco["_id"], tipo) for tipo in ARQUIVOS}

    # Execução
    resposta = client.get(LISTA.format(avanco["_id"]), headers=headers)

    # Verificação
    assert resposta.status_code == 200
    midias = {item["tipo"]: item for item in resposta.get_json()["midias"]}
    assert set(midias) == set(ARQUIVOS)
    for tipo, documento in enviados.items():
        assert midias[tipo]["id"] == str(documento["_id"])
        assert midias[tipo]["avanco_id"] == str(avanco["_id"])


@pytest.mark.parametrize(
    "caminho",
    [LISTA, DETALHE, CONTEUDO],
    ids=["lista", "detalhe", "conteudo"],
)
@pytest.mark.parametrize("expirado", [False, True], ids=["sem-token", "expirado"])
def test_ct03_sem_sessao_nao_acessa_midia(
    app, client, account, database, avanco, armazenamento_local, caminho, expirado
):
    # Preparação
    midia = enviar(app, database, avanco["_id"], "foto")
    alvo = avanco["_id"] if caminho == LISTA else midia["_id"]
    antes = snapshot(database)
    headers = {}
    if expirado:
        with app.app_context():
            token = create_access_token(
                identity=str(account["_id"]),
                additional_claims={
                    "tipo": "construtora",
                    "sessao_id": "sessao-teste-expirada",
                },
                expires_delta=timedelta(seconds=-60),
            )
        headers = {"Authorization": "Bearer " + token}

    # Execução
    resposta = client.get(caminho.format(alvo), headers=headers)

    # Verificação
    assert resposta.status_code == 401
    assert ARQUIVOS["foto"][2] not in resposta.data
    corpo = resposta.get_data(as_text=True)
    assert midia["referencia_externa"] not in corpo
    assert midia["nome"] not in corpo
    assert snapshot(database) == antes


@routes(("GET", DETALHE.format(MIDIA_ID)), ("GET", CONTEUDO.format(MIDIA_ID)))
def test_ct45_midia_continua_recuperavel_apos_reiniciar_o_flask(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    midia = enviar(app, database, avanco["_id"], "foto")
    antes = client.get(CONTEUDO.format(midia["_id"]), headers=headers)

    # Execução: nova aplicação Flask, sem nenhum estado do processo anterior.
    with isolated_app(database) as reiniciado:
        reiniciado.config.update(
            MIDIA_PROVEDOR="local", MIDIA_DIRETORIO=armazenamento_local
        )
        with reiniciado.test_client() as novo_cliente:
            metadados = novo_cliente.get(DETALHE.format(midia["_id"]), headers=headers)
            depois = novo_cliente.get(CONTEUDO.format(midia["_id"]), headers=headers)

    # Verificação
    assert antes.status_code == 200
    assert metadados.status_code == 200
    assert metadados.get_json()["id"] == str(midia["_id"])
    assert metadados.get_json()["avanco_id"] == str(avanco["_id"])
    assert depois.status_code == 200
    assert depois.data == antes.data == ARQUIVOS["foto"][2]


@pytest.mark.atlas
@routes(("GET", DETALHE.format(MIDIA_ID)))
def test_ct45_metadados_persistem_em_novo_processo(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    sonda = Path(__file__).resolve().parent / "restart_probe.py"
    midia = enviar(app, database, avanco["_id"], "foto")
    caminho = DETALHE.format(midia["_id"])
    esperado = client.get(caminho, headers=headers)

    # Execução
    ambiente = dict(
        os.environ,
        TEST_DATABASE_NAME=database.name,
        TEST_RESOURCE_PATH=caminho,
        MIDIA_PROVEDOR="local",
        MIDIA_DIRETORIO=armazenamento_local,
    )
    resultado = subprocess.run(
        [sys.executable, str(sonda)],
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Verificação
    assert esperado.status_code == 200
    assert resultado.returncode == 0, "Falha no processo novo; credenciais omitidas"
    reiniciado = json.loads(resultado.stdout)
    assert reiniciado["status"] == 200
    assert reiniciado["body"] == esperado.get_json()


@pytest.mark.skipif(
    not PROVEDOR_EXTERNO,
    reason="CT-109 exige MIDIA_PROVEDOR do provedor aprovado; o padrão local não comprova o serviço externo",
)
@pytest.mark.parametrize("tipo", sorted(ARQUIVOS))
@routes(("GET", CONTEUDO.format(MIDIA_ID)))
def test_ct109_provedor_configurado_recupera_os_tres_tipos(
    app, client, headers, database, avanco, tipo
):
    # Preparação: sem armazenamento_local, usa a configuração real do ambiente.
    from app.avancos import midias

    midia = enviar(app, database, avanco["_id"], tipo)

    # Execução
    resposta = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    with app.app_context():
        acesso = midias.armazenamento().obter_acesso(midia["referencia_externa"])

    # Verificação
    assert resposta.status_code in (200, 302), resposta.get_data(as_text=True)
    if resposta.status_code == 200:
        assert resposta.data == ARQUIVOS[tipo][2]
    else:
        assert resposta.headers["Location"]
    # Os metadados do banco apontam ao objeto correto no provedor.
    assert acesso.conteudo == ARQUIVOS[tipo][2] or acesso.url_temporaria


@routes(("GET", LISTA.format(AVANCO_ID)), ("GET", DETALHE.format(MIDIA_ID)))
def test_vinculo_entre_avanco_e_midia_e_respeitado(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    outro = database.tbl_avancos.insert_one(
        {**avanco, "_id": ObjectId()}
    ).inserted_id
    midia = enviar(app, database, avanco["_id"], "foto")
    orfa = enviar(app, database, ObjectId(), "documento")

    # Execução
    vizinho = client.get(LISTA.format(outro), headers=headers)
    detalhe_orfa = client.get(DETALHE.format(orfa["_id"]), headers=headers)
    conteudo_orfa = client.get(CONTEUDO.format(orfa["_id"]), headers=headers)

    # Verificação
    assert vizinho.status_code == 200
    assert vizinho.get_json() == {"midias": []}
    assert str(midia["_id"]) not in vizinho.get_data(as_text=True)
    # Mídia cujo avanço não existe é referência órfã, não conteúdo acessível.
    assert_erro(detalhe_orfa, 404, "MIDIA_NAO_ENCONTRADA")
    assert_erro(conteudo_orfa, 404, "MIDIA_NAO_ENCONTRADA")


@routes(("GET", LISTA.format(AVANCO_ID)), ("GET", DETALHE.format(MIDIA_ID)))
def test_registros_inexistentes_e_ids_invalidos(client, headers, database, avanco):
    # Preparação
    antes = snapshot(database)

    # Execução
    sem_avanco = client.get(LISTA.format(ObjectId()), headers=headers)
    avanco_invalido = client.get(LISTA.format("nao-e-um-id"), headers=headers)
    sem_midia = client.get(DETALHE.format(ObjectId()), headers=headers)
    midia_invalida = client.get(DETALHE.format("nao-e-um-id"), headers=headers)
    sem_conteudo = client.get(CONTEUDO.format(ObjectId()), headers=headers)
    vazio = client.get(LISTA.format(avanco["_id"]), headers=headers)

    # Verificação
    assert_erro(sem_avanco, 404, "AVANCO_NAO_ENCONTRADO")
    assert_erro(avanco_invalido, 400, "ID_INVALIDO")
    assert_erro(sem_midia, 404, "MIDIA_NAO_ENCONTRADA")
    assert_erro(midia_invalida, 400, "ID_INVALIDO")
    assert_erro(sem_conteudo, 404, "MIDIA_NAO_ENCONTRADA")
    # Avanço existente sem mídia é lista vazia, não erro.
    assert vazio.status_code == 200
    assert vazio.get_json() == {"midias": []}
    assert snapshot(database) == antes


@routes(("GET", LISTA.format(AVANCO_ID)), ("GET", DETALHE.format(MIDIA_ID)))
def test_metadados_nao_expoem_referencia_nem_endereco_do_provedor(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    midia = enviar(app, database, avanco["_id"], "foto")

    # Execução
    respostas = [
        client.get(LISTA.format(avanco["_id"]), headers=headers),
        client.get(DETALHE.format(midia["_id"]), headers=headers),
    ]

    # Verificação
    for resposta in respostas:
        corpo = resposta.get_data(as_text=True)
        assert resposta.status_code == 200
        assert midia["referencia_externa"] not in corpo
        assert "referencia_externa" not in corpo
        assert "provedor" not in corpo
        assert armazenamento_local not in corpo
        # Nenhum endereço absoluto: o arquivo só é alcançado por rota do Flask.
        assert "://" not in corpo


@pytest.mark.parametrize(
    "falha,codigo",
    [
        ("ConteudoAusenteNoProvedor", "CONTEUDO_AUSENTE_NO_PROVEDOR"),
        ("ProvedorIndisponivel", "PROVEDOR_INDISPONIVEL"),
    ],
)
@routes(("GET", CONTEUDO.format(MIDIA_ID)))
def test_falha_do_provedor_nao_vira_midia_inexistente(
    app, client, headers, database, avanco, armazenamento_local, falha, codigo
):
    # Preparação
    from app.avancos import midias

    midia = enviar(app, database, avanco["_id"], "foto")

    # Execução
    with patch("app.avancos.midias.armazenamento") as fabrica:
        fabrica.return_value.obter_acesso.side_effect = getattr(midias, falha)(
            "detalhe interno do provedor"
        )
        resposta = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    inexistente = client.get(CONTEUDO.format(ObjectId()), headers=headers)

    # Verificação
    assert_erro(resposta, 502, codigo)
    assert "detalhe interno" not in resposta.get_data(as_text=True)
    # Registro ausente continua distinguível da falha de acesso ao provedor.
    assert_erro(inexistente, 404, "MIDIA_NAO_ENCONTRADA")


@routes(("GET", CONTEUDO.format(MIDIA_ID)))
def test_arquivo_ausente_no_provedor_difere_de_midia_inexistente(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação: metadados no banco, arquivo removido do armazenamento.
    midia = enviar(app, database, avanco["_id"], "foto")
    (Path(armazenamento_local) / midia["referencia_externa"]).unlink()

    # Execução
    resposta = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    metadados = client.get(DETALHE.format(midia["_id"]), headers=headers)

    # Verificação
    assert_erro(resposta, 502, "CONTEUDO_AUSENTE_NO_PROVEDOR")
    assert metadados.status_code == 200


@routes(("GET", CONTEUDO.format(MIDIA_ID)))
def test_endereco_do_provedor_e_repassado_somente_com_validade_curta(
    app, client, headers, database, avanco, armazenamento_local
):
    # Preparação
    from app.avancos import midias

    midia = enviar(app, database, avanco["_id"], "foto")
    endereco = "https://provedor.example/objeto-ficticio?assinatura=ficticia"

    # Execução
    with patch("app.avancos.midias.armazenamento") as fabrica:
        fabrica.return_value.obter_acesso.return_value = midias.Acesso(
            url_temporaria=endereco,
            expira_em=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        temporario = client.get(CONTEUDO.format(midia["_id"]), headers=headers)
    with patch("app.avancos.midias.armazenamento") as fabrica:
        fabrica.return_value.obter_acesso.return_value = midias.Acesso(
            url_temporaria=endereco
        )
        permanente = client.get(CONTEUDO.format(midia["_id"]), headers=headers)

    # Verificação
    assert temporario.status_code == 302
    assert temporario.headers["Location"] == endereco
    assert temporario.headers["Cache-Control"] == "private, no-store"
    # Endereço sem validade seria um atalho permanente em volta da sessão.
    assert_erro(permanente, 502, "ACESSO_TEMPORARIO_INVALIDO")
    assert "provedor.example" not in permanente.get_data(as_text=True)


@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("consultar_midias", LISTA),
        ("buscar_midia_por_id", DETALHE),
    ],
)
@routes(("GET", LISTA.format(AVANCO_ID)), ("GET", DETALHE.format(MIDIA_ID)))
def test_falha_do_banco_nao_expoe_detalhes(
    client, headers, database, avanco, metodo, caminho
):
    # Execução
    with patch(
        "app.avancos.repository." + metodo,
        side_effect=PyMongoError("detalhe privado da conexão"),
    ):
        resposta = client.get(caminho.format(avanco["_id"]), headers=headers)

    # Verificação
    assert_erro(resposta, 500, "FALHA_NO_BANCO")
    assert "detalhe privado" not in resposta.get_data(as_text=True)
