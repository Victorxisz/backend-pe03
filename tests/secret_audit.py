"""Auditoria local por padrões; retorna apenas localização e regra, nunca valores."""

import re
import subprocess

PATTERNS = {
    "chave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credencial MongoDB": re.compile(r"mongodb(?:\+srv)?://([^\s:/]+):([^\s@]+)@"),
    "segredo literal": re.compile(
        r"""(?im)(?:JWT_SECRET_KEY|SECRET_KEY|API_KEY|AWS_SECRET_ACCESS_KEY)\s*[\]"']*\s*[:=]\s*["']([^"'\r\n]+)["']"""
    ),
}


def find_secrets(content):
    findings = []
    for rule, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            # Exemplos explicitamente fictícios, não exceções por caminho de arquivo.
            value = match.group(match.lastindex) if match.lastindex else ""
            if value and (
                value.lower() in {"senha", "password", "changeme", "your_secret_here"}
                or any(
                    word in value.lower()
                    for word in ("ficticia", "fictício", "example", "${", "<")
                )
            ):
                continue
            findings.append((rule, content.count("\n", 0, match.start()) + 1))
    return findings


def audit_git(root):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)

    findings = []
    forbidden = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.test",
        "id_rsa",
        "id_ed25519",
    }
    paths = git("ls-files", "-z").decode("utf-8").split("\0")
    for name in filter(None, paths):
        path = root / name
        if path.name in forbidden:
            findings.append((name, "arquivo de credenciais"))
        if path.is_file():
            findings.extend(
                (name, rule, line)
                for rule, line in find_secrets(
                    path.read_text(encoding="utf-8", errors="replace")
                )
            )
    # Todos os blobs alcançáveis pelas referências locais, inclusive versões removidas.
    for entry in git("rev-list", "--objects", "--all").decode("utf-8").splitlines():
        oid, _, name = entry.partition(" ")
        if git("cat-file", "-t", oid).strip() != b"blob":
            continue
        if name.rsplit("/", 1)[-1] in forbidden:
            findings.append((oid, name, "arquivo de credenciais no histórico"))
        content = git("cat-file", "blob", oid).decode("utf-8", errors="replace")
        findings.extend((oid, name, rule, line) for rule, line in find_secrets(content))
    return findings
