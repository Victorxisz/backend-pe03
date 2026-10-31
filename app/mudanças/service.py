"""Replanejamento de obras e marcos sem atalhos para as regras de estado."""

from bson import ObjectId
from bson.errors import InvalidId

from app.dominio.comum import ErroDominio, Mudanca, Relogio
from app.dominio.obras import PrazoEntrega
from app.marcos.service import ServicoMarcos
from app.marcos.validacoes import validar_periodo_previsto
from app.obras.service import ServicoObras
from app.serializacao import serializar
from .repository import MudancaConcorrente, RepositorioMudancas
from .validacoes import validar_mudanca


class ErroMudanca(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)


class ServicoMudancas:
    def __init__(self, repositorio=None, obras=None, marcos=None, relogio=None):
        self.relogio = relogio if relogio is not None else Relogio()
        self.repositorio = repositorio if repositorio is not None else RepositorioMudancas()
        self.obras = obras if obras is not None else ServicoObras(relogio=self.relogio)
        self.marcos = marcos if marcos is not None else ServicoMarcos(relogio=self.relogio)

    def aplicar(self, obra_id, dados, autor):
        try:
            validar_mudanca(dados)
            return self._aplicar(obra_id, dados, autor)
        except ErroDominio as erro:
            raise ErroMudanca(str(erro), 422, erro.campos) from erro
        except MudancaConcorrente as erro:
            raise ErroMudanca("O alvo foi alterado; consulte novamente", 409, ["versao"]) from erro

    def _aplicar(self, obra_id, dados, autor):
        # As consultas existentes validam ids, existência e pertencimento à obra.
        obra = self.obras.buscar_obra(obra_id)
        alvo = dados["alvo"]
        try:
            if not isinstance(alvo["id"], str):
                raise InvalidId()
            alvo_id = ObjectId(alvo["id"])
        except (InvalidId, TypeError):
            raise ErroMudanca("ID do alvo inválido", 400, ["alvo.id"]) from None
        if alvo["tipo"] == "obra":
            if str(alvo_id) != obra["id"]:
                raise ErroMudanca("O alvo não pertence à obra", 404, ["alvo.id"])
            documento = self.obras.repositorio.buscar_obra_por_id(alvo_id)
        else:
            self.marcos.buscar_marco(obra_id, str(alvo_id))
            documento = self.marcos.repositorio.buscar_marco_por_id(alvo_id)
        if documento is None:
            raise ErroMudanca("Alvo não encontrado", 404, ["alvo.id"])
        if documento.get("versao", 0) != dados["versao"]:
            raise MudancaConcorrente()

        campo = dados["campo"]
        novo_valor = dados["novo_valor"]
        if campo == "estado":
            parametros = {"estado": novo_valor, "motivo": dados["motivo"]}
            if alvo["tipo"] == "obra":
                return self.obras.alterar_estado(
                    str(alvo_id), parametros, autor, versao_esperada=dados["versao"]
                )
            if "confirmar_dependencias" in dados:
                parametros["confirmar_dependencias"] = dados["confirmar_dependencias"]
            self.marcos.alterar_estado_marco(
                str(alvo_id), parametros, autor, versao_esperada=dados["versao"]
            )
            return serializar(self.marcos.buscar_marco(obra_id, str(alvo_id)))

        if campo == "entrega":
            novo_valor = PrazoEntrega.de_dados(novo_valor).para_dict()
            anterior = documento["entrega"]
            campos = {"entrega": novo_valor}
        else:
            if not isinstance(novo_valor, dict) or set(novo_valor) != {"inicio_previsto", "fim_previsto"}:
                raise ErroDominio("Informe início e fim previstos", ["novo_valor"])
            erro = validar_periodo_previsto(novo_valor)
            if erro:
                raise ErroDominio(*erro)
            anterior = {campo: documento[campo] for campo in novo_valor}
            campos = dict(novo_valor)

        if anterior == novo_valor:
            return self._representar(alvo["tipo"], documento)
        evento = Mudanca(alvo["tipo"], alvo_id, campo, anterior, novo_valor,
                         dados["motivo"], autor, self.relogio.agora()).para_documento()
        evento["obra_id"] = ObjectId(obra_id)
        salvo = self.repositorio.aplicar(alvo["tipo"], documento, campos, evento)
        return self._representar(alvo["tipo"], salvo)

    def _representar(self, tipo, documento):
        if tipo == "obra":
            return self.obras.obra_para_dict(documento)
        return serializar(self.marcos._marco_para_dict(documento))
