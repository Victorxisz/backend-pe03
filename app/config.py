"""Configuração de mídia lida apenas quando o serviço é criado."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfiguracaoArmazenamento:
    cloud_name: str = field(repr=False)
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    pasta: str = "pe03/evidencias"
    limite_foto: int = 10 * 1024 * 1024
    limite_video: int = 100 * 1024 * 1024
    limite_documento: int = 10 * 1024 * 1024
    validade_acesso: int = 300
    timeout: int = 30

    @classmethod
    def do_ambiente(cls, prefixo=""):
        def numero(nome, padrao):
            try:
                valor = int(os.getenv(prefixo + nome, str(padrao)))
                if valor <= 0:
                    raise ValueError
                return valor
            except ValueError:
                raise ValueError(f"Configure {prefixo + nome} com um inteiro positivo") from None

        return cls(
            cloud_name=os.getenv(prefixo + "CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.getenv(prefixo + "CLOUDINARY_API_KEY", ""),
            api_secret=os.getenv(prefixo + "CLOUDINARY_API_SECRET", ""),
            pasta=os.getenv(prefixo + "CLOUDINARY_FOLDER", "pe03/evidencias"),
            limite_foto=numero("MIDIA_FOTO_MAX_BYTES", 10 * 1024 * 1024),
            limite_video=numero("MIDIA_VIDEO_MAX_BYTES", 100 * 1024 * 1024),
            limite_documento=numero("MIDIA_DOCUMENTO_MAX_BYTES", 10 * 1024 * 1024),
            validade_acesso=numero("MIDIA_ACESSO_SEGUNDOS", 300),
            timeout=numero("CLOUDINARY_TIMEOUT", 30),
        )
