import re


CAMPOS_TEXTO = ("nome", "email", "telefone", "cargo")
CAMPOS_ATUALIZAVEIS = set(CAMPOS_TEXTO) | {"obras"}

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

        if not isinstance(obras, list) or not all(
            type(codigo_obra) is int and codigo_obra > 0
            for codigo_obra in obras
        ):
            return {
                "erro": (
                    "Obras deve ser uma lista "
                    "de números inteiros positivos"
                )
            }, 422

    return None


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
        # Remove códigos repetidos, preservando a ordem.
        dados_normalizados["obras"] = list(
            dict.fromkeys(dados["obras"])
        )

    return dados_normalizados