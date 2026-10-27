import re
from bson import ObjectId
from bson.errors import InvalidId

CAMPOS_TEXTO = ("nome", "email", "telefone", "cargo")
CAMPOS_ATUALIZAVEIS = set(CAMPOS_TEXTO) | {"obras"}
CAMPOS_CONSTRUTORA = {"nome", "email", "telefone", "senha"}

PADRAO_EMAIL = r"[^@\s]+@[^@\s]+\.[^@\s]+"
PADRAO_TELEFONE = r"[0-9()\s-]+"


def validar_dados_trabalhador(dados, atualizacao=False):
    """
    Cadastro: exige todos os campos de texto.
    Atualização: valida somente os campos enviados.
    """
    if not isinstance(dados, dict):
        return {"erro": "Envie um objeto JSON válido"}, 422

    if atualizacao:
        if not dados:
            return {
                "erro": "Envie pelo menos um campo para atualizar"
            }, 422

        campos_desconhecidos = set(dados) - CAMPOS_ATUALIZAVEIS

        if campos_desconhecidos:
            return {
                "erro": (
                    "Campos permitidos: nome, email, "
                    "telefone, cargo e obras"
                )
            }, 422

    # No cadastro, todos os campos de texto são obrigatórios.
    # Na atualização, os campos ausentes são ignorados. Utilizando o patch ao invés do put
    for campo in CAMPOS_TEXTO:
        if atualizacao and campo not in dados:
            continue

        valor = dados.get(campo)

        if not isinstance(valor, str) or not valor.strip():
            return {
                "erro": (
                    f"O campo '{campo}' deve ser um texto preenchido"
                )
            }, 422

    # Verifica o formato básico do email.
    if "email" in dados:
        email = dados["email"].strip()

        if not re.fullmatch(PADRAO_EMAIL, email):
            return {
                "erro": "Informe um email em formato válido"
            }, 422

    # Aceita telefone com DDD, sem o código do país.
    if "telefone" in dados:
        telefone = dados["telefone"].strip()

        if not re.fullmatch(PADRAO_TELEFONE, telefone):
            return {
                "erro": (
                    "O telefone deve conter apenas números, "
                    "espaços, parênteses ou hífen"
                )
            }, 422

        numeros = re.sub(r"[^0-9]", "", telefone)

        if len(numeros) not in (10, 11):
            return {
                "erro": (
                    "Informe um telefone com DDD, "
                    "com 10 ou 11 dígitos, sem +55"
                )
            }, 422

    # No cadastro, a obra vem da URL.
    # Na atualização, a lista pode vir no JSON.
    if atualizacao and "obras" in dados:
        obras = dados["obras"]

        if not isinstance(obras, list):
            return {
                "erro": "Obras deve ser uma lista de IDs MongoDB"
            }, 422

        for codigo_obra in obras:
            if not isinstance(codigo_obra, str):
                return {
                    "erro": "Cada ID de obra deve ser um texto"
                }, 422

            try:
                ObjectId(codigo_obra)
            except (InvalidId, TypeError):
                return {
                    "erro": "A lista contém um ID de obra inválido"
                }, 422


def normalizar_dados_trabalhador(dados, incluir_obras=False):
    """
    Prepara dados já validados para armazenamento.
    Retorna um novo dicionário com os campos aceitos.
    """
    dados_normalizados = {
        campo: dados[campo].strip()
        for campo in CAMPOS_TEXTO
        if campo in dados
    }

    # Armazena o telefone somente com números.
    if "telefone" in dados_normalizados:
        dados_normalizados["telefone"] = re.sub(
            r"[^0-9]",
            "",
            dados_normalizados["telefone"]
        )

    # Padroniza a escrita do cargo.
    if "cargo" in dados_normalizados:
        dados_normalizados["cargo"] = (
            dados_normalizados["cargo"].lower()
        )

    if incluir_obras and "obras" in dados:
        # Padroniza IDs e remove repetições.
        dados_normalizados["obras"] = list(dict.fromkeys(
            str(ObjectId(codigo_obra))
            for codigo_obra in dados["obras"]
        ))

    return dados_normalizados


def validar_dados_construtora(dados, atualizacao=False):
    if not isinstance(dados, dict) or not dados:
        return {
            "erro": "Preencha os dados da construtora para continuar."
        }, 422

    if set(dados) - CAMPOS_CONSTRUTORA:
        return {
            "erro": (
                "Não foi possível processar alguns dados enviados. "
                "Atualize a página e tente novamente."
            )
        }, 422

    mensagens_campos = {
        "nome": "Informe o nome da construtora.",
        "email": "Informe o e-mail da construtora.",
        "telefone": "Informe um telefone para contato.",
        "senha": "Crie uma senha para sua conta."
    }

    if not atualizacao:
        for campo in ("nome", "email", "senha"):
            if campo not in dados:
                return {"erro": mensagens_campos[campo]}, 422

    for campo, valor in dados.items():
        if not isinstance(valor, str) or not valor.strip():
            return {"erro": mensagens_campos[campo]}, 422

    if "email" in dados:
        email = dados["email"].strip()

        if not re.fullmatch(PADRAO_EMAIL, email):
            return {
                "erro": (
                    "Confira o e-mail informado. "
                    "Use um endereço como contato@empresa.com."
                )
            }, 422

    if "telefone" in dados:
        telefone = dados["telefone"].strip()

        if not re.fullmatch(PADRAO_TELEFONE, telefone):
            return {
                "erro": (
                    "Confira o telefone informado. "
                    "Use um número como (11) 99999-9999."
                )
            }, 422

        numeros = re.sub(r"[^0-9]", "", telefone)

        if len(numeros) not in (10, 11):
            return {
                "erro": (
                    "Informe o telefone com DDD, "
                    "sem o código do país (+55)."
                )
            }, 422

    if "senha" in dados:
        senha = dados["senha"]

        if len(senha) < 12:
            return {
                "erro": "Escolha uma senha com pelo menos 12 caracteres."
            }, 422

        if len(senha.encode("utf-8")) > 72:
            return {
                "erro": (
                    "Sua senha está muito longa. "
                    "Escolha uma senha um pouco menor."
                )
            }, 422

    return None

def normalizar_dados_construtora(dados):
    """
    Prepara os dados já validados para armazenamento.
    Não inclui a senha: seu hash será gerado na rota.
    """
    dados_normalizados = {}

    if "nome" in dados:
        dados_normalizados["nome"] = dados["nome"].strip()

    if "email" in dados:
        dados_normalizados["email"] = dados["email"].strip().lower()

    if "telefone" in dados:
        dados_normalizados["telefone"] = re.sub(
            r"[^0-9]", "", dados["telefone"]
        )

    return dados_normalizados

def validar_dados_login(dados):
    if not isinstance(dados, dict):
        return {"erro": "Preencha seu email e sua senha"}, 422

    email = dados.get("email")
    senha = dados.get("senha")

    if not isinstance(email, str) or not email.strip():
        return {"erro": "Preencha seu email"}, 422

    if not isinstance(senha, str) or not senha.strip():
        return {"erro": "Preencha sua senha"}, 422

    # Mantém o limite usado no cadastro com Bcrypt.
    if len(senha.encode("utf-8")) > 72:
        return {"erro": "Email ou senha incorretos"}, 401

    return None