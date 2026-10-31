"""Verifica detecção sem usar ou exibir credenciais reais."""

import pytest
import subprocess
from secret_audit import audit_git, find_secrets


@pytest.mark.parametrize(
    "content",
    [
        "mongodb+srv" + "://user:synthetic-value@host/db",
        "JWT_SECRET_KEY" + " = 'synthetic-value'",
        "-----BEGIN " + "PRIVATE KEY-----",
    ],
)
def test_detectar_padrao_sensivel(content):
    # Preparação
    expected_count = 1

    # Execução
    findings = find_secrets(content)

    # Verificação
    assert len(findings) == expected_count
    assert all(len(finding) == 2 for finding in findings)


def test_permitir_exemplo_explicitamente_ficticio():
    # Preparação
    content = "JWT_SECRET_KEY" + " = 'chave-ficticia-de-testes'"

    # Execução
    findings = find_secrets(content)

    # Verificação
    assert findings == []


def test_placeholder_teste_exato_nao_libera_valores_com_prefixo_semelhante():
    campo = "CLOUDINARY_API_KEY"
    assert find_secrets(campo + " = 'teste'") == []
    assert len(find_secrets(campo + " = 'teste-valor-sintetico'")) == 1


@pytest.mark.parametrize("valor", ["teste", "TESTE"])
def test_permitir_valor_exato_usado_pelo_provedor_simulado(valor):
    content = "CLOUDINARY_API_KEY" + " = '" + valor + "'"

    assert find_secrets(content) == []


def test_auditoria_encontra_valor_removido_do_historico(tmp_path):
    # Preparação: um repositório descartável com credencial inteiramente fictícia.
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    arquivo = tmp_path / "configuracao.py"
    arquivo.write_text("JWT_SECRET_" + "KEY = 'valor-sintetico-123'\n", encoding="utf-8")
    git("add", "configuracao.py")
    git("-c", "user.name=Teste", "-c", "user.email=teste@example.com", "commit", "-qm", "Adicionar exemplo")
    arquivo.write_text("# exemplo removido\n", encoding="utf-8")
    git("add", "configuracao.py")
    git("-c", "user.name=Teste", "-c", "user.email=teste@example.com", "commit", "-qm", "Remover exemplo")

    # Execução e verificação: a segunda versão não deve esconder a primeira.
    findings = audit_git(tmp_path)
    assert any(len(item) == 4 and item[1] == "configuracao.py" and item[2] == "segredo literal" for item in findings)
