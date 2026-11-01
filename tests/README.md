# Organização dos testes

Os casos são agrupados por funcionalidade: `autenticacao`, `obras`, `marcos`,
`avancos`, `midias`, `mudancas`, `historico`, `ocorrencias` e `trabalhadores`.
`dominio` cobre regras dos objetos; `infraestrutura` cobre isolamento e contratos
transversais das rotas; `seguranca` cobre a auditoria de segredos.

`integracao` reúne fluxos que atravessam módulos ou reiniciam a aplicação.
Estar nessa pasta não implica rede real: cada arquivo informa se os provedores
são simulados ou reais. Os testes reais continuam opt-in.

`test_exclusao_cascata.py` fica na raiz por atravessar quase todos os módulos:
UC-17 remove obra ou marco com marcos, avanços, mídias, ocorrências, histórico e
vínculos de trabalhador. Ele traz o próprio cenário e o provedor simulado, e usa
`transacao_local` nos casos que dependem da transação.

## Executar

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m pytest tests/avancos -q
.\.venv\Scripts\python -m pytest tests/midias tests/integracao -q
```

Por padrão o MongoDB é simulado. `--atlas` habilita os testes compatíveis com
coleções temporárias no banco configurado. Os cenários exclusivos de UC-09
mantêm `--uc09-atlas`, `--uc09-cloudinary` e suas variáveis `TEST_UC09_*`.
Outros testes Cloudinary usam `RUN_CLOUDINARY_TESTS=1` e `TEST_CLOUDINARY_*`.
Não habilite integrações reais sem ler os requisitos do cenário.

## Recursos compartilhados

- `conftest.py`: banco isolado, aplicação, sessão, relógio e opções do pytest.
- `support_avancos.py`: provedor simulado, cenário de marco, formulário e
  simulador único de rollback local. Com `--atlas`, não substitui transações reais.
- `support_publicacoes.py`: cenário de publicação reutilizado pelo histórico.
- `support_atlas.py`: ciclo de vida do banco descartável exclusivo de UC-09.
- `support_midias.py`, `support_obras.py`, `support.py` e `mongo_support.py`:
  arquivos de mídia gerados, dados, comparações e isolamento de coleções.
- Os scripts `*_probe.py` na raiz são auxiliares de subprocesso, não testes.

Não importe fixtures de outro arquivo `test_*.py`. Coloque recursos reutilizáveis
em `conftest.py` ou em `support_*.py`, preservando o isolamento de cada teste.

O antigo `test_avancos_uc09.py` foi dividido em cadastro HTTP, consultas,
idempotência, falhas de cadastro e integração com exclusão. Os corpos dos testes
e suas parametrizações foram preservados. O cadastro contratual fica em arquivo
próprio porque também verifica a representação pública e a publicação posterior.

A reorganização manteve 455 funções de teste e 1.142 casos parametrizados.
A redução de duplicação concentrou-se nas fixtures de banco e armazenamento;
cenários de erro, segurança e concorrência não foram removidos por quantidade.
