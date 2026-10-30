"""UC-09: serviço, persistência e limpeza; a rota PATCH ainda não existe.

Sem --atlas, rollback é simulado: estes testes não comprovam isolamento nem
concorrência real do MongoDB. O provedor de arquivos é sempre simulado.
"""

from contextlib import nullcontext
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from support import snapshot
from support_midias import arquivo, config, conteudos


@pytest.fixture
def camadas(app):
    # Imports após isolated_app: usa os módulos ligados ao banco desta execução.
    from app.avancos import repository, service, validacoes
    from app.avancos.midias import ErroMidia, ServicoMidias
    from app.avancos.revisoes import ConflitoRascunho
    from app.integracoes.armazenamento import ErroArmazenamento, ErroLimpeza
    from app.mudanças.ocorrencias.historico.service import consultar_previa

    return SimpleNamespace(
        repo=repository, service=service, validacoes=validacoes,
        ErroMidia=ErroMidia, ServicoMidias=ServicoMidias,
        ConflitoRascunho=ConflitoRascunho,
        ErroArmazenamento=ErroArmazenamento, ErroLimpeza=ErroLimpeza,
        consultar_previa=consultar_previa,
    )


@pytest.fixture
def transacao_local(camadas, database, monkeypatch, request):
    if request.config.getoption("--atlas"):
        return

    import db
    from mongomock.collection import Collection

    # Guarda as operações originais para restaurar o banco mesmo quando um
    # teste injeta uma falha de escrita na coleção.
    apagar = Collection.delete_many
    inserir = Collection.insert_many

    class Sessao:
        def with_transaction(self, gravar):
            antes = snapshot(database)
            try:
                return gravar(self)
            except Exception:
                for nome in database.list_collection_names():
                    apagar(database[nome], {})
                for nome, documentos in antes.items():
                    inserir(database[nome], deepcopy(documentos))
                raise

    monkeypatch.setattr(
        db.cliente_mongo, "start_session", lambda: nullcontext(Sessao())
    )

    def sem_sessao(original):
        @wraps(original)
        def executar(*args, **kwargs):
            kwargs.pop("session", None)
            return original(*args, **kwargs)
        return executar

    for nome in (
        "find", "find_one", "update_one", "insert_one", "insert_many",
        "delete_many", "delete_one", "find_one_and_update",
    ):
        monkeypatch.setattr(Collection, nome, sem_sessao(getattr(Collection, nome)))


@pytest.fixture
def cenario(transacao_local, camadas, database, config, conteudos):
    obra, marco, avanco = ObjectId(), ObjectId(), ObjectId()
    database.tbl_obras.insert_one({"_id": obra, "nome": "Obra de teste"})
    database.tbl_marcos.insert_one({"_id": marco, "obra_id": obra, "nome": "Fundação"})
    database.tbl_avancos.insert_one({
        "_id": avanco, "marco_id": marco, "autor": str(ObjectId()),
        "data": "2030-10-19", "descricao": "Descrição anterior",
        "estado": "rascunho", "revisao": 3,
    })

    arquivos_remotos = {}

    def metadados(conteudo, nome="foto.png", tipo="foto", mime="image/png"):
        referencia = {
            "provedor": "cloudinary", "public_id": config.pasta + "/" + uuid4().hex,
            "resource_type": {"foto": "image", "video": "video", "documento": "raw"}[tipo],
            "delivery_type": "authenticated", "formato": nome.rsplit(".", 1)[-1],
        }
        arquivos_remotos[referencia["public_id"]] = conteudo
        return {
            "tipo": tipo, "nome": nome, "mime": mime, "tamanho": len(conteudo),
            "referencia_externa": referencia,
        }

    fotos = []
    for nome in ("a.png", "b.png"):
        midia = {**metadados(conteudos["png"], nome), "_id": ObjectId(), "avanco_id": avanco}
        database.tbl_midias.insert_one(midia)
        fotos.append(midia)

    def enviar(validado):
        return metadados(validado.conteudo, validado.nome, validado.tipo, validado.mime)

    def recuperar(referencia, tamanho):
        conteudo = arquivos_remotos.get(referencia["public_id"])
        if conteudo is None:
            raise camadas.ErroArmazenamento("Arquivo ausente", 404)
        if len(conteudo) != tamanho:
            raise camadas.ErroArmazenamento("Tamanho inconsistente", 502)
        return conteudo

    storage = Mock()
    storage.config = config
    storage.enviar.side_effect = enviar
    storage.obter_conteudo.side_effect = recuperar
    storage.remover.side_effect = lambda ref: arquivos_remotos.pop(ref["public_id"], None)
    midias = camadas.ServicoMidias(storage)

    def editar(dados, arquivos=()):
        return camadas.service.editar_rascunho(
            str(avanco), dados, arquivos, servico_midias=midias
        )

    return SimpleNamespace(
        obra=obra, marco=marco, avanco=avanco, fotos=fotos, storage=storage,
        midias=midias, remotos=arquivos_remotos, editar=editar,
    )


@pytest.mark.parametrize("dados", [
    None, [], "texto", {}, {"data": None}, {"data": "2030-02-30"},
    {"data": "20301019"}, {"descricao": "  "}, {"descricao": 1},
    {"midias_manter": None}, {"midias_manter": "id"},
    {"midias_manter": [None]}, {"midias_manter": ["invalido"]},
])
def test_entrada_invalida_nao_altera_banco_nem_envia_arquivos(camadas, cenario, database, dados):
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar(dados)
    assert erro.value.status == 422
    assert snapshot(database) == antes
    cenario.storage.enviar.assert_not_called()
    cenario.storage.remover.assert_not_called()


@pytest.mark.parametrize("campo", ["autor", "marco_id", "obra_id", "estado", "publicacao", "revisao", "_id"])
def test_campos_protegidos_rejeitados(camadas, cenario, database, campo):
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Correção", campo: "tentativa"})
    assert erro.value.status == 422
    assert campo in erro.value.campos
    assert snapshot(database) == antes


@pytest.mark.parametrize("identificador", [None, 1, {}, "", "invalido"])
def test_id_invalido_retorna_400(camadas, identificador):
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        camadas.service.editar_rascunho(identificador, {"descricao": "Correção"})
    assert erro.value.status == 400


def test_avanco_inexistente_retorna_404(camadas):
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        camadas.service.editar_rascunho(str(ObjectId()), {"descricao": "Correção"})
    assert erro.value.status == 404


@pytest.mark.parametrize("dados", [
    {"descricao": "  Descrição revisada  "}, {"data": "2030-10-20"},
    {"data": "2030-10-20", "descricao": "Descrição revisada"},
])
def test_ct37_edicao_parcial_preserva_campos_e_midia(cenario, database, dados):
    anterior = database.tbl_avancos.find_one({"_id": cenario.avanco})
    resposta = cenario.editar(dados)
    salvo = database.tbl_avancos.find_one({"_id": cenario.avanco})
    for campo in ("autor", "marco_id", "estado"):
        assert salvo[campo] == anterior[campo]
    for campo in ("data", "descricao"):
        assert salvo[campo] == dados.get(campo, anterior[campo]).strip()
    assert salvo["revisao"] == 4 and "publicacao" not in salvo
    assert {m["_id"] for m in database.tbl_midias.find()} == {m["_id"] for m in cenario.fotos}
    assert resposta == {"id": str(cenario.avanco), **{k: salvo[k] for k in ("data", "descricao", "estado", "revisao")}}
    assert not {"autor", "referencia_externa", "public_id", "midias_removidas"} & resposta.keys()
    cenario.storage.enviar.assert_not_called()
    cenario.storage.remover.assert_not_called()


def test_rascunho_legado_sem_revisao_passa_a_revisao_um(cenario, database):
    database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$unset": {"revisao": ""}})
    assert cenario.editar({"descricao": "Correção"})["revisao"] == 1


@pytest.mark.parametrize("revisao", [-1, True, "3", None])
def test_revisao_invalida_preserva_rascunho(camadas, cenario, database, revisao):
    database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$set": {"revisao": revisao}})
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Correção"})
    assert erro.value.status == 409
    assert snapshot(database) == antes


def test_ct38_remover_ultima_midia_sem_substituir_rejeitado(camadas, cenario, database):
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"midias_manter": []})
    assert erro.value.status == 422
    assert snapshot(database) == antes
    cenario.storage.enviar.assert_not_called()
    cenario.storage.remover.assert_not_called()


@pytest.mark.parametrize("duplicada", [False, True])
def test_midia_alheia_ou_duplicada_rejeitada(camadas, cenario, database, duplicada):
    midia = cenario.fotos[0]["_id"] if duplicada else ObjectId()
    if not duplicada:
        database.tbl_midias.insert_one({"_id": midia, "avanco_id": ObjectId()})
    ids = [str(midia)] * (2 if duplicada else 1)
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"midias_manter": ids})
    assert erro.value.status == 422
    assert snapshot(database) == antes


@pytest.mark.parametrize("estado,publicacao", [
    ("publicado", False), ("publicado", True), ("rascunho", True), ("arquivado", False),
])
def test_ct40_publicado_ou_inconsistente_nao_editado(camadas, cenario, database, conteudos, estado, publicacao):
    mudanca = {"estado": estado}
    if publicacao:
        mudanca["publicacao"] = {"descricao": "Conteúdo publicado"}
    database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$set": mudanca})
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Tentativa"}, [arquivo(conteudos["png"])])
    assert erro.value.status == 409
    assert snapshot(database) == antes
    cenario.storage.enviar.assert_not_called()


@pytest.mark.parametrize("substituir", [False, True])
def test_ct37_adicionar_ou_substituir_todas_as_midias(cenario, database, conteudos, substituir):
    antigas = {m["referencia_externa"]["public_id"] for m in cenario.fotos}
    dados = {"midias_manter": []} if substituir else {}
    resposta = cenario.editar(dados, [arquivo(conteudos["pdf"], "relatorio.pdf")])
    atuais = list(database.tbl_midias.find({"avanco_id": cenario.avanco}))
    assert len(atuais) == (1 if substituir else 3)
    assert all(isinstance(m["_id"], ObjectId) for m in atuais)
    assert all(m["avanco_id"] == cenario.avanco for m in atuais)
    assert any(m["tipo"] == "documento" for m in atuais)
    assert resposta["estado"] == "rascunho"
    assert database.tbl_limpezas_midias.count_documents({}) == 0
    if substituir:
        assert antigas.isdisjoint(cenario.remotos)
    else:
        assert antigas.issubset(cenario.remotos)


def test_limpeza_so_depois_do_commit(cenario, database):
    a, b = cenario.fotos
    remover = cenario.storage.remover.side_effect

    def verificar_e_remover(referencia):
        assert database.tbl_avancos.find_one({"_id": cenario.avanco})["revisao"] == 4
        assert database.tbl_midias.find_one({"_id": b["_id"]}) is None
        assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]})["midia"] == b
        return remover(referencia)

    cenario.storage.remover.side_effect = verificar_e_remover
    cenario.editar({"midias_manter": [str(a["_id"])]})
    cenario.storage.remover.assert_called_once_with(b["referencia_externa"])
    assert database.tbl_limpezas_midias.count_documents({}) == 0


def test_ct42_edicao_permanece_fora_da_previa(camadas, cenario):
    assert camadas.consultar_previa(str(cenario.obra)) == []
    cenario.editar({"descricao": "Revisão ainda privada"})
    assert camadas.consultar_previa(str(cenario.obra)) == []


@pytest.mark.parametrize("status,esperado", [(404, 422), (422, 422), (502, 503), (503, 503)])
def test_midia_mantida_irrecuperavel_impede_upload(camadas, cenario, database, conteudos, status, esperado):
    cenario.storage.obter_conteudo.side_effect = camadas.ErroArmazenamento("Falha", status)
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Correção"}, [arquivo(conteudos["png"])])
    assert erro.value.status == esperado
    assert snapshot(database) == antes
    cenario.storage.enviar.assert_not_called()


def test_metadados_mantidos_invalidos_rejeitados(camadas, cenario, database):
    database.tbl_midias.update_one({"_id": cenario.fotos[0]["_id"]}, {"$set": {"mime": "text/html"}})
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Correção"})
    assert erro.value.status == 422
    assert snapshot(database) == antes
    cenario.storage.obter_conteudo.assert_not_called()


def test_substituicao_por_arquivo_invalido_preserva_anteriores(camadas, cenario, database):
    antes, remotos = snapshot(database), dict(cenario.remotos)
    with pytest.raises(camadas.ErroMidia):
        cenario.editar({"midias_manter": []}, [arquivo(b"foto falsa", "foto.png")])
    assert snapshot(database) == antes
    assert cenario.remotos == remotos
    cenario.storage.enviar.assert_not_called()


@pytest.mark.parametrize("ponto", ["tarefa", "exclusao", "insercao"])
def test_falha_transacao_desfaz_edicao_e_limpa_uploads(camadas, cenario, database, conteudos, monkeypatch, ponto):
    antes, remotos = snapshot(database), dict(cenario.remotos)
    colecao, metodo = {
        "tarefa": (database.tbl_limpezas_midias, "update_one"),
        "exclusao": (database.tbl_midias, "delete_many"),
        "insercao": (database.tbl_midias, "insert_many"),
    }[ponto]
    monkeypatch.setattr(colecao, metodo, Mock(side_effect=PyMongoError("Falha de escrita")))
    with pytest.raises(PyMongoError):
        cenario.editar({"midias_manter": [], "descricao": "Não deve persistir"}, [arquivo(conteudos["png"])])
    assert snapshot(database) == antes
    assert cenario.remotos == remotos
    cenario.storage.remover.assert_called_once()


@pytest.mark.parametrize("mudanca", ["revisao", "publicacao", "midia", "exclusao"])
def test_mudanca_entre_leitura_e_gravacao_rejeita_edicao(camadas, cenario, database, conteudos, monkeypatch, mudanca):
    original = camadas.repo.salvar_edicao
    esperado = {}

    def mudar_e_salvar(**kwargs):
        if mudanca == "revisao":
            database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$inc": {"revisao": 1}})
        elif mudanca == "publicacao":
            database.tbl_avancos.update_one({"_id": cenario.avanco}, {"$set": {"estado": "publicado", "publicacao": {}}})
        elif mudanca == "exclusao":
            database.tbl_avancos.delete_one({"_id": cenario.avanco})
        else:
            database.tbl_midias.update_one({"_id": cenario.fotos[0]["_id"]}, {"$set": {"nome": "Alterada por outra operação"}})
        esperado.update(snapshot(database))
        return original(**kwargs)

    monkeypatch.setattr(camadas.repo, "salvar_edicao", mudar_e_salvar)
    remotos = dict(cenario.remotos)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"descricao": "Não deve sobrescrever"}, [arquivo(conteudos["png"])])
    assert erro.value.status == 409
    assert snapshot(database) == esperado
    assert cenario.remotos == remotos


@pytest.mark.parametrize("formato", [str, lambda valor: valor], ids=["texto", "ObjectId"])
def test_midia_referenciada_em_publicacao_nao_perde_metadados(camadas, cenario, database, formato):
    a, b = cenario.fotos
    database.tbl_avancos.insert_one({"estado": "publicado", "publicacao": {"midias": [{"id": formato(b["_id"])}]}})
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"midias_manter": [str(a["_id"])]})
    assert erro.value.status == 409
    assert snapshot(database) == antes
    cenario.storage.remover.assert_not_called()


def test_arquivo_compartilhado_nao_e_removido(cenario, database):
    a, b = cenario.fotos
    copia = {**deepcopy(b), "_id": ObjectId(), "avanco_id": ObjectId()}
    copia["referencia_externa"].pop("formato")  # Formato não muda a identidade.
    database.tbl_midias.insert_one(copia)
    cenario.editar({"midias_manter": [str(a["_id"])]})
    assert database.tbl_midias.find_one({"_id": b["_id"]}) is None
    assert database.tbl_midias.find_one({"_id": copia["_id"]}) is not None
    assert b["referencia_externa"]["public_id"] in cenario.remotos
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]}) is not None
    cenario.storage.remover.assert_not_called()


@pytest.mark.parametrize("falha", ["consulta", "provedor", "conclusao"])
def test_falha_limpeza_preserva_edicao_e_tarefa(camadas, cenario, database, monkeypatch, falha):
    a, b = cenario.fotos
    if falha == "consulta":
        monkeypatch.setattr(camadas.repo, "referencia_em_uso", Mock(side_effect=PyMongoError("Falha")))
    elif falha == "provedor":
        cenario.storage.remover.side_effect = camadas.ErroArmazenamento("Indisponível")
    else:
        monkeypatch.setattr(camadas.repo, "concluir_limpeza", Mock(side_effect=PyMongoError("Falha")))
    resposta = cenario.editar({"midias_manter": [str(a["_id"])], "descricao": "Persistida"})
    assert resposta["descricao"] == "Persistida" and resposta["revisao"] == 4
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]})["midia"] == b
    assert (b["referencia_externa"]["public_id"] in cenario.remotos) == (falha != "conclusao")


def test_retentativa_conclui_tarefa_apos_falha_do_provedor(camadas, cenario, database):
    a, b = cenario.fotos
    remover = cenario.storage.remover.side_effect
    cenario.storage.remover.side_effect = camadas.ErroArmazenamento("Indisponível")
    cenario.editar({"midias_manter": [str(a["_id"])]})
    cenario.storage.remover.side_effect = remover
    tarefa = database.tbl_limpezas_midias.find_one({"_id": b["_id"]})
    camadas.service._limpar_apos_edicao(cenario.midias, [tarefa["midia"]])
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]}) is None
    assert b["referencia_externa"]["public_id"] not in cenario.remotos


@pytest.mark.parametrize("referencia", [None, {}, {"public_id": ""}])
def test_limpeza_referencia_invalida_preserva_arquivo_e_tarefa(camadas, cenario, database, referencia):
    a, b = cenario.fotos
    database.tbl_midias.update_one({"_id": b["_id"]}, {"$set": {"referencia_externa": referencia}})
    cenario.editar({"midias_manter": [str(a["_id"])]})
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]}) is not None
    assert camadas.repo.referencia_em_uso(referencia) is True
    cenario.storage.remover.assert_not_called()


def test_commit_desconhecido_nao_apaga_upload_potencialmente_em_uso(camadas, cenario, conteudos, monkeypatch):
    erro = PyMongoError("Confirmação perdida", error_labels=["UnknownTransactionCommitResult"])
    monkeypatch.setattr(camadas.repo, "salvar_edicao", Mock(side_effect=erro))
    quantidade = len(cenario.remotos)
    with pytest.raises(PyMongoError) as recebido:
        cenario.editar({"descricao": "Correção"}, [arquivo(conteudos["png"])])
    assert recebido.value is erro
    assert len(cenario.remotos) == quantidade + 1
    cenario.storage.remover.assert_not_called()


def test_falha_compensacao_informa_uploads_pendentes(camadas, cenario, database, conteudos, monkeypatch):
    antes = snapshot(database)
    monkeypatch.setattr(camadas.repo, "salvar_edicao", Mock(side_effect=PyMongoError("Falha")))
    cenario.storage.remover.side_effect = camadas.ErroArmazenamento("Falha na remoção")
    with pytest.raises(camadas.ErroLimpeza) as erro:
        cenario.editar({"descricao": "Correção"}, [arquivo(conteudos["png"])])
    assert len(erro.value.pendentes) == 1
    assert erro.value.pendentes[0]["public_id"] in cenario.remotos
    assert snapshot(database) == antes


def test_repositorio_recusa_atualizacao_de_campo_protegido(camadas, cenario, database):
    antes = snapshot(database)
    documento = database.tbl_avancos.find_one({"_id": cenario.avanco})
    with pytest.raises(ValueError):
        camadas.repo.salvar_edicao(documento, {"estado": "publicado"}, cenario.fotos, [m["_id"] for m in cenario.fotos], [])
    assert snapshot(database) == antes


def test_normalizacao_nao_muta_entrada_nem_cria_campos_ausentes(camadas):
    identificador = str(ObjectId())
    dados = {"descricao": "  Revisada  ", "midias_manter": [identificador]}
    antes = deepcopy(dados)
    assert camadas.validacoes.validar_edicao(dados) is None
    assert camadas.validacoes.normalizar_edicao(dados) == {
        "descricao": "Revisada", "midias_manter": [ObjectId(identificador)],
    }
    assert dados == antes


@pytest.mark.parametrize("falha", ["vazio", "id_alheio", "vinculo_alheio"])
def test_repositorio_defende_invariantes_sem_depender_do_service(camadas, cenario, database, falha):
    documento = database.tbl_avancos.find_one({"_id": cenario.avanco})
    anteriores = deepcopy(cenario.fotos)
    manter = [m["_id"] for m in anteriores]
    if falha == "vazio":
        manter = []
    elif falha == "id_alheio":
        manter = [ObjectId()]
    else:
        anteriores[0]["avanco_id"] = ObjectId()
    antes = snapshot(database)
    with pytest.raises(ValueError):
        camadas.repo.salvar_edicao(documento, {}, anteriores, manter, [])
    assert snapshot(database) == antes


def test_metadados_novos_invalidos_compensam_upload(camadas, cenario, database, conteudos):
    enviar = cenario.storage.enviar.side_effect

    def enviar_com_metadados_invalidos(validado):
        metadados = enviar(validado)
        metadados["mime"] = "text/html"
        return metadados

    cenario.storage.enviar.side_effect = enviar_com_metadados_invalidos
    antes, remotos = snapshot(database), dict(cenario.remotos)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        cenario.editar({"midias_manter": []}, [arquivo(conteudos["png"])])
    assert erro.value.status == 422
    assert snapshot(database) == antes
    assert cenario.remotos == remotos


@pytest.mark.parametrize("falha", ["configuracao", "credenciais"])
def test_configuracao_invalida_nao_muda_rascunho(camadas, cenario, database, monkeypatch, falha):
    excecao = ValueError("Configuração inválida") if falha == "configuracao" else camadas.ErroArmazenamento("Credenciais ausentes")
    monkeypatch.setattr(camadas.service, "ServicoMidias", Mock(side_effect=excecao))
    antes = snapshot(database)
    with pytest.raises(camadas.service.ErroAvanco) as erro:
        camadas.service.editar_rascunho(str(cenario.avanco), {"descricao": "Correção"})
    assert erro.value.status == 503
    assert snapshot(database) == antes


def test_limpeza_reverifica_referencia_a_publicacao(camadas, cenario, database):
    a, b = cenario.fotos
    remover = cenario.storage.remover.side_effect
    cenario.storage.remover.side_effect = camadas.ErroArmazenamento("Indisponível")
    cenario.editar({"midias_manter": [str(a["_id"])]})
    database.tbl_avancos.insert_one({"publicacao": {"midias": [{"id": str(b["_id"])}]}})
    cenario.storage.remover.reset_mock()
    cenario.storage.remover.side_effect = remover
    tarefa = database.tbl_limpezas_midias.find_one({"_id": b["_id"]})
    camadas.service._limpar_apos_edicao(cenario.midias, [tarefa["midia"]])
    cenario.storage.remover.assert_not_called()
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]}) is not None


def test_limpeza_continua_apos_falha_em_um_arquivo(camadas, cenario, database, conteudos):
    a, b = cenario.fotos
    remover = cenario.storage.remover.side_effect

    def remover_com_falha_em_a(referencia):
        if referencia == a["referencia_externa"]:
            raise camadas.ErroArmazenamento("Indisponível")
        return remover(referencia)

    cenario.storage.remover.side_effect = remover_com_falha_em_a
    assert cenario.editar({"midias_manter": []}, [arquivo(conteudos["png"])])["estado"] == "rascunho"
    assert database.tbl_limpezas_midias.find_one({"_id": a["_id"]}) is not None
    assert database.tbl_limpezas_midias.find_one({"_id": b["_id"]}) is None
    assert a["referencia_externa"]["public_id"] in cenario.remotos
    assert b["referencia_externa"]["public_id"] not in cenario.remotos


@pytest.mark.parametrize("campo", ["resource_type", "delivery_type", "provedor", "public_id"])
def test_referencia_de_outro_recurso_nao_impede_limpeza(camadas, cenario, database, campo):
    referencia = deepcopy(cenario.fotos[0]["referencia_externa"])
    referencia[campo] = "outro-recurso"
    assert camadas.repo.referencia_em_uso(referencia) is False


def test_falha_na_midia_mantida_desfaz_revisao(camadas, cenario, database, monkeypatch):
    antes = snapshot(database)
    monkeypatch.setattr(database.tbl_midias, "update_one", Mock(side_effect=PyMongoError("Falha")))
    with pytest.raises(PyMongoError):
        cenario.editar({"descricao": "Não deve persistir"})
    assert snapshot(database) == antes
