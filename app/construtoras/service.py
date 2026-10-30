"""Cadastro e autenticação sem dependência de request ou response do Flask."""

from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId

from app.dominio.comum import Relogio
from app.dominio.pessoas import Construtora
from validacoes import normalizar_dados_construtora, validar_dados_construtora, validar_dados_login
from .repository import RepositorioConstrutoras


class ErroConstrutora(Exception):
    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.status = status


class ServicoSessoes:
    def __init__(self, criar_acesso, criar_renovacao):
        self.criar_acesso = criar_acesso
        self.criar_renovacao = criar_renovacao

    def iniciar(self, construtora_id):
        claims = {"tipo": "construtora", "sessao_id": str(uuid4())}
        opcoes = {"identity": str(construtora_id), "additional_claims": claims}
        return self.criar_acesso(**opcoes), self.criar_renovacao(**opcoes)

    def renovar(self, construtora_id, sessao_id):
        return self.criar_acesso(identity=str(construtora_id), additional_claims={
            "tipo": "construtora", "sessao_id": sessao_id,
        })


class ServicoConstrutoras:
    def __init__(self, senhas, sessoes, repositorio=None, relogio=None):
        self.senhas, self.sessoes = senhas, sessoes
        self.repositorio = repositorio if repositorio is not None else RepositorioConstrutoras()
        self.relogio = relogio if relogio is not None else Relogio()

    def _validar(self, dados, *, atualizacao=False):
        erro = validar_dados_construtora(dados, atualizacao=atualizacao)
        if erro:
            raise ErroConstrutora(erro[0]["erro"], erro[1])
        campos = normalizar_dados_construtora(dados)
        if "senha" in dados:
            campos["senha_hash"] = self.senhas.generate_password_hash(dados["senha"]).decode("utf-8")
        return campos

    def cadastrar(self, dados):
        documento = self._validar(dados)
        documento.update(ativo=True, data_cadastro=self.relogio.agora())
        documento["_id"] = self.repositorio.inserir(documento)
        return self._resposta_autenticada(documento, "Construtora criada com sucesso")

    def _identificar(self, identificador):
        try:
            return ObjectId(identificador)
        except (InvalidId, TypeError):
            raise ErroConstrutora("Não foi possível identificar a construtora", 400) from None

    def _autorizar(self, identificador, autor, perfil):
        oid = self._identificar(identificador)
        if perfil != "construtora" or str(oid) != autor:
            raise ErroConstrutora("Você só pode alterar sua própria conta", 403)
        return oid

    def atualizar(self, identificador, dados, autor, perfil):
        oid = self._autorizar(identificador, autor, perfil)
        campos = self._validar(dados, atualizacao=True)
        if not self.repositorio.atualizar(oid, campos):
            raise ErroConstrutora("Construtora não encontrada", 404)
        return {"mensagem": "Construtora atualizada com sucesso"}

    def excluir(self, identificador, autor, perfil):
        oid = self._autorizar(identificador, autor, perfil)
        if not self.repositorio.excluir(oid):
            raise ErroConstrutora("Conta da construtora não encontrada", 404)
        return {"mensagem": "Construtora excluída com sucesso"}

    def entrar(self, dados):
        erro = validar_dados_login(dados)
        if erro:
            raise ErroConstrutora(erro[0]["erro"], erro[1])
        documento = self.repositorio.por_email(dados["email"].strip().lower())
        if documento is None or not self.senhas.check_password_hash(documento["senha_hash"], dados["senha"]):
            raise ErroConstrutora("Email ou senha incorretos", 401)
        if not Construtora.de_documento(documento).ativo:
            raise ErroConstrutora("Sua conta está desativada", 403)
        return self._resposta_autenticada(documento, "Login realizado com sucesso")

    def _resposta_autenticada(self, documento, mensagem):
        conta = Construtora.de_documento(documento)
        acesso, renovacao = self.sessoes.iniciar(conta.id)
        return {"mensagem": mensagem, "construtora": conta.para_dict(),
                "access_token": acesso, "refresh_token": renovacao}

    def _exigir_sessao(self, claims):
        if claims.get("tipo") != "construtora":
            raise ErroConstrutora("Você não tem permissão para realizar esta ação", 403)
        sessao_id = claims.get("sessao_id")
        if not isinstance(sessao_id, str) or not sessao_id:
            raise ErroConstrutora("Entre novamente na sua conta", 401)
        return sessao_id

    def renovar(self, identidade, claims):
        sessao_id = self._exigir_sessao(claims)
        try:
            if not isinstance(identidade, str):
                raise ValueError
            identificador = ObjectId(identidade)
        except (InvalidId, TypeError, ValueError):
            raise ErroConstrutora("Entre novamente na sua conta", 401) from None
        documento = self.repositorio.buscar(identificador)
        if documento is None:
            raise ErroConstrutora("Conta não encontrada", 401)
        if not Construtora.de_documento(documento).ativo:
            raise ErroConstrutora("Sua conta está desativada", 403)
        return {"access_token": self.sessoes.renovar(identificador, sessao_id)}

    def sair(self, identidade, claims):
        sessao_id = self._exigir_sessao(claims)
        self.repositorio.encerrar_sessao(sessao_id, identidade, self.relogio.agora())
        return {"mensagem": "Você saiu da conta com sucesso"}
