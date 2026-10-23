"""CT-04: auditoria de credenciais no conteúdo e histórico."""

from pathlib import Path
from secret_audit import audit_git



def test_ct04_credenciais_no_conteudo_e_historico_git():
    # Preparação
    root = Path(__file__).resolve().parents[2]

    # Execução
    findings = audit_git(root)

    # Verificação
    assert not findings, "Possíveis segredos (valores omitidos): " + repr(findings)

