"""Perspectiva opcional da obra: original privado, vínculo atômico e limpeza durável."""

from dataclasses import replace
from io import BytesIO
from bson import ObjectId
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError, WriteError
from werkzeug.exceptions import RequestEntityTooLarge

import db
from app.auth.permissions import sessao_obrigatoria
from app.avancos import repository as uploads
from app.avancos.midias import ErroMidia, ResultadoPersistenciaIndeterminado, ServicoMidias
from app.avancos.operacoes import OperacaoUpload
from app.avancos.rascunhos_repository import RepositorioRascunhos
from app.config import ConfiguracaoArmazenamento
from app.dominio.comum import Relogio
from app.integracoes.armazenamento import ArmazenamentoCloudinary, ErroArmazenamento, ErroLimpeza
from . import repository
from .service import ErroObra, ServicoObras


def representar_imagem(obra_id, imagem):
    return {"id": str(imagem["_id"]), "nome": imagem["nome"], "mime": imagem["mime"],
            "tamanho": imagem["tamanho"],
            "conteudo": f"/obras/{obra_id}/imagem-projeto/{imagem['_id']}/conteudo"}


def _obra(obra_id):
    if not ObjectId.is_valid(obra_id):
        raise ErroObra("ID da obra inválido", 400, ["id"])
    documento = repository.buscar_obra_por_id(ObjectId(obra_id))
    if documento is None or (documento.get("autor") and str(documento["autor"]) != get_jwt_identity()):
        raise ErroObra("Obra não encontrada", 404, ["id"])
    return documento


def _config():
    config = ConfiguracaoArmazenamento.do_ambiente()
    # Este fluxo só recebe fotos: também limita a leitura antes da decodificação.
    return replace(config, limite_video=config.limite_foto, limite_documento=config.limite_foto)


class ServicoImagem(ServicoMidias):
    def executar_com_midias(self, arquivos, salvar, **options):
        reservar = options.pop("antes_envio", None)

        def validar(validados):
            if len(validados) != 1 or validados[0].tipo != "foto":
                raise ErroMidia("A imagem do projeto deve ser JPEG ou PNG", campos=["imagem_projeto"])
            if reservar:
                reservar(validados)
        return super().executar_com_midias(arquivos, salvar, antes_envio=validar, **options)


def _concluir(operacao):
    try:
        db.banco_dados["tbl_uploads_pendentes"].update_one(
            {"_id": operacao.id}, {"$set": {"estado": "concluida"}})
    except PyMongoError:
        current_app.logger.warning("Diário de imagem mantido para reconciliação")


def _persistir(gravar, referencias):
    try:
        return gravar()
    except WriteError:
        raise  # Rejeição confirmada: ServicoMidias compensa o upload.
    except PyMongoError:
        raise ResultadoPersistenciaIndeterminado(referencias) from None


def criar_com_imagem(dados, arquivo, autor):
    servico = ServicoObras()
    documento = servico.preparar_cadastro(dados, autor)
    operacao = OperacaoUpload(uploads, documento["_id"], "imagem_projeto", campo_vinculo="obra_id")

    def salvar(midias):
        documento["imagem_projeto"] = {**midias[0], "_id": ObjectId()}
        _persistir(lambda: repository.salvar_obra(documento), [midias[0]["referencia_externa"]])
        _concluir(operacao)
        return servico.obra_para_dict(documento)
    return operacao.executar(ServicoImagem(config=_config()), [arquivo], salvar)


def _esperada(documento, esperada):
    atual = documento.get("imagem_projeto")
    if not isinstance(esperada, str) or esperada != (str(atual["_id"]) if atual else ""):
        raise ErroObra("A imagem mudou. Consulte a obra antes de alterar novamente", 409, ["imagem_atual"])
    return {"_id": documento["_id"], "imagem_projeto._id": atual["_id"] if atual else {"$exists": False}}


def _agendar(documento):
    imagem = documento.get("imagem_projeto")
    if imagem:
        db.banco_dados["tbl_limpezas_midias"].update_one(
            {"_id": imagem["_id"]},
            {"$setOnInsert": {"midia": imagem, "obra_id": documento["_id"], "criada_em": Relogio().agora()}},
            upsert=True)


def _limpar(obra_id):
    try:
        return _executar_limpeza(obra_id)
    except PyMongoError:
        return True


def _executar_limpeza(obra_id):
    # A tarefa é gravada antes de trocar o vínculo. Se a escrita falhar ou
    # disputar com outra operação, o arquivo ainda em uso nunca é apagado.
    pendente = False
    for tarefa in db.banco_dados["tbl_limpezas_midias"].find({"obra_id": obra_id}):
        try:
            midia = tarefa["midia"]
            if RepositorioRascunhos().referencia_em_uso(midia["referencia_externa"], ids_midias=[midia["_id"]]):
                pendente = True
                continue
            ArmazenamentoCloudinary().remover(midia["referencia_externa"])
            db.banco_dados["tbl_limpezas_midias"].delete_one({"_id": tarefa["_id"]})
        except (ErroArmazenamento, PyMongoError):
            pendente = True
    return pendente


def substituir(obra_id, arquivo, esperada):
    anterior = _obra(obra_id)
    filtro = _esperada(anterior, esperada)
    operacao = OperacaoUpload(uploads, anterior["_id"], "imagem_projeto", campo_vinculo="obra_id")

    def salvar(midias):
        _agendar(anterior)
        nova = {**midias[0], "_id": ObjectId()}
        atualizado = _persistir(lambda: db.banco_dados["tbl_obras"].find_one_and_update(
            filtro, {"$set": {"imagem_projeto": nova}}, return_document=ReturnDocument.AFTER),
            [nova["referencia_externa"]])
        if atualizado is None:
            raise ErroObra("A obra ou sua imagem mudou. Consulte novamente", 409, ["imagem_atual"])
        _concluir(operacao)
        return nova
    nova = operacao.executar(ServicoImagem(config=_config()), [arquivo], salvar)
    return {"imagem_projeto": representar_imagem(anterior["_id"], nova), "limpeza_pendente": _limpar(anterior["_id"])}


def remover(obra_id, esperada):
    anterior = _obra(obra_id)
    if not anterior.get("imagem_projeto"):
        return {"imagem_projeto": None, "limpeza_pendente": _limpar(anterior["_id"])}
    filtro = _esperada(anterior, esperada)
    _agendar(anterior)
    atualizado = _persistir(lambda: db.banco_dados["tbl_obras"].find_one_and_update(
        filtro, {"$unset": {"imagem_projeto": ""}}, return_document=ReturnDocument.AFTER), [])
    if atualizado is None:
        raise ErroObra("A obra ou sua imagem mudou. Consulte novamente", 409, ["imagem_atual"])
    return {"imagem_projeto": None, "limpeza_pendente": _limpar(anterior["_id"])}


def arquivos_da_obra(obra_id, *, session=None):
    documento = db.banco_dados["tbl_obras"].find_one({"_id": obra_id}, session=session)
    midias = [documento["imagem_projeto"]] if documento and documento.get("imagem_projeto") else []
    midias += [tarefa["midia"] for tarefa in db.banco_dados["tbl_limpezas_midias"].find({"obra_id": obra_id}, session=session)]
    return list({str(midia["_id"]): midia for midia in midias}.values())


imagens_bp = Blueprint("imagens_projeto", __name__)


@imagens_bp.before_request
@sessao_obrigatoria
def exigir_sessao():
    pass


@imagens_bp.after_request
def proteger(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


def erro_imagem(erro):
    if isinstance(erro, ResultadoPersistenciaIndeterminado):
        return jsonify(mensagem="Não foi possível confirmar a gravação. Consulte a obra antes de repetir.", codigo="RESULTADO_INDETERMINADO"), 503
    if isinstance(erro, RequestEntityTooLarge):
        return jsonify(mensagem="A imagem excede o limite permitido", campos=["imagem_projeto"]), 413
    if isinstance(erro, PyMongoError):
        return jsonify(mensagem="Não foi possível salvar ou consultar a imagem do projeto"), 500
    if isinstance(erro, ValueError) and not isinstance(erro, ErroMidia):
        return jsonify(mensagem="A configuração de armazenamento está indisponível"), 503
    campos = ["imagem_projeto"] if isinstance(erro, ErroMidia) else getattr(erro, "campos", ["imagem_projeto"])
    return jsonify(mensagem=str(erro), campos=campos), getattr(erro, "status", 503)


for classe in (ErroObra, ErroMidia, ErroArmazenamento, ResultadoPersistenciaIndeterminado, PyMongoError, RequestEntityTooLarge, ValueError):
    imagens_bp.register_error_handler(classe, erro_imagem)


def ler_arquivo(*, cadastro=False):
    if request.mimetype != "multipart/form-data":
        raise ErroObra("Envie a imagem como multipart/form-data", 415, ["imagem_projeto"])
    request.environ["pe03.max_content_length"] = _config().limite_foto + 64 * 1024
    campos = {"cadastro"} if cadastro else {"imagem_atual"}
    if set(request.form) != campos or any(len(request.form.getlist(campo)) != 1 for campo in campos):
        raise ErroObra("Envie somente os campos esperados, sem repetições", 422, sorted(campos))
    if set(request.files) != {"imagem_projeto"} or len(request.files.getlist("imagem_projeto")) != 1:
        raise ErroObra("Envie uma única imagem do projeto", 422, ["imagem_projeto"])
    return request.files["imagem_projeto"]


@imagens_bp.put("/obras/<string:obra_id>/imagem-projeto")
def atualizar_imagem(obra_id):
    _obra(obra_id)  # Validar contexto antes de receber o arquivo.
    arquivo = ler_arquivo()
    return jsonify(substituir(obra_id, arquivo, request.form["imagem_atual"]))


@imagens_bp.delete("/obras/<string:obra_id>/imagem-projeto")
def excluir_imagem(obra_id):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or set(dados) != {"imagem_atual"} or not isinstance(dados["imagem_atual"], str):
        raise ErroObra("Informe a imagem atual para removê-la", 422, ["imagem_atual"])
    return jsonify(remover(obra_id, dados["imagem_atual"]))


@imagens_bp.get("/obras/<string:obra_id>/imagem-projeto/<string:imagem_id>/conteudo")
def obter_imagem(obra_id, imagem_id):
    imagem = _obra(obra_id).get("imagem_projeto")
    if not imagem or str(imagem["_id"]) != imagem_id:
        raise ErroObra("Imagem do projeto não encontrada", 404, ["imagem_projeto"])
    if imagem.get("mime") not in {"image/jpeg", "image/png"}:
        raise ErroObra("Formato da imagem armazenada inválido", 422, ["imagem_projeto"])
    conteudo = ArmazenamentoCloudinary().obter_conteudo(imagem["referencia_externa"], imagem["tamanho"])
    return send_file(BytesIO(conteudo), mimetype=imagem["mime"], download_name=imagem["nome"], as_attachment=False)
