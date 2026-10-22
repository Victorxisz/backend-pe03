# Projeto Ágil — acompanhamento de obras

## Executar os testes

Na pasta `backend-pe03`, usando PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-test.txt
.\.venv\Scripts\python -m pytest -v
```

Não é necessário ativar o ambiente virtual. O antigo `test_api.py` da raiz foi
migrado para `tests/`; execute os comandos acima, não o arquivo antigo.
Todos os testes seguem **Preparação → Execução → Verificação**, com fixtures para
os dados e recursos compartilhados. Os nomes `test_ctNN_*` identificam a regra;
os parâmetros identificam a variação. Para investigar uma falha:

```powershell
.\.venv\Scripts\python -m pytest tests/test_api.py -k ct08 -vv --tb=short
```

### Isolamento e persistência

A execução padrão usa `mongomock`, um banco em memória novo por teste, com dados
fictícios. Não lê `.env`, não usa `MONGO_URI` do ambiente e não abre conexão MongoDB
real. As verificações comparam respostas HTTP, documentos armazenados e snapshots
de todas as coleções não vazias antes/depois das rejeições. Isso exercita a API e
seu acesso ao armazenamento em memória, **não comprova persistência no Atlas**.

O adaptador em `tests/support.py` substitui o cliente MongoDB antes de importar a
aplicação e redireciona a seleção do banco em `db.py` para o namespace
de teste. Não modifica a configuração de produção. Cada teste recebe um banco
`tests_<prefixo>_<uuid>` descartável; somente esse banco é removido no teardown.

Para integração real, use um **cluster de teste separado da demonstração**, com
credenciais exclusivas autorizadas a criar/remover os bancos descartáveis.
Defina `TEST_MONGO_URI` no ambiente da sessão com a URI desse cluster, cujo banco
na URI comece por `tests_` (exemplo de formato fictício:
`mongodb+srv://usuario:senha@cluster-teste.example/tests_pe03`). Não copie a URI
da demonstração, não grave credenciais no README nem no Git. O nome do banco
sozinho não comprova que o cluster é exclusivo: essa separação deve existir na
configuração do Atlas.

```powershell
# Após definir TEST_MONGO_URI com a credencial exclusiva de teste:
.\.venv\Scripts\python -m pytest --atlas -v
# Critério final: rotas ausentes também devem reprovar a execução.
.\.venv\Scripts\python -m pytest --atlas --require-routes -v
```

`--atlas` nunca usa fallback para a URI da demonstração. URI ausente/inválida ou
conexão indisponível causam erro explícito. Não é necessário manter Flask rodando.
CT-09 cria a obra, consulta com novo cliente e inicia outro processo Python com
uma aplicação Flask e conexão MongoDB novas, consultando o mesmo banco de teste.
Os dois processos usam o mesmo relógio controlado; as consultas são comparadas
aos campos enviados na criação, ao ID e à auditoria retornados pelo cadastro.
Sem `--atlas`, CT-09 fica como `SKIP`; não há versão em memória apresentada como
prova de persistência. A configuração real de `db.py` ainda deve ser validada no
deploy, pois o adaptador de teste a substitui.

### Cobertura e dependências dos cartões 2 a 7

| Casos | Verificações | Dependência |
| --- | --- | --- |
| CT-01/02 | Login válido, uso do token e credenciais inválidas | `POST /login`, listagem protegida |
| CT-03/04 | Leitura/escrita sem token, expirado e após logout; estado preservado | Autenticação JWT, `/logout` e rotas de obras |
| CT-05/06 | Cliente, entrega, JSON, `Location`, documento salvo, autoria/data do servidor e nova leitura | Criação e detalhe de obras |
| CT-07/08 | Modalidades conflitantes/ausentes, datas e nomes inválidos; campo indicado e nenhuma alteração | Validação da criação |
| CT-09 | Recuperação real após novo cliente/processo | Criação/detalhe e Atlas exclusivo de teste |
| CT-10 | Falha de gravação, mensagem de erro, sem recurso criado | Tratamento de erro na criação |
| CT-11 | Lista/detalhes corretos e marcos separados por obra | Listagem, detalhe e listagem de marcos |
| CT-12/13 | Filtros sobre documentos distintos, interseção e resultado vazio | Filtros de obras |
| CT-14 | Limites de atraso com relógio fixo e rejeição de edição do alerta | Detalhe e edição |
| CT-15 | ID ausente e filtros inválidos sem efeitos colaterais | Consultas e validações |
| CT-16 | Edição parcial com leitura posterior e preservação dos demais campos | Edição descritiva |
| CT-17 | Prazo/conclusão bloqueados, inclusive junto com campo permitido | Validação da edição descritiva |

Na branch `MatheusHermida`, o PATCH de edição descritiva já está registrado.
As rotas de login/logout, criação/consulta/listagem/exclusão de obras e consulta
de marcos continuam pendentes. A suíte verifica o mapa de rotas antes dos cenários e informa
`SKIP` com a dependência exata. Assim que a rota existir, o teste passa a executá-la:
erros de importação, autenticação ou implementação não são convertidos em `SKIP`.
`--require-routes` transforma ausência de rota em falha de preparação para CI/aceite.
**Uma execução com skips não significa que CT-01 a CT-17 foram aprovados.**

`tests/test_trabalhadores.py` preserva a regressão do cadastro já implementado
nesta branch (obra fictícia com ObjectId). `tests/test_isolamento.py` verifica o
redirecionamento do banco e a ausência de dados herdados. O cadastro `/usuarios`
foi removido da suíte: não integra CT-01 a CT-17 nem a conta única do MVP.

### Contrato usado pelos testes pendentes

Como o contrato técnico ainda é proposto, os testes explicitam as escolhas para
integração: coleções `tbl_construtora`, `tbl_obras`, `tbl_marcos`; login com
`username`/`password` (hash Bcrypt); identidade JWT `username`; cliente de referência
como string; auditoria `autor` e `data_registro`; vínculo de marco `obra_id` como
ObjectId; listas em `obras`/`marcos`; detalhes com `id` textual. Erros de domínio
usam `mensagem` não vazia e `campos`; credenciais inválidas usam mensagem neutra
`{"msg": "Usuário ou senha inválidos"}`. Edição proibida retorna `422`.

Os limites dos filtros são inclusivos por dia; entrega estimada usa o **fim** do
intervalo. O relógio dos cenários é `2030-10-20T12:00:00Z`; instantes retornados
devem conter fuso. Se a equipe decidir outro contrato, alinhar a documentação e
os testes juntos, preservando as regras de negócio e as verificações de persistência.

CT-03 exige somente a rota de cada variação; uma exclusão ainda ausente não
impede verificar uma leitura já implementada. CT-17 usa o estado `concluída`,
conforme RN-02, para evitar aprovação por enumeração inválida.

O CT-04 examina nomes de arquivos, conteúdo rastreado atual e blobs do histórico
alcançável por todas as referências locais do Git. Detecta padrões de chaves
privadas, URIs MongoDB com credenciais e atribuições literais de segredos. Os
resultados mostram apenas localização/regra, sem revelar valores. Exemplos
explicitamente fictícios são desconsiderados. A auditoria é heurística: não
identifica todo formato de segredo e não inspeciona histórico ausente em clones
rasos. Não faz fetch, não modifica commits nem reescreve nenhuma branch.
`tests/test_secret_audit.py` valida o detector com textos sintéticos.

Os testes HTTP não substituem os passos de interface previstos no documento de
casos: repetir os caminhos P0 no React (inclusive ausência de anúncio de sucesso
no CT-10). A revisão de segurança continua necessária; ausência de alertas no
scanner local não é garantia absoluta de ausência de segredos.

Documentação de produto e desenvolvimento do MVP acadêmico, com entrega prevista para **03/11/2026**. O foco é permitir que uma construtora registre e publique o andamento de obras com evidências, histórico de mudanças e ocorrências.

> Estado atual: especificação do MVP e implementação parcial. Este repositório já contém rotas Flask de trabalhadores e edição descritiva de obras; os demais fluxos descritos são requisitos, não funcionalidades presumidamente prontas. O protótipo visual anterior é apenas referência de interface.

## Comece por aqui

1. [Visão do produto e limite do MVP](docs/01-visao-e-escopo.md) — problema, valor e o que será demonstrado.
2. [Linguagem e modelo de domínio](docs/02-dominio-e-regras.md) — conceitos, relações e regras que não podem ser violadas.
3. [Funcionalidades](docs/03-funcionalidades.md) — catálogo priorizado, dividido por capacidade.
4. [Jornadas e critérios de aceite](docs/04-jornadas-e-aceite.md) — o que deve funcionar de ponta a ponta.
5. [Arquitetura e contrato inicial da API](docs/05-arquitetura-e-contratos.md) — orientação para React, Flask, MongoDB Atlas e EC2.
6. [Opções de APIs externas](docs/06-apis-externas.md) — alternativas, custos de adoção e decisão pendente.
7. [Plano de entrega e decisões](docs/07-plano-e-decisoes.md) — sequência de construção, riscos e dúvidas registradas.
8. [Casos de uso do MVP](docs/08-casos-de-uso-mvp.md) — trilha detalhada de ações da construtora.
9. [Casos de teste do MVP](docs/09-casos-de-teste-mvp.md) — verificações ligadas a cada caso de uso.
10. [Matriz de rastreabilidade](docs/10-matriz-de-rastreabilidade.md) — relação entre valor, funcionalidades, usos e testes.
11. [Organização proposta do backend](docs/11-organizacao-backend.md) — função de cada pasta e arquivo, com exemplos do projeto.

## Como usar esta documentação

- Uma tarefa de desenvolvimento deve apontar para a funcionalidade (`F-xx`) e para os critérios de aceite correspondentes (`CA-xx`).
- Mudanças de escopo devem atualizar primeiro a visão do produto, depois regras, funcionalidades e contrato da API afetados.
- `Confirmado` identifica decisão do grupo informada nesta conversa; `Proposta` identifica uma recomendação de modelagem ainda revisável; `Pendente` exige decisão ou validação.
- A documentação deste repositório pode ser a fonte principal enquanto cliente e servidor ficam em repositórios separados. O outro repositório deve apontar para esta fonte e para a versão da API adotada.

## Restrições da disciplina

Servidor Flask com API REST no nível 2 de Richardson; banco MongoDB Atlas; cliente React consumindo HTTP; implantação em EC2; ao menos uma API externa; **código do cliente e do servidor em repositórios distintos**; credenciais fora do Git e fornecidas ao professor pelo canal exigido pela disciplina. O tema e a integração externa ainda precisam de validação final pelo professor.


## UC-04 — edição descritiva de obra

`PATCH /api/v1/obras/{id}` exige `Authorization: Bearer <token>` válido.
Configure `JWT_SECRET_KEY` no ambiente do servidor com o mesmo segredo do emissor
JWT. Não há chave padrão de produção. A inicialização do verificador JWT foi
adicionada; emissão de tokens, login e logout dependem do cartão de autenticação.
Os testes geram tokens fictícios exclusivamente no ambiente isolado.

O corpo JSON deve conter um ou mais campos: `nome`, `descricao`, `localizacao`
(endereço no contrato atual) e `cliente` (um único cliente de referência).
Todos devem ser textos não vazios. Exemplo de corpo:

```json
{"descricao": "Descrição corrigida", "localizacao": "Rua Fictícia, 120"}
```

A resposta `200` contém `id` e os quatro campos descritivos atuais. A atualização
usa `$set` em uma única operação, sem sobrescrever campos omitidos, sem upsert e
sem modificar outras obras. Prazo, conclusão, auditoria, alertas e campos
desconhecidos são rejeitados com `422` antes de qualquer gravação, inclusive
quando enviados junto de uma correção válida ou de um motivo. Mudanças de prazo
ou conclusão devem passar pelo fluxo próprio com motivo e histórico.

Respostas adicionais: `400` para ID inválido, `404` para obra inexistente,
`401` para token ausente/expirado e `500` para falha de persistência.
A lógica está separada em `app/obras/routes.py`, `service.py` e `repository.py`.

Para executar a cobertura UC-04:

```powershell
.\.venv\Scripts\python -m pytest tests/test_api.py tests/test_uc04.py -k "ct16 or ct17" -v
```

CT-16 verifica o documento efetivamente atualizado no banco isolado, além do JSON
retornado. A releitura HTTP foi mantida no cenário separado
`test_ct16_releitura_http`, pendente do GET. CT-17 verifica que a tentativa
proibida preserva o banco inteiro. As verificações adicionais cobrem corpo/campos
inválidos, IDs, falha de gravação e preservação de outra obra. A execução local usa
memória; a validação da persistência no Atlas de teste continua separada.


### UC-04 — verificações locais e pendências separadas

Os cenários negativos de `tests/test_uc04.py` conferem a lista exata de campos
inválidos, a ausência de chamada a `find_one_and_update` e o banco preservado.
As falhas de gravação mantêm rota, serviço e repositório reais, simulando a
exceção somente no método da coleção: rejeição de gravação e servidor indisponível.
Também verificam o filtro por ID e o `$set` enviado. São falhas simuladas antes
da gravação; não demonstram rollback após timeout com resultado indeterminado.

```powershell
# Cobertura local UC-04 com relatório separado das pendências:
.\.venv\Scripts\python -m pytest tests/test_api.py tests/test_uc04.py tests/test_uc04_atlas.py -k "ct16 or ct17" -v
```

- **GET pendente:** `test_ct16_releitura_http`, em `tests/test_api.py`, precisa de
  `GET /api/v1/obras/{id}` para validar a releitura por HTTP.
- **Atlas pendente:** `tests/test_uc04_atlas.py` tem três cenários: correção
  persistida, rejeição de prazo e rejeição de conclusão. Consultam o mesmo banco
  descartável por outra conexão MongoDB, sem mocks de gravação e sem depender do
  GET. Por padrão ficam como `SKIP` antes de abrir qualquer conexão externa.

Para executar somente a integração, depois de configurar `TEST_MONGO_URI` com
credenciais exclusivas do cluster de teste conforme as instruções anteriores:

```powershell
.\.venv\Scripts\python -m pytest tests/test_uc04_atlas.py --atlas --require-routes -v
```

Não usar a base da demonstração. Os testes de Atlas não foram executados nesta
validação local. Falhas reais de rede durante uma gravação não são provocadas
por esta suíte; os cenários de erro no método da coleção continuam simulados.


### Integração da main no PR do UC-04

Os testes de referência permanecem em `tests/`; o `test_api.py` antigo da raiz
foi removido na resolução do conflito. O verificador JWT é inicializado uma
única vez e o blueprint da construtora recebido da main foi preservado.
O cadastro recebido da main foi mantido em `app/obras/cadastro_routes.py`, separado
do PATCH versionado. Ele ainda não é registrado, assim como na main recebida;
a publicação depende do alinhamento de autenticação e contrato de criação.

O cadastro de trabalhadores recebido da main exige ObjectId e vínculo com obra
existente, usando transação. Os cinco cenários de `tests/test_trabalhadores.py`
foram alinhados: criam uma obra fictícia no banco isolado, verificam o ID da obra
na resposta e o vínculo nas duas coleções. Cada ausência de campo deve retornar
`422` com a mensagem específica, preservando o snapshot de todas as coleções.

O `mongomock` não suporta sessões: somente no modo local, a fixture desse arquivo
simula o contexto da sessão/transação e remove o argumento `session` antes de
executar as operações reais no armazenamento em memória. Isso verifica o fluxo
e os dados salvos, sem comprovar atomicidade ou rollback no MongoDB. Com
`--atlas`, a adaptação fica desativada e usa-se a sessão real no banco de teste.
O Atlas não foi acessado nesta validação.

```powershell
.\.venv\Scripts\python -m pytest tests/test_trabalhadores.py -v
```
