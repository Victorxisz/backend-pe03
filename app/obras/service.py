"""Cadastro, consulta e edição descritiva das obras."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import re

from bson import ObjectId
from bson.errors import InvalidId

from . import repository
from .validacoes import validar_criacao_obra
from app.dominio.comum import ErroDominio, Relogio
from app.dominio.obras import Obra
from app.serializacao import serializar

EDITAVEIS = {"nome", "descricao", "localizacao", "cliente"}
CADASTRAVEIS = EDITAVEIS | {"tipo", "inicio", "entrega"}


class ErroObra(Exception):
    def __init__(self, mensagem, status, campos=()):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)

class ServicoObras:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.relogio = relogio if relogio is not None else Relogio()

    def obra_para_dict(self, documento):
        obra = {
            campo: valor
            for campo, valor in documento.items()
            if campo not in {"_id", "critica"}
        }

        obra["id"] = str(documento["_id"])
        obra["versao"] = documento.get("versao", 0)

        registro = obra.get("data_registro")
        if isinstance(registro, datetime):
            if registro.tzinfo is None:
                registro = registro.replace(tzinfo=timezone.utc)

            obra["data_registro"] = registro.isoformat()

        if "dependencias_marcos" in documento:
            obra["dependencias_marcos"] = [
                {
                    "id": str(vinculo["_id"]),
                    "marco_id": str(vinculo["marco_id"]),
                    "depende_de_id": str(vinculo["depende_de_id"]),
                }
                for vinculo in documento["dependencias_marcos"]
            ]

        obra["alertas"] = self.calcular_alertas(documento)
        return serializar(obra)

    def criar_obra(self, dados, autor):
        erro = validar_criacao_obra(dados)
        if erro:
            raise ErroObra(erro["mensagem"], 422, erro["campos"])

        proibidos = sorted(set(dados) - CADASTRAVEIS)
        if proibidos:
            raise ErroObra("Envie somente os campos do cadastro da obra", 422, proibidos)

        documento = deepcopy(dados)
        registro = self.relogio.agora()
        # BSON armazena milissegundos; POST e consultas devem devolver o mesmo instante.
        registro = registro.replace(microsecond=(registro.microsecond // 1000) * 1000)
        documento.update(
            _id=ObjectId(),
            autor=autor,
            data_registro=registro,
            estado="planejada",
        )
        self.repositorio.salvar_obra(documento)
        return self.obra_para_dict(documento)

    def buscar_obra(self, identifier):
        try:
            obra_id = ObjectId(identifier)
        except (InvalidId, TypeError):
            raise ErroObra("ID da obra inválido", 400, ["id"])

        documento = self.repositorio.buscar_obra_por_id(obra_id)
        if documento is None:
            raise ErroObra("Obra não encontrada", 404, ["id"])
        return self.obra_para_dict(documento)

    def listar_obras(self, parametros):
        permitidos = {"nome", "cliente", "estado", "alerta", "registroDe", "registroAte", "entregaDe", "entregaAte"}
        desconhecidos = sorted(set(parametros) - permitidos)
        if desconhecidos:
            raise ErroObra("Filtros desconhecidos", 422, desconhecidos)
        if hasattr(parametros, "getlist"):
            repetidos = sorted(campo for campo in parametros if len(parametros.getlist(campo)) != 1)
            if repetidos:
                raise ErroObra("Não repita filtros", 422, repetidos)
        if "alerta" in parametros and parametros["alerta"] != "atrasada":
            raise ErroObra("O único alerta permitido é 'atrasada'", 422, ["alerta"])
        datas = {}
        for campo in ("registroDe", "registroAte", "entregaDe", "entregaAte"):
            if campo not in parametros:
                continue
            valor = parametros[campo]
            try:
                data = date.fromisoformat(valor)
                if data.isoformat() != valor:
                    raise ValueError
            except (ValueError, TypeError):
                raise ErroObra("Informe uma data válida no formato AAAA-MM-DD", 422, [campo])
            datas[campo] = data
        for inicio, fim in (("registroDe", "registroAte"), ("entregaDe", "entregaAte")):
            if inicio in datas and fim in datas and datas[fim] < datas[inicio]:
                raise ErroObra("O fim do filtro não pode ser anterior ao início", 422, [fim])

        filtro = {}

        for campo in ("nome", "cliente"):
            if campo not in parametros:
                continue

            valor = parametros[campo].strip()

            if not valor:
                continue

            filtro[campo] = {
                "$regex": re.escape(valor),
                "$options": "i"
            }

        if "estado" in parametros:
            estado = parametros["estado"]
            if estado not in {"planejada", "em andamento", "concluída", "suspensa"}:
                raise ErroObra("Estado da obra inválido", 422, ["estado"])
            filtro["estado"] = estado
        registro = {}
        if "registroDe" in datas:
            registro["$gte"] = datetime.combine(datas["registroDe"], time.min, tzinfo=timezone.utc)
        if "registroAte" in datas:
            # Inclui todo o último dia sem depender da precisão do armazenamento.
            fim = datas["registroAte"]
            if fim == date.max:
                registro["$lte"] = datetime.max.replace(tzinfo=timezone.utc)
            else:
                registro["$lt"] = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if registro:
            filtro["data_registro"] = registro
        entrega = {}
        for campo, operador in (("entregaDe", "$gte"), ("entregaAte", "$lte")):
            if campo in datas:
                entrega[operador] = datas[campo].isoformat()
        if entrega:
            filtro["$or"] = [
                {"entrega.modalidade": "data_exata", "entrega.data": entrega},
                {"entrega.modalidade": "intervalo_estimado", "entrega.fim": entrega},
            ]
        obras = [self.obra_para_dict(documento) for documento in self.repositorio.consultar_obras(filtro)]
        if "alerta" in parametros:
            obras = [obra for obra in obras if parametros["alerta"] in obra["alertas"]]
        return obras

    def listar_marcos(self, identifier):
        # Compatibilidade para consumidores do serviço anterior à migração da rota.
        from app.marcos.service import ErroMarco, listar_marcos as consultar_marcos

        try:
            return consultar_marcos(identifier)
        except ErroMarco as erro:
            raise ErroObra(str(erro), erro.status, erro.campos) from erro

    def editar_descricao(self, identifier, dados):
        try:
            obra_id = ObjectId(identifier)
        except (InvalidId, TypeError):
            raise ErroObra("ID da obra inválido", 400, ["id"])

        if not isinstance(dados, dict) or not dados:
            raise ErroObra("Envie um objeto JSON com campos para corrigir", 422, ["corpo"])

        proibidos = sorted(set(dados) - EDITAVEIS)
        if proibidos:
            raise ErroObra(
                "Esta rota aceita apenas nome, descrição, endereço e cliente. "
                "Prazo e conclusão exigem o fluxo de mudança com motivo e histórico.",
                422,
                proibidos,
            )

        invalidos = [
            campo
            for campo, valor in dados.items()
            if not isinstance(valor, str) or not valor.strip()
        ]
        if invalidos:
            raise ErroObra("Os campos enviados devem ser textos não vazios", 422, invalidos)

        documento = self.repositorio.atualizar_descricao(obra_id, dados)
        if documento is None:
            raise ErroObra("Obra não encontrada", 404, ["id"])
        return documento

    def calcular_alertas(self, documento):
        return Obra.de_documento(documento).alertas(self.relogio.agora().date())

    def alterar_estado(self, identifier, dados, autor, *, versao_esperada=None):
        try:
            obra_id = ObjectId(identifier)
        except (InvalidId, TypeError):
            raise ErroObra("ID da obra inválido", 400, ["id"]) from None
        if not isinstance(dados, dict) or set(dados) != {"estado", "motivo"}:
            campos = sorted(set(dados) - {"estado", "motivo"}) if isinstance(dados, dict) else ["corpo"]
            raise ErroObra("Envie somente estado e motivo", 422, campos or ["estado", "motivo"])
        documento = self.repositorio.buscar_obra_por_id(obra_id)
        if documento is None:
            raise ErroObra("Obra não encontrada", 404, ["id"])
        if versao_esperada is not None and documento.get("versao", 0) != versao_esperada:
            raise ErroObra("A obra foi alterada; consulte novamente", 409, ["versao"])
        try:
            obra = Obra.de_documento(documento)
            mudanca = obra.alterar_estado(dados["estado"], dados["motivo"], autor, self.relogio.agora())
        except ErroDominio as erro:
            raise ErroObra(str(erro), 422, erro.campos) from erro
        if mudanca is None:
            return self.obra_para_dict(documento)
        salvo = self.repositorio.salvar_estado_com_historico(documento, mudanca.para_documento())
        if salvo is None:
            raise ErroObra("A obra foi alterada por outra requisição; consulte novamente", 409, ["estado"])
        return self.obra_para_dict(salvo)


_servico = ServicoObras()

# Fachada para consumidores anteriores à refatoração.
obra_para_dict = _servico.obra_para_dict
criar_obra = _servico.criar_obra
buscar_obra = _servico.buscar_obra
listar_obras = _servico.listar_obras
listar_marcos = _servico.listar_marcos
editar_descricao = _servico.editar_descricao
calcular_alertas = _servico.calcular_alertas
