"""Verifica detecção sem usar ou exibir credenciais reais."""

import pytest
from secret_audit import find_secrets


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
