"""Arquivos válidos gerados em memória para testes de envio e recuperação."""

from io import BytesIO
import av
import pytest
from PIL import Image
from pypdf import PdfWriter
from werkzeug.datastructures import FileStorage
from app.config import ConfiguracaoArmazenamento

@pytest.fixture
def config():
    return ConfiguracaoArmazenamento("nuvem-ficticia", "chave-ficticia", "segredo-ficticio")



@pytest.fixture(scope="module")
def conteudos():
    imagens = {}
    for formato, extensao in (("JPEG", "jpg"), ("PNG", "png")):
        buffer = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(buffer, format=formato)
        imagens[extensao] = buffer.getvalue()
    buffer = BytesIO()
    pdf = PdfWriter()
    pdf.add_blank_page(width=72, height=72)
    pdf.write(buffer)
    imagens["pdf"] = buffer.getvalue()
    buffer = BytesIO()
    with av.open(buffer, mode="w", format="mp4") as video:
        stream = video.add_stream("mpeg4", rate=1)
        stream.width = stream.height = 16
        stream.pix_fmt = "yuv420p"
        frame = av.VideoFrame(16, 16, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        for packet in stream.encode(frame):
            video.mux(packet)
        for packet in stream.encode():
            video.mux(packet)
    imagens["mp4"] = buffer.getvalue()
    return imagens



def arquivo(conteudo, nome="evidencia.bin", mime="application/octet-stream"):
    return FileStorage(stream=BytesIO(conteudo), filename=nome, content_type=mime)

