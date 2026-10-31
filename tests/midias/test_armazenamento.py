"""UC-08: infraestrutura de mídia — CT-31/32/34/35 e CT-109/110.

Os testes locais não comprovam o fluxo completo de rascunhos nem o Cloudinary real.
"""

import os
from dataclasses import replace
from unittest.mock import Mock
from urllib.request import urlopen
from urllib.parse import parse_qs, urlparse

import pytest
from cloudinary.exceptions import NotFound
from werkzeug.datastructures import FileStorage

from support_midias import config, conteudos, arquivo
from app.config import ConfiguracaoArmazenamento
from app.avancos.midias import ErroMidia, ServicoMidias, validar_arquivo
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento, ErroLimpeza


@pytest.fixture
def provedor(monkeypatch, config):
    def resposta(stream, **opcoes):
        return {"public_id": opcoes["public_id"], "bytes": len(stream.getvalue()),
                "resource_type": opcoes["resource_type"], "type": opcoes["type"]}
    upload = Mock(side_effect=resposta)
    destroy = Mock(return_value={"result": "ok"})
    resource = Mock(side_effect=lambda **kwargs: {"public_id": kwargs["public_id"]})
    monkeypatch.setattr("cloudinary.uploader.upload", upload)
    monkeypatch.setattr("cloudinary.uploader.destroy", destroy)
    monkeypatch.setattr("cloudinary.api.resource", resource)
    return ArmazenamentoCloudinary(config), upload, destroy, resource


@pytest.mark.parametrize("campo,valor", [
    ("resource_type", []), ("resource_type", {}),
    ("resource_type", None), ("resource_type", "desconhecido"),
    ("public_id", []), ("public_id", "outra-pasta/" + "a" * 32),
    ("provedor", "outro"), ("delivery_type", "upload"),
])
def test_referencia_malformada_recusada_antes_de_acessar_provedor(
    provedor, config, campo, valor
):
    storage, upload, destroy, resource = provedor
    referencia = {
        "provedor": "cloudinary",
        "public_id": config.pasta + "/" + "a" * 32,
        "resource_type": "image",
        "delivery_type": "authenticated",
        "formato": "png",
    }
    referencia[campo] = valor

    with pytest.raises(ErroArmazenamento) as erro:
        storage.obter_acesso(referencia)

    assert erro.value.status == 422
    upload.assert_not_called()
    destroy.assert_not_called()
    resource.assert_not_called()


@pytest.mark.parametrize("extensao,tipo,mime", [
    ("jpg", "foto", "image/jpeg"), ("png", "foto", "image/png"),
    ("mp4", "video", "video/mp4"), ("pdf", "documento", "application/pdf"),
])
def test_ct31_ct32_valida_conteudo_independente_do_nome(config, conteudos, extensao, tipo, mime):
    # Preparação: nome e MIME não anunciam o tipo verdadeiro.
    recebido = arquivo(conteudos[extensao], "../../evidencia.bin")
    # Execução
    validado = validar_arquivo(recebido, config)
    # Verificação
    assert validado.tipo == tipo
    assert validado.mime == mime
    assert validado.formato == extensao
    assert validado.tamanho == len(conteudos[extensao])
    assert "/" not in validado.nome


@pytest.mark.parametrize("extensao,tipo_recurso", [("png", "image"), ("jpg", "image"), ("mp4", "video"), ("pdf", "raw")])
def test_ct31_ct32_upload_metadados_e_remocao(provedor, config, conteudos, extensao, tipo_recurso):
    # Preparação
    storage, upload, destroy, _ = provedor
    validado = validar_arquivo(arquivo(conteudos[extensao]), config)
    # Execução
    metadata = storage.enviar(validado)
    storage.remover(metadata["referencia_externa"])
    # Verificação
    assert metadata["tamanho"] == len(conteudos[extensao])
    assert metadata["tipo"] == validado.tipo
    assert metadata["nome"] == "evidencia.bin"
    assert "url" not in metadata  # Não persiste URL temporária.
    ref = metadata["referencia_externa"]
    assert ref["resource_type"] == tipo_recurso
    assert ref["delivery_type"] == "authenticated"
    assert upload.call_args.kwargs["overwrite"] is False
    assert destroy.call_args.kwargs["public_id"] == ref["public_id"]
    assert destroy.call_args.kwargs["resource_type"] == tipo_recurso
    assert destroy.call_args.kwargs["invalidate"] is True


@pytest.mark.parametrize("conteudo", [b"", b"<script>fake</script>", b"%PDF-falso", b"\x89PNG\r\n\x1a\ncorrompido", b"\x00\x00\x00\x18ftypisom000000000000"])
def test_ct34_rejeita_arquivo_falso_antes_do_upload(provedor, conteudo):
    # Preparação
    storage, upload, _, _ = provedor
    callback = Mock()
    # Execução
    with pytest.raises(ErroMidia):
        ServicoMidias(storage).executar_com_midias([arquivo(conteudo, "foto.jpg", "image/jpeg")], callback)
    # Verificação
    upload.assert_not_called()
    callback.assert_not_called()


@pytest.mark.parametrize("extensao,campo", [("png", "limite_foto"), ("mp4", "limite_video"), ("pdf", "limite_documento")])
def test_ct34_limite_por_tipo(config, conteudos, extensao, campo):
    # Preparação
    conteudo = conteudos[extensao]
    limite_exato = replace(config, **{campo: len(conteudo)})
    menor = replace(config, **{campo: len(conteudo) - 1})
    # Execução e verificação
    assert validar_arquivo(arquivo(conteudo), limite_exato).tamanho == len(conteudo)
    with pytest.raises(ErroMidia) as erro:
        validar_arquivo(arquivo(conteudo), menor)
    assert erro.value.status == 413


def test_ct34_leitura_limitada(config):
    # Preparação
    config = replace(config, limite_foto=10, limite_video=10, limite_documento=10)
    stream = Mock()
    stream.read.return_value = b"X" * 11
    recebido = FileStorage(stream=stream, filename="grande.mp4")
    # Execução
    with pytest.raises(ErroMidia) as erro:
        validar_arquivo(recebido, config)
    # Verificação
    assert erro.value.status == 413
    stream.read.assert_called_once_with(11)


def test_ct34_valida_todo_lote_antes_do_primeiro_upload(provedor, conteudos):
    # Preparação
    storage, upload, _, _ = provedor
    callback = Mock()
    # Execução
    with pytest.raises(ErroMidia):
        ServicoMidias(storage).executar_com_midias([arquivo(conteudos["png"]), arquivo(b"falso")], callback)
    # Verificação
    upload.assert_not_called()
    callback.assert_not_called()


def test_ct35_lote_sem_midia_rejeitado(provedor):
    # Preparação
    storage, upload, _, _ = provedor
    callback = Mock()
    # Execução
    with pytest.raises(ErroMidia):
        ServicoMidias(storage).executar_com_midias([], callback)
    # Verificação
    upload.assert_not_called()
    callback.assert_not_called()


def test_ct35_salva_so_depois_de_todos_uploads(provedor, conteudos):
    # Preparação
    storage, upload, destroy, _ = provedor
    def salvar(metadata):
        assert upload.call_count == 2
        assert len(metadata) == 2
        return {"id": "avanco-ficticio", "midias": metadata}
    # Execução
    result = ServicoMidias(storage).executar_com_midias([arquivo(conteudos["png"]), arquivo(conteudos["pdf"])], salvar)
    # Verificação
    assert result["id"] == "avanco-ficticio"
    destroy.assert_not_called()


def test_ct35_falha_negocio_remove_novos_arquivos(provedor, conteudos):
    # Preparação
    storage, _, destroy, _ = provedor
    salvar = Mock(side_effect=RuntimeError("falha fictícia do banco"))
    # Execução
    with pytest.raises(RuntimeError):
        ServicoMidias(storage).executar_com_midias([arquivo(conteudos["png"]), arquivo(conteudos["pdf"])], salvar)
    # Verificação
    assert destroy.call_count == 2
    assert len({call.kwargs["public_id"] for call in destroy.call_args_list}) == 2


def test_ct35_timeout_no_segundo_envio_compensa_o_lote(provedor, conteudos):
    # Preparação
    storage, upload, destroy, _ = provedor
    responder = upload.side_effect
    # Usa um primeiro upload verdadeiro simulado, preservando o ID escolhido pelo serviço.
    contador = 0
    def enviar(stream, **kwargs):
        nonlocal contador
        contador += 1
        if contador == 2:
            raise TimeoutError("detalhe privado")
        return responder(stream, **kwargs)
    upload.side_effect = enviar
    salvar = Mock()
    # Execução
    with pytest.raises(ErroArmazenamento) as erro:
        ServicoMidias(storage).executar_com_midias([arquivo(conteudos["png"]), arquivo(conteudos["pdf"])], salvar)
    # Verificação
    assert "privado" not in str(erro.value)
    assert destroy.call_count == 2
    salvar.assert_not_called()


def test_ct35_falha_limpeza_informa_referencias_pendentes(provedor, conteudos):
    # Preparação
    storage, _, destroy, _ = provedor
    destroy.side_effect = OSError("provedor indisponível")
    salvar = Mock(side_effect=RuntimeError("falha fictícia do banco"))
    # Execução
    with pytest.raises(ErroLimpeza) as erro:
        ServicoMidias(storage).executar_com_midias([arquivo(conteudos["png"]), arquivo(conteudos["pdf"])], salvar)
    # Verificação
    assert len(erro.value.pendentes) == 2
    assert destroy.call_count == 2


@pytest.mark.parametrize("resposta", [{}, {"result": "error"}])
def test_ct110_remocao_sem_confirmacao_falha(provedor, conteudos, config, resposta):
    # Preparação
    storage, _, destroy, _ = provedor
    metadata = storage.enviar(validar_arquivo(arquivo(conteudos["png"]), config))
    destroy.side_effect = None
    destroy.return_value = resposta
    # Execução e verificação
    with pytest.raises(ErroArmazenamento):
        storage.remover(metadata["referencia_externa"])


def test_ct110_remocao_idempotente(provedor, conteudos, config):
    # Preparação
    storage, _, destroy, _ = provedor
    metadata = storage.enviar(validar_arquivo(arquivo(conteudos["png"]), config))
    destroy.return_value = {"result": "not found"}
    # Execução e verificação
    storage.remover(metadata["referencia_externa"])


@pytest.mark.parametrize("extensao", ["png", "mp4", "pdf"])
def test_ct109_acesso_assinado_temporario(provedor, conteudos, config, extensao):
    # Preparação
    storage, _, _, resource = provedor
    metadata = storage.enviar(validar_arquivo(arquivo(conteudos[extensao]), config))
    # Execução
    access = storage.obter_acesso(metadata["referencia_externa"])
    # Verificação
    assert access["url"].startswith("https://")
    assert "signature=" in access["url"]
    assert "expires_at=" in access["url"]
    assert parse_qs(urlparse(access["url"]).query)["format"] == [extensao]
    assert config.api_secret not in access["url"]
    assert isinstance(access["expira_em"], int)
    resource.assert_called_once()


def test_ct110_arquivo_ausente_diferente_de_indisponibilidade(provedor, conteudos, config):
    # Preparação
    storage, _, _, resource = provedor
    ref = storage.enviar(validar_arquivo(arquivo(conteudos["pdf"]), config))["referencia_externa"]
    resource.side_effect = NotFound("ausente")
    # Execução e verificação
    assert storage.verificar_disponibilidade(ref) is False
    with pytest.raises(ErroArmazenamento) as erro:
        storage.obter_acesso(ref)
    assert erro.value.status == 404
    resource.side_effect = OSError("credencial ou rede indisponível")
    with pytest.raises(ErroArmazenamento) as erro:
        storage.verificar_disponibilidade(ref)
    assert erro.value.status == 503


def test_ct110_resposta_upload_invalida_remove_arquivo(provedor, conteudos, config):
    # Preparação
    storage, upload, destroy, _ = provedor
    upload.side_effect = None
    upload.return_value = {}
    # Execução
    with pytest.raises(ErroArmazenamento):
        storage.enviar(validar_arquivo(arquivo(conteudos["png"]), config))
    # Verificação
    destroy.assert_called_once()


def test_configuracao_sem_credenciais_nao_inicia_upload(monkeypatch):
    # Preparação
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    # Execução e verificação
    with pytest.raises(ErroArmazenamento):
        ArmazenamentoCloudinary()


def test_configuracao_limite_invalido(monkeypatch):
    # Preparação
    monkeypatch.setenv("MIDIA_FOTO_MAX_BYTES", "-1")
    # Execução e verificação
    with pytest.raises(ValueError):
        ConfiguracaoArmazenamento.do_ambiente()


@pytest.mark.cloudinary
@pytest.mark.skipif(os.getenv("RUN_CLOUDINARY_TESTS") != "1", reason="Exige RUN_CLOUDINARY_TESTS=1 e credenciais TEST_CLOUDINARY_* exclusivas")
@pytest.mark.parametrize("extensao", ["png", "mp4", "pdf"])
def test_ct109_cloudinary_real_envia_abre_e_remove(conteudos, extensao):
    # Preparação: nunca usa credenciais padrão ou o banco da aplicação.
    config = ConfiguracaoArmazenamento.do_ambiente(prefixo="TEST_")
    storage = ArmazenamentoCloudinary(config)
    validado = validar_arquivo(arquivo(conteudos[extensao]), config)
    ref = None
    try:
        # Execução
        metadata = storage.enviar(validado)
        ref = metadata["referencia_externa"]
        assert storage.verificar_disponibilidade(ref)
        access = storage.obter_acesso(ref)
        with urlopen(access["url"], timeout=config.timeout) as response:
            recovered = response.read(len(validado.conteudo) + 1)
        # Verificação
        assert recovered == validado.conteudo
    finally:
        if ref is not None:
            storage.remover(ref)
    assert not storage.verificar_disponibilidade(ref)


@pytest.mark.parametrize("resposta", [None, {}, {"public_id": "outro-arquivo"}])
def test_ct110_disponibilidade_sem_confirmacao_nao_e_sucesso(provedor, conteudos, config, resposta):
    # Preparação
    storage, _, _, resource = provedor
    ref = storage.enviar(validar_arquivo(arquivo(conteudos["png"]), config))["referencia_externa"]
    resource.side_effect = None
    resource.return_value = resposta
    # Execução e verificação
    with pytest.raises(ErroArmazenamento):
        storage.verificar_disponibilidade(ref)


def test_ct110_nao_remove_referencia_fora_da_pasta(provedor):
    # Preparação
    storage, _, destroy, _ = provedor
    ref = {"public_id": "outro-projeto/arquivo", "resource_type": "image", "delivery_type": "authenticated"}
    # Execução
    with pytest.raises(ErroArmazenamento) as erro:
        storage.remover(ref)
    # Verificação
    assert erro.value.status == 422
    destroy.assert_not_called()
