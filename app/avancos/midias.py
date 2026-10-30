"""Validação por conteúdo e compensação dos uploads de uma operação de negócio."""

from dataclasses import dataclass
from io import BytesIO
import warnings
from pymongo.errors import PyMongoError

import av
from PIL import Image
from pypdf import PdfReader
from werkzeug.utils import secure_filename

from app.config import ConfiguracaoArmazenamento
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento, ErroLimpeza


class ErroMidia(ValueError):
    def __init__(self, mensagem, status=422, codigo="MIDIA_INVALIDA", campos=None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.campos = ["midias"] if campos is None else list(campos)


@dataclass(frozen=True)
class ArquivoValidado:
    conteudo: bytes
    tipo: str
    nome: str
    mime: str
    formato: str

    @property
    def tamanho(self):
        return len(self.conteudo)


def validar_arquivo(arquivo, config):
    """Arquivo recebido como FileStorage; extensão e Content-Type não definem o tipo."""
    if arquivo is None or not getattr(arquivo, "filename", ""):
        raise ErroMidia("Envie um arquivo com nome")
    teto = max(config.limite_foto, config.limite_video, config.limite_documento)
    conteudo = arquivo.stream.read(teto + 1)
    if len(conteudo) > teto:
        raise ErroMidia("Arquivo excede o tamanho máximo permitido", 413)
    if not conteudo:
        raise ErroMidia("Não envie arquivos vazios")
    try:
        if conteudo.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
            tipo, limite = "foto", config.limite_foto
            if len(conteudo) > limite:
                raise ErroMidia("Foto excede o limite configurado", 413)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(conteudo)) as image:
                    formato = {"JPEG": "jpg", "PNG": "png"}[image.format]
                    image.verify()
                with Image.open(BytesIO(conteudo)) as image:
                    image.load()
            mime = "image/jpeg" if formato == "jpg" else "image/png"
        elif conteudo.startswith(b"%PDF-"):
            tipo, formato, mime, limite = "documento", "pdf", "application/pdf", config.limite_documento
            if len(conteudo) > limite:
                raise ErroMidia("Documento excede o limite configurado", 413)
            documento = PdfReader(BytesIO(conteudo), strict=True)
            if documento.is_encrypted or not documento.pages:
                raise ValueError("PDF vazio ou protegido")
            for pagina in documento.pages:
                # Força leitura dos objetos de conteúdo, além do cabeçalho PDF.
                conteudos = pagina.get_contents()
                if conteudos is not None:
                    conteudos.get_data()
        elif len(conteudo) >= 12 and conteudo[4:8] == b"ftyp":
            tipo, formato, mime, limite = "video", "mp4", "video/mp4", config.limite_video
            if len(conteudo) > limite:
                raise ErroMidia("Vídeo excede o limite configurado", 413)
            marcas = [conteudo[8:12]]
            tamanho_ftyp = int.from_bytes(conteudo[:4], "big")
            if tamanho_ftyp < 16 or tamanho_ftyp > len(conteudo):
                raise ValueError("MP4 inválido")
            marcas.extend(conteudo[i:i+4] for i in range(16, tamanho_ftyp, 4))
            if not set(marcas) & {b"isom", b"iso2", b"mp41", b"mp42", b"avc1"}:
                raise ValueError("Contêiner não permitido")
            with av.open(BytesIO(conteudo)) as video:
                if not video.streams.video or next(video.decode(video=0), None) is None:
                    raise ValueError("MP4 sem imagem decodificável")
        else:
            raise ErroMidia("Formato não permitido. Use JPEG, PNG, MP4 ou PDF")
    except ErroMidia:
        raise
    except Exception:
        raise ErroMidia("Arquivo inválido, corrompido ou protegido") from None
    nome = secure_filename(arquivo.filename)[:180] or "arquivo"
    return ArquivoValidado(conteudo, tipo, nome, mime, formato)


class ServicoMidias:
    def __init__(self, armazenamento=None, config=None):
        self.config = config or (armazenamento.config if armazenamento else ConfiguracaoArmazenamento.do_ambiente())
        self.armazenamento = armazenamento or ArmazenamentoCloudinary(self.config)

    def executar_com_midias(
        self,
        arquivos,
        salvar,
        *,
        permitir_sem_novos=False,
    ):
        """
        Valida os arquivos, envia e chama salvar(metadados).

        salvar deve retornar após a confirmação da transação.
        A limpeza dos arquivos antigos acontece fora deste método.
        """
        arquivos = list(arquivos)

        if not arquivos and not permitir_sem_novos:
            raise ErroMidia(
                "Envie ao menos uma foto, vídeo ou documento"
            )

        # Valida todo o lote antes de começar os uploads.
        validados = [
            validar_arquivo(arquivo, self.config)
            for arquivo in arquivos
        ]

        enviados = []

        try:
            for arquivo in validados:
                enviados.append(
                    self.armazenamento.enviar(arquivo)
                )

            return salvar(enviados)

        except Exception as erro:
            # O banco pode ter confirmado a transação sem que a
            # confirmação tenha chegado à aplicação. Nesse caso,
            # não podemos apagar arquivos possivelmente em uso.
            if (
                isinstance(erro, PyMongoError)
                and erro.has_error_label(
                    "UnknownTransactionCommitResult"
                )
            ):
                raise

            pendentes = (
                list(erro.pendentes)
                if isinstance(erro, ErroLimpeza)
                else []
            )

            for midia in reversed(enviados):
                referencia = midia["referencia_externa"]

                try:
                    self.armazenamento.remover(referencia)
                except ErroArmazenamento:
                    pendentes.append(referencia)

            if pendentes:
                raise ErroLimpeza(pendentes) from erro

            raise

    def limpar_sem_referencias(self, midias, referencia_em_uso, ):
        pendentes = []

        for midia in midias:
            referencia = midia["referencia_externa"]

            try:
                if referencia_em_uso(referencia):
                    continue

                self.armazenamento.remover(referencia)
            except (ErroArmazenamento, PyMongoError):
                pendentes.append(referencia)

        return pendentes