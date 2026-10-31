"""Publica somente conteúdo válido com evidências recuperáveis."""

from datetime import timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.avancos.acesso_midias import midia_para_dict
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento
from app.dominio.comum import Relogio
from app.dominio.avancos import Avanco
from . import repository
from .validacoes import validar_midias, validar_rascunho


class ErroPublicacao(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)

class ServicoPublicacoes:
    def __init__(self, repositorio=None, relogio=None, armazenamento_factory=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.relogio = relogio if relogio is not None else Relogio()
        self.armazenamento_factory = armazenamento_factory

    def _id(self, valor, campo):
        try:
            if not isinstance(valor, (str, ObjectId)):
                raise TypeError
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroPublicacao("Identificador inválido", 400, [campo]) from None

    def _avanco(self, valor):
        documento = self.repositorio.buscar_avanco(self._id(valor, "avanco_id"))
        if documento is None:
            raise ErroPublicacao("Avanço não encontrado", 404, ["avanco_id"])
        return documento

    def _representar(self, documento):
        fato = documento["publicacao"]
        instante = fato["instante"]
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
        descricao = documento.get("descricao", fato["descricao"])
        data = documento.get("data", fato["data"])
        midias = []
        for original in fato.get("midias", []):
            item = dict(original)
            if "conteudo" not in item and item.get("id"):
                item["conteudo"] = f"/midias/{item['id']}/conteudo"
            midias.append(item)
        representacao = {
            "id": str(documento["_id"]), "avanco_id": str(documento["_id"]),
            "estado": "publicado", "autor": fato["autor"], "instante": instante.isoformat(),
            "data": data, "descricao": descricao,
            "marco": {"id": str(fato["marco"]["id"]), "nome": fato["marco"]["nome"]},
            "midias": midias,
        }
        if descricao != fato["descricao"] or data != fato["data"]:
            representacao["editado"] = True
        return representacao

    def publicar_avanco(self, avanco_id, autor):
        documento = self._avanco(avanco_id)
        if documento.get("estado") == "publicado" and documento.get("publicacao"):
            return self._representar(documento), False
        if documento.get("estado") != "rascunho" or "publicacao" in documento:
            raise ErroPublicacao("Somente rascunhos podem ser publicados", 409, ["estado"])
        campos = validar_rascunho(documento)
        if campos:
            raise ErroPublicacao("Complete o rascunho antes de publicar", 422, campos)
        marco = self.repositorio.buscar_marco(documento["marco_id"])
        if (marco is None or not isinstance(marco.get("obra_id"), ObjectId)
                or self.repositorio.buscar_obra(marco["obra_id"]) is None):
            raise ErroPublicacao("Marco ou obra não encontrado", 404, ["marco_id"])
        midias = self.repositorio.consultar_midias(documento["_id"])
        if not validar_midias(midias):
            raise ErroPublicacao("O avanço precisa de mídias válidas para publicação", 422, ["midias"])
        try:
            armazenamento = (self.armazenamento_factory or ArmazenamentoCloudinary)()
            for midia in midias:
                # Verifica recuperação real, incluindo limite e tamanho, não apenas a referência.
                armazenamento.obter_conteudo(midia["referencia_externa"], midia["tamanho"])
        except ErroArmazenamento as erro:
            if erro.status in (404, 422):
                raise ErroPublicacao("Uma mídia não está disponível para publicação", 422, ["midias"]) from None
            raise ErroPublicacao("Não foi possível confirmar as mídias no armazenamento", 503, ["midias"]) from None
        except ValueError:
            raise ErroPublicacao("O armazenamento não está configurado corretamente", 503, ["midias"]) from None
        if self.repositorio.consultar_midias(documento["_id"]) != midias:
            raise ErroPublicacao("As mídias foram alteradas; revise o avanço novamente", 409, ["midias"])
        Avanco.de_documento(documento).publicar()
        instante = self.relogio.agora()
        instante = instante.replace(microsecond=instante.microsecond // 1000 * 1000)
        representacoes = []
        for midia in midias:
            item = midia_para_dict(midia)
            item["conteudo"] = f"/midias/{item['id']}/conteudo"
            representacoes.append(item)
        fato = {"autor": autor, "instante": instante, "data": documento["data"],
                "descricao": documento["descricao"],
                "marco": {"id": marco["_id"], "nome": marco.get("nome", "Marco")},
                "midias": representacoes}
        try:
            publicado = self.repositorio.publicar(documento, fato, marco, midias)
        except repository.VinculoAlterado:
            raise ErroPublicacao("Obra, marco ou mídia foi alterado; revise antes de publicar", 409,
                                 ["avanco_id"]) from None
        if publicado is not None:
            return self._representar(publicado), True
        atual = self._avanco(avanco_id)
        if atual.get("estado") == "publicado" and atual.get("publicacao"):
            return self._representar(atual), False
        raise ErroPublicacao("O avanço foi alterado; revise antes de publicar", 409, ["avanco_id"])

    def consultar_publicacoes(self, avanco_id):
        documento = self._avanco(avanco_id)
        if documento.get("estado") != "publicado" or not documento.get("publicacao"):
            return []
        return [self._representar(documento)]

    def consultar_previa(self, obra_id):
        identificador = self._id(obra_id, "obra_id")
        if self.repositorio.buscar_obra(identificador) is None:
            raise ErroPublicacao("Obra não encontrada", 404, ["obra_id"])
        return [self._representar(item) for item in self.repositorio.consultar_publicados(identificador)]


_servico = ServicoPublicacoes()

# Fachada para consumidores anteriores à refatoração.
_id = _servico._id
_avanco = _servico._avanco
_representar = _servico._representar
publicar_avanco = _servico.publicar_avanco
consultar_publicacoes = _servico.consultar_publicacoes
consultar_previa = _servico.consultar_previa
