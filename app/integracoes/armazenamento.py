"""Operações Cloudinary; referências são persistentes, URLs de acesso expiram."""

import re
from io import BytesIO
from time import time
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import urlopen

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from cloudinary.exceptions import NotFound

from app.config import ConfiguracaoArmazenamento


class ErroArmazenamento(Exception):
    def __init__(self, mensagem, status=503):
        super().__init__(mensagem)
        self.status = status


class ErroLimpeza(ErroArmazenamento):
    def __init__(self, pendentes):
        super().__init__("A operação falhou e há arquivos pendentes de remoção")
        self.pendentes = pendentes


class ArmazenamentoCloudinary:
    def __init__(self, config=None):
        self.config = config or ConfiguracaoArmazenamento.do_ambiente()
        if not all((self.config.cloud_name, self.config.api_key, self.config.api_secret)):
            raise ErroArmazenamento("Configure as credenciais de armazenamento no servidor")
        pasta = self.config.pasta
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", pasta):
            raise ErroArmazenamento("Configure uma pasta válida para as evidências")

    def _opcoes(self):
        # Opções por chamada: não modifica a configuração global do SDK.
        return dict(cloud_name=self.config.cloud_name, api_key=self.config.api_key,
                    api_secret=self.config.api_secret, timeout=self.config.timeout)

    def _referencia(self, referencia):
        if not isinstance(referencia, dict):
            raise ErroArmazenamento("Referência de mídia inválida", 422)
        public_id = referencia.get("public_id", "")
        if (not isinstance(public_id, str)
                or not re.fullmatch(re.escape(self.config.pasta) + r"/[0-9a-f]{32}(?:\.pdf)?", public_id)
                or referencia.get("resource_type") not in {"image", "video", "raw"}
                or referencia.get("delivery_type") != "authenticated"):
            raise ErroArmazenamento("Referência de mídia inválida", 422)
        return dict(public_id=public_id, resource_type=referencia["resource_type"],
                    type="authenticated")

    def enviar(self, arquivo):
        """Recebe somente um ArquivoValidado produzido pelo validador de mídia."""
        resource_type = {"foto": "image", "video": "video", "documento": "raw"}[arquivo.tipo]
        public_id = self.config.pasta + "/" + uuid4().hex
        if resource_type == "raw":
            public_id += ".pdf"
        referencia = dict(provedor="cloudinary", public_id=public_id, resource_type=resource_type,
                          delivery_type="authenticated", formato=arquivo.formato)
        try:
            resultado = cloudinary.uploader.upload(
                BytesIO(arquivo.conteudo), public_id=public_id, resource_type=resource_type,
                type="authenticated", overwrite=False, unique_filename=False,
                **self._opcoes(),
            )
            if resultado.get("public_id") != public_id or resultado.get("bytes") != arquivo.tamanho:
                raise ValueError("Resposta de upload inconsistente")
            if resultado.get("resource_type") != resource_type or resultado.get("type") != "authenticated":
                raise ValueError("Resposta de upload inconsistente")
        except Exception:
            # ID é escolhido antes do envio: mesmo timeout pode ter gravado o arquivo.
            try:
                self.remover(referencia)
            except ErroArmazenamento:
                raise ErroLimpeza([referencia]) from None
            raise ErroArmazenamento("Não foi possível enviar a mídia. Tente novamente") from None
        return dict(tipo=arquivo.tipo, nome=arquivo.nome, tamanho=arquivo.tamanho,
                    mime=arquivo.mime, referencia_externa=referencia)

    def verificar_disponibilidade(self, referencia):
        opcoes = self._referencia(referencia)
        try:
            resultado = cloudinary.api.resource(**opcoes, **self._opcoes())
        except NotFound:
            return False
        except Exception:
            raise ErroArmazenamento("Não foi possível verificar a disponibilidade da mídia") from None
        if not isinstance(resultado, dict) or resultado.get("public_id") != opcoes["public_id"]:
            raise ErroArmazenamento("O armazenamento não confirmou a disponibilidade da mídia")
        return True

    def obter_acesso(self, referencia):
        opcoes = self._referencia(referencia)
        if not self.verificar_disponibilidade(referencia):
            raise ErroArmazenamento("Mídia não encontrada no armazenamento", 404)
        expires_at = int(time()) + self.config.validade_acesso
        try:
            url = cloudinary.utils.private_download_url(
                opcoes.pop("public_id"),
                referencia.get("formato"),
                expires_at=expires_at, attachment=True, **opcoes, **self._opcoes(),
            )
        except Exception:
            raise ErroArmazenamento("Não foi possível gerar acesso à mídia") from None
        return {"url": url, "expira_em": expires_at}

    def remover(self, referencia):
        opcoes = self._referencia(referencia)
        try:
            resultado = cloudinary.uploader.destroy(invalidate=True, **opcoes, **self._opcoes())
            if resultado.get("result") not in {"ok", "not found"}:
                raise ValueError("Remoção não confirmada")
        except Exception:
            raise ErroArmazenamento("Não foi possível remover a mídia") from None

    def obter_conteudo(self, referencia, tamanho_esperado):
        """Baixa o original no servidor, sem expor a URL assinada ao navegador."""
        teto = max(self.config.limite_foto, self.config.limite_video, self.config.limite_documento)
        if type(tamanho_esperado) is not int or not 0 < tamanho_esperado <= teto:
            raise ErroArmazenamento("Tamanho da mídia armazenada inválido", 502)
        acesso = self.obter_acesso(referencia)
        try:
            with urlopen(acesso["url"], timeout=self.config.timeout) as resposta:
                conteudo = resposta.read(tamanho_esperado + 1)
        except HTTPError as erro:
            if erro.code == 404:
                raise ErroArmazenamento("Mídia não encontrada no armazenamento", 404) from None
            raise ErroArmazenamento("Não foi possível recuperar o arquivo da mídia") from None
        except Exception:
            raise ErroArmazenamento("Não foi possível recuperar o arquivo da mídia") from None
        if len(conteudo) != tamanho_esperado:
            raise ErroArmazenamento("O armazenamento devolveu um arquivo de tamanho inconsistente", 502)
        return conteudo
