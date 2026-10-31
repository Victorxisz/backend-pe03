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
                value.lower() in {"senha", "password", "changeme", "your_secret_here", "teste"}
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
    entries = git("rev-list", "--objects", "--all").decode("utf-8").splitlines()
    # Uma única instância de git, sem deixar de examinar os blobs do histórico.
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for entry in entries:
            oid, _, name = entry.partition(" ")
            process.stdin.write((oid + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                raise RuntimeError("Não foi possível ler os objetos do histórico Git")
            kind, size = header[1], int(header[2])
            raw = process.stdout.read(size)
            if len(raw) != size or process.stdout.read(1) != b"\n":
                raise RuntimeError("Leitura incompleta do histórico Git")
            if kind != b"blob":
                continue
            if name.rsplit("/", 1)[-1] in forbidden:
                findings.append((oid, name, "arquivo de credenciais no histórico"))
            content = raw.decode("utf-8", errors="replace")
            findings.extend((oid, name, rule, line) for rule, line in find_secrets(content))
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Falha ao examinar o histórico Git")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    return findings
