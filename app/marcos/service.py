"""Regras de negócio de marcos e suas dependências."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.obras import repository as obras_repository

from . import repository
from .dependencias import cria_ciclo
from .validacoes import validar_alteracao_estado, validar_marco
from app.dominio.comum import ErroDominio, Relogio
from app.dominio.marcos import Marco, DependenciasPendentes

MAX_TENTATIVAS_DEPENDENCIA = 5


class ErroMarco(Exception):
    def __init__(self, mensagem, status, campos=(), detalhes=None):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.detalhes = detalhes or {}

class ServicoMarcos:
    def __init__(self, repositorio=None, relogio=None, repositorio_obras=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.relogio = relogio if relogio is not None else Relogio()
        self.repositorio_obras = repositorio_obras if repositorio_obras is not None else obras_repository

    def criar_marco(self, obra_id, dados):
        object_id_obra = self._identificar_id(obra_id, "obra_id")
        erro = validar_marco(dados)
        if erro:
            mensagem, campos = erro
            raise ErroMarco(mensagem, 422, campos)
        if not self.repositorio.obra_existe(object_id_obra):
            raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

        documento = {
            "obra_id": object_id_obra,
            "nome": dados["nome"].strip(),
            "descricao": dados["descricao"].strip(),
            "inicio_previsto": dados["inicio_previsto"],
            "fim_previsto": dados["fim_previsto"],
            "estado": "a iniciar",
        }
        identifier = self.repositorio.inserir_marco(documento)
        return {
            "id": str(identifier),
            "obra_id": str(object_id_obra),
            **{
                key: documento[key]
                for key in (
                    "nome", "descricao", "inicio_previsto", "fim_previsto", "estado"
                )
            },
        }

    def alterar_estado_marco(self, marco_id, dados, autor):
        object_id = self._identificar_id(marco_id, "marco_id")
        erro = validar_alteracao_estado(dados)
        if erro:
            mensagem, campos = erro
            raise ErroMarco(mensagem, 422, campos)

        marco = self.repositorio.buscar_marco(object_id)
        if not marco:
            raise ErroMarco("Marco não encontrado", 404, ["marco_id"])

        novo_estado = dados["estado"]
        anterior = marco.get("estado", "a iniciar")
        if anterior == novo_estado:
            return {"id": str(object_id), "estado": anterior}

        try:
            pendentes = (
                self.repositorio.dependencias_pendentes(marco)
                if novo_estado == "concluído"
                else []
            )
        except repository.DependenciaInconsistente as erro:
            raise ErroMarco(
                "As dependências do marco precisam ser corrigidas",
                409,
                detalhes={"codigo": "DEPENDENCIA_INCONSISTENTE"},
            ) from erro

        entidade = Marco.de_documento(marco)
        try:
            mudanca = entidade.alterar_estado(
                novo_estado, dados["motivo"], autor, self.relogio.agora(),
                pendentes=pendentes, confirmar=dados.get("confirmar_dependencias") is True,
            )
        except DependenciasPendentes as erro:
            raise ErroMarco(str(erro), 409, [], {
                "codigo": "DEPENDENCIAS_PENDENTES", "dependencias": erro.dependencias
            }) from erro
        except ErroDominio as erro:
            raise ErroMarco(str(erro), 422, erro.campos) from erro
        evento = {
            **mudanca.para_documento(),
            "estado_anterior": anterior,
            "estado_novo": novo_estado,
            "confirmou_dependencias_pendentes": bool(
                pendentes and dados.get("confirmar_dependencias") is True
            ),
            "dependencias_pendentes": pendentes,
        }
        try:
            self.repositorio.salvar_estado_com_historico(object_id, anterior, novo_estado, evento)
        except repository.EstadoMarcoAlterado:
            raise ErroMarco(
                "O estado do marco foi alterado por outra requisição; atualize os dados e tente novamente",
                409,
                [],
                {"codigo": "MARCO_ALTERADO_CONCORRENTEMENTE"},
            )
        return {"id": str(object_id), "estado": novo_estado}

    def buscar_marco(self, obra_id, marco_id):
        object_id_obra = self._identificar_id(obra_id, "obra_id")
        object_id_marco = self._identificar_id(marco_id, "marco_id")
        if not self.repositorio.obra_existe(object_id_obra):
            raise ErroMarco("Obra não encontrada", 404, ["obra_id"])

        documento = self.repositorio.buscar_marco_por_id(object_id_marco)
        if documento is None or documento.get("obra_id") != object_id_obra:
            raise ErroMarco("Marco não encontrado", 404, ["marco_id"])
        return self._marco_para_dict(documento)

    def listar_marcos(self, obra_id):
        # Mantém os campos e erros da listagem originalmente publicada em obras.
        try:
            object_id_obra = self._identificar_id(obra_id, "obra_id")
        except ErroMarco:
            raise ErroMarco("ID da obra inválido", 400, ["id"]) from None
        if not self.repositorio.obra_existe(object_id_obra):
            raise ErroMarco("Obra não encontrada", 404, ["id"])

        return [
            {campo: valor for campo, valor in self._marco_para_dict(documento).items()
             if campo != "obra_id"}
            for documento in self.repositorio_obras.consultar_marcos(object_id_obra)
        ]

    def _marco_para_dict(self, documento):
        marco = {
            campo: self._serializar_object_ids(valor)
            for campo, valor in documento.items() if campo != "_id"
        }
        marco["id"] = str(documento["_id"])
        return marco

    def _serializar_object_ids(self, valor):
        if isinstance(valor, ObjectId):
            return str(valor)
        if isinstance(valor, dict):
            return {campo: self._serializar_object_ids(item) for campo, item in valor.items()}
        if isinstance(valor, list):
            return [self._serializar_object_ids(item) for item in valor]
        return valor

    def listar_dependencias(self, marco_id):
        object_id = self._identificar_id(marco_id, "marco_id")
        marco, obra = self._obter_marco_e_obra(object_id)
        dependencias = []
        for vinculo in obra.get("dependencias_marcos", []):
            if vinculo["marco_id"] != object_id:
                continue
            destino = self.repositorio.buscar_marco_por_id(vinculo["depende_de_id"])
            if destino is None:
                continue
            dependencias.append(self._serializar_dependencia(vinculo, marco, destino))
        dependencias.sort(key=lambda item: item["id"])
        return dependencias

    def criar_dependencia(self, marco_id, dados):
        object_id = self._identificar_id(marco_id, "marco_id")
        if not isinstance(dados, dict) or set(dados) != {"depende_de_id"}:
            raise ErroMarco("Envie somente o campo 'depende_de_id'", 422, ["depende_de_id"])
        destino_id = self._identificar_id(dados["depende_de_id"], "depende_de_id")

        marco, obra = self._obter_marco_e_obra(object_id)
        destino = self.repositorio.buscar_marco_por_id(destino_id)
        if destino is None:
            raise ErroMarco("Marco de dependência não encontrado", 404, ["depende_de_id"])
        if destino.get("obra_id") != marco.get("obra_id"):
            raise ErroMarco("A dependência deve pertencer à mesma obra", 409, ["depende_de_id"])

        for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
            vinculos = list(obra.get("dependencias_marcos", []))
            if any(
                item["marco_id"] == object_id and item["depende_de_id"] == destino_id
                for item in vinculos
            ):
                raise ErroMarco("Esta dependência já existe", 409, ["depende_de_id"])
            if cria_ciclo(vinculos, object_id, destino_id):
                raise ErroMarco("A dependência formaria um ciclo", 409, ["depende_de_id"])

            vinculo = {
                "_id": ObjectId(),
                "marco_id": object_id,
                "depende_de_id": destino_id,
            }
            novos_vinculos = vinculos + [vinculo]
            if self.repositorio.substituir_dependencias(obra, novos_vinculos):
                return self._serializar_dependencia(vinculo, marco, destino)

            marco, obra = self._obter_marco_e_obra(object_id)
            if self.repositorio.buscar_marco_por_id(destino_id) is None:
                raise ErroMarco("Marco de dependência não encontrado", 404, ["depende_de_id"])

        raise ErroMarco("As dependências foram alteradas por outra requisição; tente novamente", 409)

    def remover_dependencia(self, marco_id, dependencia_id):
        object_id = self._identificar_id(marco_id, "marco_id")
        vinculo_id = self._identificar_id(dependencia_id, "dependencia_id")
        _, obra = self._obter_marco_e_obra(object_id)

        for _ in range(MAX_TENTATIVAS_DEPENDENCIA):
            vinculos = list(obra.get("dependencias_marcos", []))
            novos_vinculos = [
                item for item in vinculos
                if not (item["_id"] == vinculo_id and item["marco_id"] == object_id)
            ]
            if len(novos_vinculos) == len(vinculos):
                raise ErroMarco("Dependência não encontrada", 404, ["dependencia_id"])
            if self.repositorio.substituir_dependencias(obra, novos_vinculos):
                return
            _, obra = self._obter_marco_e_obra(object_id)

        raise ErroMarco("As dependências foram alteradas por outra requisição; tente novamente", 409)

    def _identificar_id(self, value, campo):
        if not isinstance(value, (str, ObjectId)) or (isinstance(value, str) and not value.strip()):
            status = 422 if campo == "depende_de_id" else 400
            raise ErroMarco(f"ID inválido: {campo}", status, [campo])
        try:
            return value if isinstance(value, ObjectId) else ObjectId(value)
        except (InvalidId, TypeError):
            raise ErroMarco(f"ID inválido: {campo}", 400, [campo])

    def _obter_marco_e_obra(self, marco_id):
        marco = self.repositorio.buscar_marco_por_id(marco_id)
        if marco is None:
            raise ErroMarco("Marco não encontrado", 404, ["marco_id"])
        obra = self.repositorio.buscar_obra_por_id(marco["obra_id"])
        if obra is None:
            raise ErroMarco("Obra não encontrada", 404, ["obra_id"])
        return marco, obra

    def _serializar_dependencia(self, vinculo, origem, destino):
        return {
            "id": str(vinculo["_id"]),
            "marco_id": str(vinculo["marco_id"]),
            "depende_de_id": str(vinculo["depende_de_id"]),
            "marco_nome": origem.get("nome", "Marco"),
            "depende_de_nome": destino.get("nome", "Marco"),
        }


_servico = ServicoMarcos()

# Fachada para consumidores anteriores à refatoração.
criar_marco = _servico.criar_marco
alterar_estado_marco = _servico.alterar_estado_marco
buscar_marco = _servico.buscar_marco
listar_marcos = _servico.listar_marcos
_marco_para_dict = _servico._marco_para_dict
_serializar_object_ids = _servico._serializar_object_ids
listar_dependencias = _servico.listar_dependencias
criar_dependencia = _servico.criar_dependencia
remover_dependencia = _servico.remover_dependencia
_identificar_id = _servico._identificar_id
_obter_marco_e_obra = _servico._obter_marco_e_obra
_serializar_dependencia = _servico._serializar_dependencia
