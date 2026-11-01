"""Casos de uso de trabalhadores com armazenamento e relógio substituíveis."""

import re

from bson import ObjectId
from bson.errors import InvalidId

from app.dominio.comum import Relogio
from app.dominio.pessoas import Trabalhador
from validacoes import normalizar_dados_trabalhador, validar_dados_trabalhador
from .repository import RepositorioTrabalhadores


class ErroTrabalhador(Exception):
    def __init__(self, corpo, status):
        self.corpo, self.status = corpo, status
        super().__init__(corpo.get("erro", "Dados de trabalhador inválidos"))


def trabalhador_para_dict(documento):
    campos = ("email", "telefone", "cargo", "ativo")
    dados = {campo: documento.get(campo) for campo in campos}
    dados.update(id=str(documento["_id"]), nome=documento.get("nome", ""),
                 obras=documento.get("obras", []),
                 data_cadastro=documento.get("data_cadastro", documento.get("criado_em")))
    if "construtora_id" in documento:
        dados["construtora_id"] = documento["construtora_id"]
    return dados


class ServicoTrabalhadores:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio if repositorio is not None else RepositorioTrabalhadores()
        self.relogio = relogio if relogio is not None else Relogio()

    def _identificar(self, valor, tipo):
        try:
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroTrabalhador({"erro": f"ID {tipo} inválido"}, 400) from None

    def _validar(self, dados, *, atualizacao=False):
        erro = validar_dados_trabalhador(dados, atualizacao=atualizacao)
        if erro:
            raise ErroTrabalhador(*erro)
        return normalizar_dados_trabalhador(dados, incluir_obras=atualizacao)

    def _exigir_obra(self, identificador, autor):
        obra = self.repositorio.buscar_obra(identificador)
        if obra is None or (obra.get("autor") and obra["autor"] != autor):
            raise ErroTrabalhador({"erro": "Obra não encontrada"}, 404)
        return obra

    def _exigir_trabalhador(self, identificador, autor):
        documento = self.repositorio.buscar(identificador)
        if documento is None or (documento.get("construtora_id") and documento["construtora_id"] != autor):
            raise ErroTrabalhador({"erro": "Trabalhador não encontrado"}, 404)
        return documento

    def cadastrar(self, obra_id, dados, autor):
        identificador = self._identificar(obra_id, "da obra")
        normalizados = self._validar(dados)
        self._exigir_obra(identificador, autor)
        trabalhador = Trabalhador(**normalizados, construtora_id=autor, data_cadastro=self.relogio.agora())
        trabalhador.vincular_obra(identificador)
        novo_id = self.repositorio.inserir(trabalhador.para_documento())
        return {"mensagem": "Trabalhador criado com sucesso e vinculado à obra",
                "id": str(novo_id), "obra_id": str(identificador)}

    def detalhar(self, trabalhador_id, autor):
        identificador = self._identificar(trabalhador_id, "do trabalhador")
        return trabalhador_para_dict(self._exigir_trabalhador(identificador, autor))

    def atualizar(self, trabalhador_id, dados, autor):
        identificador = self._identificar(trabalhador_id, "do trabalhador")
        campos = self._validar(dados, atualizacao=True)
        if "obras" in campos:
            existentes = self.repositorio.obras_existentes([ObjectId(valor) for valor in campos["obras"]])
            encontradas = {str(obra["_id"]) for obra in existentes
                           if not obra.get("autor") or obra["autor"] == autor}
            ausentes = sorted(set(campos["obras"]) - encontradas)
            if ausentes:
                raise ErroTrabalhador({"erro": "Uma ou mais obras não foram encontradas", "obras": ausentes}, 422)
        self._exigir_trabalhador(identificador, autor)
        if not self.repositorio.atualizar(identificador, campos):
            raise ErroTrabalhador({"erro": "Trabalhador não encontrado"}, 404)
        return {"mensagem": "Trabalhador atualizado com sucesso", "id": str(identificador)}

    def excluir(self, trabalhador_id, autor):
        identificador = self._identificar(trabalhador_id, "do trabalhador")
        self._exigir_trabalhador(identificador, autor)
        if not self.repositorio.excluir(identificador):
            raise ErroTrabalhador({"erro": "Trabalhador não encontrado"}, 404)
        return {"mensagem": "Trabalhador excluído com sucesso"}

    def filtrar_texto(self, campo, termo, autor):
        termo = termo.strip()
        if not termo:
            raise ErroTrabalhador({"erro": f"Digite um {'nome' if campo == 'nome' else 'cargo'} para pesquisar"}, 422)
        return self._consultar({campo: {"$regex": re.escape(termo), "$options": "i"}}, autor)

    def por_obra(self, obra_id, autor):
        identificador = self._identificar(obra_id, "da obra")
        self._exigir_obra(identificador, autor)
        return self._consultar({"obras": str(identificador)}, autor)

    def _consultar(self, filtro, autor):
        return [trabalhador_para_dict(documento) for documento in self.repositorio.consultar(filtro)
                if not documento.get("construtora_id") or documento["construtora_id"] == autor]
