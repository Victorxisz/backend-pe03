# Projeto Ágil — acompanhamento de obras

A organização atual com POO e as decisões de 30/10 estão em
[Modelo e organização do backend](docs/13-modelo-poo.md).

## Rotas existentes

Inventário conferido no `url_map` da aplicação: **40 operações de negócio**.
As barras finais abaixo fazem parte dos caminhos atuais. `HEAD` nas consultas,
`OPTIONS` automático e a rota técnica `/static/{filename}` não entram na contagem.

| Métodos | Caminho | Finalidade |
| --- | --- | --- |
| POST | `/construtora/` | Cadastrar conta |
| POST | `/construtora/login/` | Entrar e emitir tokens |
| POST | `/construtora/refresh/` | Renovar acesso com refresh token |
| POST | `/construtora/logout/` | Encerrar a sessão |
| PATCH, DELETE | `/construtora/{construtora_id}` | Alterar ou excluir a própria conta |
| GET, POST | `/obras` | Listar/filtrar ou cadastrar obras |
| GET, PATCH | `/obras/{obra_id}` | Consultar ou corrigir dados descritivos |
| PATCH | `/obras/{obra_id}/estado` | Alterar estado com motivo e histórico |
| GET, POST | `/obras/{obra_id}/marcos` | Listar ou cadastrar marcos |
| GET | `/obras/{obra_id}/marcos/{marco_id}` | Consultar marco da obra |
| POST | `/obras/{obra_id}/mudancas` | Aplicar replanejamento ou mudança de estado |
| GET | `/obras/{obra_id}/previa` | Consultar avanços publicados |
| PATCH | `/marcos/{marco_id}` | Alterar estado do marco com motivo |
| GET, POST | `/marcos/{marco_id}/dependencias` | Listar ou criar dependência |
| DELETE | `/marcos/{marco_id}/dependencias/{dependencia_id}` | Retirar dependência |
| GET, POST | `/marcos/{marco_id}/avancos` | Listar ou cadastrar avanços com mídias |
| GET, PATCH, DELETE | `/avancos/{avanco_id}` | Consultar, editar rascunho/corrigir publicação ou excluir rascunho |
| GET | `/avancos/{avanco_id}/versoes` | Consultar versões e comparar alterações |
| GET | `/avancos/{avanco_id}/midias` | Listar mídias |
| GET, POST | `/avancos/{avanco_id}/publicacoes` | Consultar publicação ou publicar rascunho |
| GET | `/midias/{midia_id}` | Consultar metadados da mídia |
| GET | `/midias/{midia_id}/conteudo` | Abrir arquivo com sessão válida |
| POST | `/sessoes` | Entrar na conta configurada |
| GET, DELETE | `/sessoes/atual` | Consultar ou encerrar sessão |
| GET, POST | `/trabalhadores/obra/{obra_id}/` | Listar ou cadastrar trabalhadores da obra |
| PATCH, DELETE | `/trabalhadores/{trabalhador_id}/` | Alterar ou excluir trabalhador |
| GET | `/trabalhadores/nome/{nome_usuario}/` | Buscar por nome |
| GET | `/trabalhadores/cargo/{cargo}/` | Buscar por cargo |

Cadastro de conta e login são públicos. As operações de negócio exigem token;
refresh exige refresh token e logout aceita access ou refresh da sessão.
Marcos também verificam perfil de construtora e conta ativa. Conta inativa não
pode alterar ou excluir o próprio cadastro, assim como não pode entrar/renovar.
O preflight `OPTIONS` negocia CORS sem autenticação e não executa a operação.

Os caminhos propostos em `docs/05-arquitetura-e-contratos.md` não são todos rotas
implementadas. Ainda não existem, por exemplo, `DELETE /obras/{id}`,
`DELETE /marcos/{id}`, consultas unificadas de mudanças, ocorrências e aceitações.
Isso não foi tratado como defeito de uma
rota existente nem substituído por endpoints que simulem sucesso.

`tests/test_rotas_api.py` verifica CORS em todas as operações registradas,
rejeição de chamadas sem token, conta inativa/perfil incorreto e IDs inválidos.
Os testes específicos de cada módulo continuam cobrindo suas regras de negócio.

## Linha do tempo publicada — UC-10

`GET /obras/{obraId}/previa` exige sessão de construtora ativa e retorna
`{"atualizacoes": [...]}`. Inclui somente avanços publicados dos marcos da obra,
ordenados pelo instante original da publicação decrescente e pelo ID crescente
em caso de empate. Obra sem publicações retorna 200 com lista vazia; obra
inexistente retorna 404 e identificador inválido retorna 400.

A representação compartilhada em `app/avancos/previa.py` apresenta descrição e
data atuais, contexto do marco, autor e instante da publicação e caminhos de mídia
protegidos por sessão. Uma composição atual persistida em `avanco.midias` usa o
mesmo formato de metadados públicos de `publicacao.midias` e prevalece sobre esse
snapshot original; sem o campo atual, permanece a composição original.
`editado: true` indica diferença de texto, data ou mídia, ou uma marca persistida
`avanco.editado: true` para correções que tenham restaurado o conteúdo original.
A leitura não altera o snapshot nem o banco. O fluxo de escrita e o histórico de
correções da UC-11 são descritos na seção de consulta de versões abaixo.

Os testes de prévia, publicação e acesso à mídia cobrem filtros, ordenação,
autenticação, composição atual e releitura em nova instância. A comprovação em
processo independente e MongoDB real usa `tests/test_publicacoes.py::test_ct45_previa_persistida_apos_novo_processo`
com `--atlas`; os testes locais em memória não comprovam durabilidade no MongoDB.

## Replanejamento e situação — UC-12

`POST /obras/{obraId}/mudancas` exige sessão da construtora. O corpo contém
`alvo` (`tipo`: `obra` ou `marco`, e `id`), `campo`, `novo_valor`, `motivo` e
`versao` inteira não negativa do alvo consultado. Documentos anteriores ao UC-12
começam na versão `0`. O servidor lê o valor anterior do banco; campos como
`valor_anterior`, `autor`, `instante` e `data_conclusao` não são aceitos no corpo.

```json
{
  "alvo": {"tipo": "obra", "id": "507f1f77bcf86cd799439011"},
  "campo": "entrega",
  "novo_valor": {"modalidade": "intervalo_estimado", "inicio": "2031-01-01", "fim": "2031-02-01"},
  "motivo": "Replanejamento aprovado pela construtora",
  "versao": 0
}
```

Campos aceitos:

| Alvo | Campo | Novo valor |
| --- | --- | --- |
| obra | `entrega` | Objeto `data_exata` com `data`, ou `intervalo_estimado` com `inicio` e `fim` |
| obra | `estado` | `planejada`, `em andamento`, `concluída` ou `suspensa` |
| marco | `periodo_previsto` | Objeto com `inicio_previsto` e `fim_previsto` |
| marco | `estado` | `a iniciar`, `em andamento` ou `concluído` |

Datas usam `AAAA-MM-DD`; intervalos exigem fim maior ou igual ao início. A troca
de modalidade substitui a entrega inteira, retirando campos incompatíveis.
Alterar estado de marco chama UC-07: dependências pendentes retornam `409` com
`codigo: DEPENDENCIAS_PENDENTES`. Após apresentar o aviso, reenviar com
`confirmar_dependencias: true` confirma a decisão; as dependências são consultadas
novamente. Essa confirmação só é aceita para estado de marco.

**Conclusão efetiva:** `data_conclusao` é a data UTC do relógio do servidor na
transição para `concluída`. Repetir esse estado preserva a data e a trilha.
Reabrir para qualquer outro estado limpa o valor atual (`null`), preservando a
data anterior no evento. Nova conclusão recebe a data da nova decisão. Registros
antigos concluídos sem essa data continuam sem alerta histórico calculável;
a consulta não inventa uma data de conclusão. O alerta `atrasada` compara a
conclusão efetiva com o prazo vigente; para obras abertas usa a data atual UTC.
No dia limite não há atraso. `atrasada` nunca é estado editável ou persistido.

Sucesso retorna `200` com o alvo atualizado e sua versão. Versão desatualizada
retorna `409`; dados inválidos, `422`; ID inválido, `400`; alvo inexistente ou de
outra obra, `404`. Alterações sem diferença de valor não criam eventos nem versões.
As rotas anteriores de estado reutilizam as mesmas regras e incrementam a versão.
O blueprint é registrado na fábrica `app.create_app`, usada por `api.py`.

**Persistência:** obras guardam prazo e evento em `historico_mudancas`, ou estado
e evento em `historico_estados`, por uma única operação atômica no documento.
Marcos atualizam alvo e `tbl_historico` numa transação MongoDB, exigindo replica
set/Atlas. Não existe fallback para gravações separadas nem exclusão isolada de
evento. Todos os eventos contêm alvo, campo, antes/depois, motivo, autor e instante.
A comparação de versão na gravação impede sobrescrita, inclusive após uma
sequência de alterações que devolva o alvo ao valor originalmente consultado.

```powershell
.\venv\Scripts\python -m pytest tests/test_mudancas.py tests/obras/test_estado.py tests/test_estado_marcos.py -q
.\venv\Scripts\python -m pytest tests/test_mudancas.py tests/test_estado_marcos.py -m atlas --atlas -q
```

Os testes Atlas usam coleções temporárias e verificam reversão tanto antes quanto
depois da inserção do evento. Testes em memória não comprovam transações reais.

## Cadastro de marcos — UC-05

`POST /obras/{obraId}/marcos` exige token de acesso da construtora e uma obra
existente. Recebe somente `nome`, `descricao`, `inicio_previsto` e `fim_previsto`.
Os textos devem ser preenchidos e as datas devem existir no formato `AAAA-MM-DD`,
com fim maior ou igual ao início. O estado inicial é sempre `a iniciar`.

A resposta `201` contém `id` e `obra_id` textuais, os dados do marco e `Location`
com `/obras/{obraId}/marcos/{id}`. O `_id` interno permanece somente no banco.
Dados inválidos retornam `422`, ID de obra inválido retorna `400` e obra
inexistente retorna `404`, sem gravação. Falha no banco retorna `500`.

```powershell
.\venv\Scripts\python -m pytest tests/test_marcos.py -v
```

CT-18 e CT-19 verificam o fluxo desde o cadastro da obra, a resposta do marco,
o documento salvo e a preservação do banco nas rejeições. CT-21 usa a mesma
`MONGO_URI` da aplicação, no ambiente ou no `.env`, conforme a seção abaixo:

```powershell
.\venv\Scripts\python -m pytest tests/test_marcos.py -k ct21 --atlas -v
```

CT-21 inicia outro processo com uma aplicação Flask e conexão MongoDB novas e
confere todos os campos do marco na coleção temporária. Essa verificação cobre a persistência
do cadastro; a releitura por HTTP depende da implementação do cartão de consultas.
Sem `--atlas`, CT-21 fica como `SKIP`; os testes em memória não comprovam persistência.

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
.\.venv\Scripts\python -m pytest tests/obras/test_cadastro.py -k ct08 -vv --tb=short
```

### Organização dos testes

```text
tests/
├── conftest.py                  # aplicação, banco, conta, tokens e relógio
├── support.py                   # carregamento isolado e snapshots
├── support_obras.py             # preparação e verificações de obras
├── restart_probe.py             # processo independente do CT-09
├── autenticacao/
│   └── test_autenticacao.py     # CT-01 a CT-04
├── obras/
│   ├── test_cadastro.py         # CT-05 a CT-08 e CT-10
│   ├── test_cadastro_atlas.py   # CT-09
│   ├── test_consultas.py        # CT-11 a CT-15: consultas e atraso
│   ├── test_edicao.py           # UC-04: CT-16/17 e alerta não editável
│   └── test_edicao_atlas.py     # UC-04 com conexão real
├── trabalhadores/
│   └── test_cadastro.py         # regressão do cadastro existente
├── seguranca/
│   ├── test_segredos.py         # CT-04: arquivos e histórico Git
│   └── test_detector_segredos.py
└── infraestrutura/
    └── test_isolamento.py
```

Os códigos CT e o padrão **Preparação → Execução → Verificação** foram preservados.
Os cenários HTTP locais integram Flask e armazenamento em memória. Os arquivos
`*_atlas.py` exigem `--atlas`; testes do detector de segredos verificam a função
isoladamente. Testes de ponta a ponta pelo React continuam fora desta suíte.
Arquivos para edição, exclusão e consultas de trabalhadores devem ser adicionados
quando esses cenários forem escritos; a reorganização preserva a cobertura existente.
O modo de importação `importlib` permite nomes como `test_cadastro.py` em pastas distintas.
Tokens das fixtures usam o mesmo gerador da aplicação, com ID da construtora,
`tipo` e `sessao_id`. CT-01 verifica a emissão dos tokens; CT-04 verifica que logout
bloqueia o PATCH e a renovação; as consultas também exigem uma conta ativa.

Para executar apenas o UC-04 local:

```powershell
.\.venv\Scripts\python -m pytest tests/obras/test_edicao.py -v
```

### Isolamento e persistência

A execução padrão usa `mongomock`, um banco em memória novo por teste, com dados
fictícios. Não lê `.env`, não usa `MONGO_URI` do ambiente e não abre conexão MongoDB
real. As verificações comparam respostas HTTP, documentos armazenados e snapshots
de todas as coleções não vazias antes/depois das rejeições. Isso exercita a API e
seu acesso ao armazenamento em memória, **não comprova persistência no Atlas**.

O adaptador em `tests/support.py` substitui o cliente MongoDB antes de importar a
aplicação. O banco continua sendo `banco_de_dados`, como em `db.py`. Cada cenário
usa coleções com prefixo aleatório `tests_<uuid>_`, mantendo os nomes lógicos
`tbl_obras`, `tbl_marcos` e demais coleções dentro do teste. Ao terminar, somente
as coleções daquele prefixo são removidas; nenhum banco é criado ou apagado.

Para integração real, `--atlas` usa a **mesma `MONGO_URI` da aplicação**: primeiro
a variável de ambiente e, se ausente, o arquivo `.env` da raiz. Não é necessário
outro banco ou outra variável de conexão. As coleções normais da aplicação ficam
fora das consultas e da limpeza dos testes. A credencial precisa permitir criar
e remover as coleções temporárias no banco `banco_de_dados`.

```powershell
# Com MONGO_URI já configurada para a aplicação:
.\.venv\Scripts\python -m pytest --atlas -v
# Critério final: rotas ausentes também devem reprovar a execução.
.\.venv\Scripts\python -m pytest --atlas --require-routes -v
```

Com `--atlas`, URI ausente/inválida ou
conexão indisponível causam erro explícito. Não é necessário manter Flask rodando.
CT-09 cria a obra, consulta com novo cliente e inicia outro processo Python com
uma aplicação Flask e conexão MongoDB novas, consultando as mesmas coleções temporárias.
Os dois processos usam o mesmo relógio controlado; as consultas são comparadas
aos campos enviados na criação, ao ID e à auditoria retornados pelo cadastro.
Sem `--atlas`, CT-09 fica como `SKIP`; não há versão em memória apresentada como
prova de persistência. A configuração real de `db.py` ainda deve ser validada no
deploy, pois o adaptador de teste a substitui.

### Cobertura e dependências dos cartões 2 a 7

| Casos | Verificações | Dependência |
| --- | --- | --- |
| CT-01/02 | Login válido, uso do token e credenciais inválidas | `POST /construtora/login/`, listagem protegida |
| CT-03/04 | Leitura/escrita sem token, expirado e após logout; estado preservado | Autenticação JWT, `/construtora/logout/` e rotas de obras |
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
Login, renovação e logout estão registrados em `/construtora/login/`,
`/construtora/refresh/` e `/construtora/logout/`. O cadastro está registrado em
`POST /obras`. Consulta/listagem/exclusão de obras e consulta
de marcos continuam pendentes. A suíte verifica o mapa de rotas antes dos cenários e informa
`SKIP` com a dependência exata. Assim que a rota existir, o teste passa a executá-la:
erros de importação, autenticação ou implementação não são convertidos em `SKIP`.
`--require-routes` transforma ausência de rota em falha de preparação para CI/aceite.
**Uma execução com skips não significa que CT-01 a CT-17 foram aprovados.**

`tests/trabalhadores/test_cadastro.py` preserva a regressão do cadastro já implementado
nesta branch (obra fictícia com ObjectId). `tests/infraestrutura/test_isolamento.py` verifica o
redirecionamento do banco e a ausência de dados herdados. O cadastro `/usuarios`
foi removido da suíte: não integra CT-01 a CT-17 nem a conta única do MVP.

### Contrato usado pelos testes pendentes

Como o contrato técnico ainda é proposto, os testes explicitam as escolhas para
integração: coleções `tbl_construtora`, `tbl_obras`, `tbl_marcos`; login com
`email`/`senha` (hash Bcrypt em `senha_hash`); identidade JWT com o ID textual
da construtora e claims `tipo` e `sessao_id`; cliente de referência
como string; auditoria `autor` (ID textual da construtora) e `data_registro`; vínculo de marco `obra_id` como
ObjectId; listas em `obras`/`marcos`; detalhes com `id` textual. Erros de domínio
usam `mensagem` não vazia e `campos`; credenciais inválidas usam mensagem neutra
`{"erro": "Email ou senha incorretos"}`. Edição proibida retorna `422`.

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
`tests/seguranca/test_detector_segredos.py` valida o detector com textos sintéticos.

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

`PATCH /obras/{id}` exige `Authorization: Bearer <token>` válido.
Configure `JWT_SECRET_KEY` no ambiente do servidor com o mesmo segredo do emissor
JWT. Não há chave padrão de produção. Login, renovação e logout estão
implementados; a sessão revogada bloqueia acesso e renovação.
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
.\.venv\Scripts\python -m pytest tests/obras/test_edicao.py -k "ct16 or ct17" -v
```

CT-16 verifica o documento efetivamente atualizado no banco isolado, além do JSON
retornado. A releitura HTTP foi mantida no cenário separado
`test_ct16_releitura_http`, usando o GET já registrado. CT-17 verifica que a tentativa
proibida preserva o banco inteiro. As verificações adicionais cobrem corpo/campos
inválidos, IDs, falha de gravação e preservação de outra obra. A execução local usa
memória; a validação da persistência no Atlas de teste continua separada.


### UC-04 — verificações locais e pendências separadas

Os cenários negativos de `tests/obras/test_edicao.py` conferem a lista exata de campos
inválidos, a ausência de chamada a `find_one_and_update` e o banco preservado.
As falhas de gravação mantêm rota, serviço e repositório reais, simulando a
exceção somente no método da coleção: rejeição de gravação e servidor indisponível.
Também verificam o filtro por ID e o `$set` enviado. São falhas simuladas antes
da gravação; não demonstram rollback após timeout com resultado indeterminado.

```powershell
# Cobertura local UC-04 com relatório separado das pendências:
.\.venv\Scripts\python -m pytest tests/obras/test_edicao.py tests/obras/test_edicao_atlas.py -k "ct16 or ct17" -v
```

- **Releitura HTTP:** `test_ct16_releitura_http`, em `tests/obras/test_edicao.py`,
  usa `GET /obras/{id}` para validar os dados após a edição.
- **Atlas pendente:** `tests/obras/test_edicao_atlas.py` tem três cenários: correção
  persistida, rejeição de prazo e rejeição de conclusão. Consultam as mesmas coleções
  temporárias por outra conexão MongoDB, sem mocks de gravação e sem depender do
  GET. Por padrão ficam como `SKIP` antes de abrir qualquer conexão externa.

Para executar somente a integração, usando `MONGO_URI` do ambiente ou do `.env`:

```powershell
.\.venv\Scripts\python -m pytest tests/obras/test_edicao_atlas.py --atlas --require-routes -v
```

Os testes em memória não comprovam persistência. Falhas reais de rede durante uma gravação não são provocadas
por esta suíte; os cenários de erro no método da coleção continuam simulados.


### Integração da main no PR do UC-04

Os testes de referência permanecem em `tests/`; o `test_api.py` antigo da raiz
foi removido na resolução do conflito. O verificador JWT é inicializado uma
única vez e o blueprint da construtora recebido da main foi preservado.
O cadastro recebido da main foi integrado em `app/obras/cadastro_routes.py`,
com nome de blueprint próprio para coexistir com o PATCH. Está registrado em
`POST /obras`, protegido por JWT. A edição usa `PATCH /obras/{id}`.
Aplicação, testes e documentação usam esses caminhos, sem prefixo de versão
ou aliases. Os métodos HTTP distinguem as operações sobre o recurso.

O cadastro usa `cliente` (em vez de `cliente_referencia`), `tipo` igual a `casa`
ou `apartamentos` e auditoria `autor`/`data_registro` gerada no servidor. O autor
é a identidade do token de acesso; o instante é UTC. Campos reservados ou
desconhecidos são rejeitados. A resposta é `201` com `Location`; validações
retornam `422` com `mensagem` e `campos`, e falha de gravação retorna `500`.
Entrega aceita data exata ou intervalo estimado, sem misturar os campos, com
datas reais em `AAAA-MM-DD` e fim maior ou igual ao início.

Os testes de criação verificam a resposta e o documento salvo sem depender do
GET ainda pendente; a releitura HTTP fica em cenários separados. Para executar:

```powershell
.\venv\Scripts\python -m pytest tests/obras/test_cadastro.py -v
```

O corpo completo está documentado no [contrato da API](docs/05-arquitetura-e-contratos.md#cadastro-de-obra--contrato-implementado).

O cadastro de trabalhadores recebido da main exige ObjectId e vínculo com obra
existente, usando transação. Os cinco cenários de `tests/trabalhadores/test_cadastro.py`
foram alinhados: criam uma obra fictícia no banco isolado, verificam o ID da obra
na resposta e o vínculo nas duas coleções. Cada ausência de campo deve retornar
`422` com a mensagem específica, preservando o snapshot de todas as coleções.

O `mongomock` não suporta sessões: somente no modo local, a fixture desse arquivo
simula o contexto da sessão/transação e remove o argumento `session` antes de
executar as operações reais no armazenamento em memória. Isso verifica o fluxo
e os dados salvos, sem comprovar atomicidade ou rollback no MongoDB. Com
`--atlas`, a adaptação fica desativada e usa-se a sessão real nas coleções temporárias
do banco da aplicação.

```powershell
.\.venv\Scripts\python -m pytest tests/trabalhadores/test_cadastro.py -v
```


## UC-03 — listagem, filtros e consulta de obras

Todas as consultas abaixo exigem uma sessão JWT de construtora ativa e não revogada:

- `GET /obras`: retorna `{"obras": [...]}`; sem resultados, retorna lista vazia e HTTP 200.
- `GET /obras/{id}`: retorna o detalhe; ID inválido retorna 400 e obra ausente retorna 404.
- `GET /obras/{id}/marcos`: lista somente marcos vinculados à obra; obra sem marcos retorna lista vazia, obra ausente retorna 404.

A listagem aceita `nome`, `cliente`, `estado`, `registroDe`, `registroAte`,
`entregaDe` e `entregaAte`. Nome e cliente usam busca parcial literal sem distinguir
maiúsculas de minúsculas. Estado aceita `planejada`, `em andamento`, `concluída`
e `suspensa`. Os filtros são combinados por interseção.
Datas usam `AAAA-MM-DD`; os limites são inclusivos e podem ser enviados separadamente.
O registro considera o dia em UTC; entrega estimada considera o fim do intervalo.
Filtros desconhecidos, datas inválidas e intervalos invertidos retornam 422 antes
da consulta das obras. Falhas de consulta retornam 500 com mensagem sem detalhes do driver.

Lista e detalhe retornam os mesmos alertas derivados, sem alterar o banco.
`atrasada` aparece após a data exata ou o fim estimado, preservando o estado da obra.
Obras concluídas não recebem atraso baseado no relógio atual; a regra histórica
com data efetiva de conclusão continua dependendo do contrato desse campo.

```powershell
.\.venv\Scripts\python -m pytest tests/obras/test_consultas.py -v
```

A execução local usa mongomock. A persistência após reinício continua sendo
verificada separadamente com Atlas exclusivo de teste.


## UC-08 — infraestrutura de fotos, vídeos e documentos

Provedor adotado neste cartão: Cloudinary. Formatos e limites iniciais acordados:
JPEG/PNG até 10 MiB, MP4 até 100 MiB e PDF até 10 MiB. Os limites, timeout e validade
do acesso são configuráveis no ambiente; consulte `.env.example`. Instale as novas
dependências de `requirements.txt`. Nenhuma credencial é fixada no código ou enviada ao React.

`app/integracoes/armazenamento.py` fornece `ArmazenamentoCloudinary`:

- `enviar(arquivo_validado)`: envia e confirma os metadados retornados pelo provedor.
- `verificar_disponibilidade(referencia)`: distingue arquivo ausente de falha do serviço.
- `obter_acesso(referencia)`: fornece URL HTTPS assinada com expiração (padrão 5 minutos).
- `remover(referencia)`: remove por referência externa, com invalidação e resultado verificado; remover arquivo já ausente é permitido.

A referência persistida contém `provedor="cloudinary"`, `public_id`,
`resource_type`, `delivery_type` e `formato`. Os metadados contêm `tipo`, `nome`,
`tamanho`, `mime` e `referencia_externa`; não guarde a URL temporária como referência.
Uploads usam IDs aleatórios, sem sobrescrever arquivos existentes, e entrega
`authenticated`. Fotos usam recurso `image`, vídeos `video` e PDFs `raw`.
Veja a [documentação oficial de acesso protegido](https://cloudinary.com/documentation/control_access_to_media)
e a [Upload API](https://cloudinary.com/documentation/image_upload_api_reference).
A conta Cloudinary precisa permitir entrega autenticada e download de PDFs;
limitações ou cotas da conta causam erro explícito, sem fallback público.

`app/avancos/midias.py` valida o conteúdo com Pillow (fotos), PyAV (contêiner MP4
com vídeo decodificável) e pypdf (estrutura e conteúdo de PDF não criptografado).
Não confia na extensão ou no Content-Type informado pelo cliente. Limita a leitura
por bytes e rejeita arquivos vazios, formatos não permitidos e conteúdo inválido.
Isso valida formato e tamanho; não substitui uma análise de malware.

O serviço reutilizável recebe arquivos `FileStorage` e uma função de persistência:

```python
from app.avancos.midias import ServicoMidias

servico = ServicoMidias()  # lê configuração do ambiente do servidor
resultado = servico.executar_com_midias(arquivos, salvar_avanco)
# salvar_avanco(metadados) deve salvar o negócio atomicamente e retornar o resultado.
```

Todo o lote é validado antes do primeiro upload. A função `salvar_avanco` só é
chamada após todos os envios confirmados. Se um envio ou a gravação falhar, o
serviço remove os novos arquivos. Como um timeout pode ocorrer após o upload,
o ID externo é escolhido antes da chamada para permitir compensação.
Os arquivos de versões anteriores não são removidos durante uma correção, pois
podem estar referenciados no histórico.

`ErroMidia` indica entrada inválida (422) ou tamanho excedido (413).
`ErroArmazenamento` indica configuração/indisponibilidade (503), ou mídia ausente
(404 ao obter acesso). `ErroLimpeza.pendentes` lista referências cuja remoção não
foi confirmada. O serviço de negócio deve guardar essas referências para nova
tentativa e nunca anunciar sucesso nesse caso. A compensação não é uma transação
distribuída: interrupções do processo e resultados indeterminados do banco exigem
reconciliação no serviço de rascunho/correção.

Este cartão entrega infraestrutura reutilizável, sem criar uma rota pública de
upload isolado. O serviço de rascunho deve validar marco, data e descrição, chamar
a infraestrutura e persistir o avanço com estado `rascunho`. A correção deve
preservar histórico e tratar as referências. Portanto, os testes abaixo cobrem
a parte de armazenamento de CT-31/32/34/35 e CT-109/110; não comprovam sozinhos
os casos de uso completos de rascunho, edição ou publicação.

```powershell
.\.venv\Scripts\python -m pytest tests/test_armazenamento.py -v
```

Por padrão, o SDK externo é simulado e os arquivos de teste são gerados localmente.
O teste real usa somente credenciais `TEST_CLOUDINARY_CLOUD_NAME`,
`TEST_CLOUDINARY_API_KEY` e `TEST_CLOUDINARY_API_SECRET` de uma conta de teste.
Não lê `.env` nem usa as credenciais normais como fallback. Após definir essas
variáveis na sessão, habilite explicitamente:

```powershell
$env:RUN_CLOUDINARY_TESTS = "1"
.\.venv\Scripts\python -m pytest tests/test_armazenamento.py -m cloudinary -v
```

O teste real envia PNG, MP4 e PDF, abre o acesso assinado, compara os bytes e remove
os arquivos. Exerce APIs e cotas reais da conta de teste. Sem essa execução,
a integração externa permanece pendente; testes locais não a substituem.


## Integração dos cartões UC-08 — envio e acesso autenticado

O envio de `app/avancos/midias.py` e as rotas de acesso agora usam o mesmo adaptador
`ArmazenamentoCloudinary`. A leitura fica em `app/avancos/acesso_midias.py`, e o
acesso ao MongoDB em `app/avancos/repository.py`. Não há fallback automático para
arquivos locais. As credenciais são as mesmas variáveis `CLOUDINARY_*` documentadas acima.

Rotas registradas em `api.py`:

- `GET /avancos/{avancoId}/midias`: lista os metadados das mídias do avanço.
- `GET /midias/{midiaId}`: retorna os metadados de uma mídia vinculada a avanço existente.
- `GET /midias/{midiaId}/conteudo`: recupera o arquivo no Cloudinary e o entrega pelo Flask.

Todas exigem JWT de uma construtora ativa; token ausente, expirado ou revogado
não permite consultar o banco de mídia nem alcançar o provedor. Os metadados
públicos incluem uma rota relativa `conteudo`, sem `public_id`, credenciais,
referência externa ou URL Cloudinary. O acesso ao original é assinado apenas
no servidor; a resposta HTTP não redireciona o navegador ao provedor.
Respostas usam `Cache-Control: private, no-store` e `X-Content-Type-Options: nosniff`.
O React deve enviar o Bearer token também ao buscar os bytes, por exemplo com
`fetch` e conversão para Blob; um elemento HTML com `src` sozinho não envia
esse cabeçalho. Vídeos aceitam requisições Range autenticadas.

Contrato persistido em `tbl_midias`:

```python
{
    "_id": ObjectId(),
    "avanco_id": id_do_avanco,  # ObjectId de um registro em tbl_avancos
    "data_envio": datetime.now(timezone.utc),
    **metadados_retornados_pelo_envio,
}
```

`metadados_retornados_pelo_envio` contém `tipo`, `nome`, `tamanho`, `mime` e
`referencia_externa` estruturada, incluindo `provedor="cloudinary"`.
A referência é salva inteira; não deve ser convertida para string nem substituída
por uma URL. O campo público `formato` continua como alias de `mime` para
compatibilidade com o cartão de acesso anterior.

O callback `salvar` de `ServicoMidias.executar_com_midias` deve persistir esses
metadados com o vínculo, junto da operação de negócio do avanço. Ele só é chamado
depois dos uploads e deve falhar por exceção se a gravação não for concluída.
A validação de marco, data e descrição e a criação do rascunho continuam sendo
responsabilidade desse serviço de negócio; estas rotas não criam avanços.

Registro inexistente ou mídia órfã retorna 404. Registro existente com arquivo
ausente no provedor retorna 502 com `CONTEUDO_AUSENTE_NO_PROVEDOR`; falha de rede,
cota ou acesso retorna 502 com `PROVEDOR_INDISPONIVEL`. Dados internos do driver
ou do Cloudinary não entram na resposta. O download é limitado ao tamanho salvo
e recusado se os bytes recebidos não corresponderem ao tamanho esperado.

```powershell
.\.venv\Scripts\python -m pytest tests/test_armazenamento.py tests/test_acesso_midias.py -v
```

Os testes locais geram arquivos válidos, simulam somente a fronteira externa e
exercitam envio → referência no MongoDB em memória → rota autenticada → bytes.
Cobrem os três tipos, sessão ausente/expirada/revogada, conta inativa, isolamento
entre avanços, mídia órfã, falhas do banco/provedor e nova instância Flask.
A nova instância usa o mesmo banco e o mesmo provedor simulados; não é uma prova
de persistência real após reinício de processo/Atlas.

Os testes `-m cloudinary` de acesso também são opt-in, com `RUN_CLOUDINARY_TESTS=1`
e credenciais `TEST_CLOUDINARY_*`. Eles enviam arquivos reais pela integração,
recuperam os bytes pelas rotas protegidas e removem os arquivos ao terminar.
Sem essa execução, o provedor externo continua não validado de ponta a ponta.


## UC-01 — sessão da construtora

Configure no `.env` do servidor `CONSTRUTORA_ID` com o ObjectId da única conta
previamente provisionada em `tbl_construtora`, com `ativo: true` e `senha_hash`
gerado com Bcrypt. Configure também `JWT_SECRET_KEY`; não versione credenciais.
O ID deve corresponder à conta já cadastrada pela administração. O projeto não
cria nem modifica a conta automaticamente. Sem ID válido, `POST /sessoes` retorna `503`.
A troca do ID exige reiniciar o servidor e invalida tokens da conta anterior.

`POST /sessoes` recebe JSON com `email` e `senha` e retorna access e refresh
JWT. `GET /sessoes/atual` exige access token e informa os dados não sensíveis
da conta ativa; `DELETE /sessoes/atual` encerra a sessão. As rotas antigas
`/construtora/login/` e `/construtora/logout/` seguem a mesma regra; a rota de
cadastro público `/construtora/` retorna `403` quando `CONSTRUTORA_ID` está configurado.
Sem essa configuração, as rotas antigas de cadastro/login mantêm o comportamento
anterior para compatibilidade; no MVP de conta única, configure o ID antes da implantação.
A renovação usa o mesmo ID de
sessão e o logout revoga ambos os tokens. A revogação é persistida no banco.

```powershell
.\.venv\Scripts\python -m pytest tests/autenticacao -q
```

A execução padrão usa `mongomock`; não configura nem conecta ao banco da
demonstração. O teste não comprova persistência real da revogação no Atlas.


## UC-09 — avanços em rascunho

`PATCH /avancos/{id}` edita apenas rascunhos. Aceita JSON para `data`, `descricao`
e `midias_manter` (lista de IDs), ou multipart com novos arquivos em `midias` e
`midias_manter` como lista JSON textual. Campos omitidos são preservados;
ao menos uma mídia deve permanecer. Publicações retornam `409`, pois dependem
do versionamento da UC-11. A edição usa o controle de revisão e a limpeza retomável
existentes, preservando autor, marco e estado.

A integração preserva a listagem como array e o campo `data_registro`. Acrescenta
`instante_registro` como alias e IDs/caminhos autenticados nas mídias, sem expor
referências externas. Documentos anteriores continuam consultáveis.

A construtora autenticada pode registrar um avanço em um marco existente com
`POST /marcos/{marcoId}/avancos`, usando `multipart/form-data`: campos de texto
`data` (`AAAA-MM-DD`) e `descricao`, e um ou mais arquivos no campo `midias`.
A resposta `201` devolve o recurso e `Location: /avancos/{id}`. Os recursos
`GET /marcos/{marcoId}/avancos` e `GET /avancos/{id}` retornam seus metadados;
cada mídia inclui um caminho autenticado para ler seu conteúdo. O servidor gera
autoria, instante e estado `rascunho`. Não há exigência de registros diários.

O serviço valida todos os arquivos antes do upload. Aceita no máximo cinco mídias
e 110 MiB por requisição multipart, incluindo campos e cabeçalhos. É necessário
informar `Content-Length`; o servidor responde `411` se estiver ausente e `413`
quando os limites forem excedidos.

Para repetição segura, o cliente deve enviar um `Idempotency-Key` único para cada
cadastro e reutilizar essa mesma chave e os mesmos dados em uma tentativa após
perda de resposta. A chave aceita letras, números, ponto, hífen e sublinhado, com
até 128 caracteres. Repetir uma operação concluída retorna o mesmo avanço; usar
a chave para dados diferentes ou uma operação ainda pendente retorna `409`. Sem
essa chave opcional, tentativas repetidas são tratadas como cadastros distintos.

Antes de cada upload é gravada em `tbl_uploads_pendentes` uma referência de
operação com o ID de cada arquivo planejado. Avanço, mídias, vínculo com marco e
marcação da operação como concluída são gravados na mesma transação MongoDB. Se o
processo for interrompido, a operação pendente permite localizar possíveis órfãos.
Falhas de remoção preservam a operação para reconciliação; um resultado de commit
incerto mantém os arquivos até que a gravação seja conferida. A implantação precisa
de um MongoDB que ofereça transações e do registro de operações persistente.

Para reconciliar, um responsável deve primeiro **parar a aplicação e aguardar
todos os uploads em andamento**, inclusive em outras instâncias. Com o mesmo
ambiente de banco e armazenamento configurado, liste as operações pendentes:

```powershell
.\.venv\Scripts\python -m app.avancos.reconciliacao --listar
```

Depois de conferir a operação, execute, substituindo o identificador listado:

```powershell
.\.venv\Scripts\python -m app.avancos.reconciliacao --operacao IDENTIFICADOR --servico-parado
```

A rotina preserva mídias de operações concluídas ou com avanço existente. Para
uma operação pendente sem avanço, tenta remover todas as referências e só marca
como limpa depois da confirmação do provedor. Se a remoção falhar, a operação
permanece pendente para nova tentativa. Após uma operação marcada como limpa, o
cliente deve usar uma nova chave para criar um novo avanço. `--servico-parado` é
uma confirmação operacional: ele não desliga servidores automaticamente.

Para executar CT-31 a CT-36 localmente, sem Atlas nem Cloudinary reais:

```powershell
.\.venv\Scripts\python -m pytest tests/test_avancos.py tests/test_avancos_atlas.py tests/test_avancos_integracao.py tests/test_armazenamento.py -m "not cloudinary" -q -ra
```

O teste local simula a transação e a fronteira do Cloudinary; isso não comprova
rollback nem persistência no MongoDB real. O cenário em `test_avancos_atlas.py`
é ignorado por padrão. Para executá-lo, use um **cluster Atlas exclusivo de
teste**, com conta própria e permissão para criar e remover bancos descartáveis;
a URI deve ser fornecida exclusivamente na variável `TEST_UC09_MONGO_URI`, com
nome de banco começando por `tests_uc09_`. Não use a base da demonstração. A
execução cria um banco com nome aleatório `tests_uc09_<uuid>`, remove somente
esse banco ao final e usa upload simulado. Uma nova aplicação em processo
separado consulta o avanço com uma nova conexão.

```powershell
# Após definir TEST_UC09_MONGO_URI para o cluster exclusivo de teste:
.\.venv\Scripts\python -m pytest tests/test_avancos_atlas.py --uc09-atlas -v
```

A execução em Atlas não valida o Cloudinary real. Os testes reais do Cloudinary
existentes exigem configuração e credenciais exclusivas de teste separadas.


### Integração real do UC-09

O teste conjunto em `tests/test_avancos_integracao.py` exige **cluster Atlas e
conta Cloudinary exclusivos de teste**. Ele só executa com `--uc09-atlas` e
`--uc09-cloudinary`, `TEST_UC09_MONGO_URI` apontando para o cluster de teste e
as variáveis `TEST_UC09_CLOUDINARY_CLOUD_NAME`, `TEST_UC09_CLOUDINARY_API_KEY`
e `TEST_UC09_CLOUDINARY_API_SECRET` da conta Cloudinary de teste. Ele não usa as
credenciais `CLOUDINARY_*` como fallback. O MongoDB usa bancos `tests_uc09_<uuid>`
e as mídias usam uma pasta `tests_uc09/<uuid>`. São testados PNG, MP4 e PDF,
com leitura do conteúdo em outro processo. Há ainda um teste de rollback com
transação real do Atlas e falha injetada na gravação de metadados.

```powershell
# Somente após configurar os serviços exclusivos de teste:
.\.venv\Scripts\python -m pytest tests/test_avancos_atlas.py tests/test_avancos_integracao.py --uc09-atlas --uc09-cloudinary -v
```

Ao fim, os arquivos e bancos temporários são removidos. Se a limpeza de arquivo
falhar, o banco de teste é preservado para permitir a reconciliação. Nenhum desses
serviços reais foi acessado na execução local desta tarefa.

## UC-09 — excluir avanço em rascunho (CT-39)

`DELETE /avancos/{avancoId}` exige a sessão de uma construtora ativa. O backend
não altera nada ao apenas consultar ou abrir a confirmação: a interface deve
cancelar sem enviar DELETE. Esta rota não exclui avanços publicados.

- `204`, sem corpo: arquivos exclusivos removidos, mídias do rascunho removidas e avanço excluído.
- `400`: ID inválido; `404`: avanço inexistente (inclusive ao repetir uma exclusão já concluída).
- `409`: não é rascunho, revisão mudou ou outra requisição ainda está excluindo.
- `422`: referência de uma mídia é inválida; nada é removido antes de validar o lote.
- `503`: limpeza ou finalização no banco ainda não concluída; nunca representa sucesso.

A exclusão faz uma reserva atômica por estado e revisão, usando o mesmo protocolo
`app/avancos/revisoes.py` da publicação. O estado interno `exclusao_pendente`
impede publicar/editar o rascunho durante a limpeza e retira suas mídias das rotas
de leitura. Não é um novo estado de negócio editável pelo React.

Antes de remover o primeiro arquivo, o próprio documento do avanço recebe um
diário durável em `exclusao`: arquivos da operação, pendentes, início, tentativas
e bloqueio temporário. Isso evita depender da memória do processo. A lista de
pendentes diminui a cada arquivo confirmado; arquivos com referências em outros
registros são preservados. A identidade compara provedor, public_id, tipo de
recurso e tipo de entrega, sem depender da ordem do dicionário ou do formato.
Referências históricas também são preservadas de forma conservadora.

Se o provedor falhar, os demais arquivos ainda são processados, a falha é
registrada com mensagem neutra e a resposta inclui `codigo="LIMPEZA_PENDENTE"`
e a quantidade pendente, sem referências externas nem credenciais. Para retomar,
repita o mesmo DELETE. Os arquivos já confirmados não são removidos novamente.
Remover um objeto já ausente é aceito pelo adaptador Cloudinary, permitindo
recuperar também timeouts cuja resposta tenha sido perdida.

O bloqueio evita duas limpezas simultâneas do mesmo avanço e é renovado durante
a operação. Após uma interrupção abrupta, outra requisição pode retomá-la quando
o bloqueio de cinco minutos expirar. Não há agendador automático neste cartão.
As pendências podem ser localizadas em `tbl_avancos` pelo estado
`exclusao_pendente`, mesmo após reiniciar o servidor.

As mídias do rascunho e o avanço só são removidos do banco depois de processar os
arquivos. Se a finalização no MongoDB falhar, o diário permanece e o DELETE pode
ser repetido, sem retornar 204 antecipadamente. Isso é compensação retomável,
não uma transação distribuída entre MongoDB e Cloudinary. Todos os serviços que
editarem rascunhos devem usar `revisoes.registrar_alteracao` e respeitar o estado;
escritas diretas no banco fora desse protocolo não são uma API suportada.

A verificação de compartilhamento consulta os registros do banco e preserva
objetos referenciados por outras mídias ou por snapshots históricos. Registros
já reservados para exclusão não são leitores ativos; a remoção externa é
idempotente quando duas exclusões compartilham o mesmo objeto. Para o volume
do MVP, a busca conservadora percorre as coleções; um volume maior exigirá um
índice/registro central de referências para evitar essa varredura.

```powershell
.\.venv\Scripts\python -m pytest tests/test_exclusao_rascunhos.py -v
```

Os testes locais usam MongoDB em memória e simulam apenas o provedor externo.
Cobrem fotos/vídeos/PDFs, ausência de efeitos antes do DELETE, arquivos
compartilhados e históricos, autenticação, conflitos de revisão/publicação,
falhas parciais, retomada após timeout e falhas de finalização no banco.
Não comprovam persistência no Atlas nem remoção no Cloudinary real.

### Consulta de versões de avanços

`GET /avancos/{id}/versoes` exige sessão e retorna versões em ordem, com a
atual identificada e os trechos de texto antes/depois para cada correção. A
versão inicial vem do snapshot da publicação. A consulta não expõe referências
privadas do provedor. Cada mídia inclui `retida`, indicando se o registro ainda
pertence ao acervo desse avanço. O caminho `conteudo` é reconstruído para a rota
autenticada; se o registro foi removido ou pertence a outro avanço, retorna
`retida: false` e `conteudo: null`, preservando os metadados históricos. Essa
checagem é local, sem chamadas ao provedor; `retida` não verifica a disponibilidade
do arquivo remoto. A informação de retenção é somente de consulta e não é
gravada nos snapshots nem considerada uma correção de conteúdo.

Cada versão contém `numero`, `atual`, `conteudo`, `autor_original`,
`origem_simulada` e `correcao`. A correção separa autor, motivo e instante de
quem criou o avanço. `campos` identifica alterações de data, descrição e mídias;
`diferencas_texto` contém trechos `igual`, `inserido`, `removido` ou `substituido`,
com `antes` e `depois`. Concatenar cada lado reconstrói integralmente o texto.
Datas de auditoria usam ISO 8601 e IDs BSON são serializados como texto.

Avanço inexistente retorna 404, rascunho retorna uma lista vazia, e publicação
sem correções retorna uma versão atual. Publicação declarada sem snapshot ou
cadeia inconsistente retorna 409 `HISTORICO_INDISPONIVEL`, sem fabricar versões.

`PATCH /avancos/{id}` com JSON ou `multipart/form-data` e `motivo` corrige uma
publicação. Aceita `descricao`, `data`, `midias_manter` (lista JSON de IDs de
mídias já vinculadas no multipart) e até cinco arquivos em `midias`. Cada correção
grava `antes`, `depois`, motivo, autor e instante no avanço, junto com o conteúdo
atual em uma transação MongoDB. Mídias de versões anteriores permanecem
armazenadas. Novos uploads são compensados se a gravação falhar; uma cadeia
inconsistente retorna 409.

A revisão usa a mesma validação de concorrência da edição de rascunhos e da
publicação. Revisões inválidas são rejeitadas, e o conteúdo usado para compor
o próximo evento vem da mesma leitura cuja revisão será comparada na gravação.

Execute sem a base de demonstração: `python -m pytest tests/test_versoes.py -q`.
Rollback após a escrita e conflito concorrente são verificados em MongoDB real
com `python -m pytest tests/test_versoes.py -m atlas --atlas -q`, em coleções
temporárias. A rede de armazenamento dos demais testes é simulada.

### Histórico de mudanças

`GET /obras/{id}/mudancas` devolve `{ "mudancas": [...] }` em ordem de instante.
A lista **inclui** decisões sobre obra e marco e cada correção de publicação.
Cada item possui `consulta` para `GET /mudancas/{id}`; correções também possuem
`comparacao` apontando para `GET /avancos/{id}/versoes`. Os campos `antes` e
`depois` vêm dos registros originais, sem alterar a trilha. Uma obra existente
sem eventos devolve lista vazia; não há PATCH ou DELETE de mudança isolada.

O desempate usa a posição numérica da decisão/correção, mantendo a sequência
mesmo com mais de dez entradas no mesmo instante. Instantes são normalizados
em UTC antes da ordenação. As correções reutilizam o leitor de versões de
UC-11: snapshot ausente, cadeia divergente ou dados obrigatórios incompletos
retornam `409 HISTORICO_INDISPONIVEL`, tanto na lista quanto no detalhe, sem
regravar registros nem transformar inconsistências em histórico vazio.

Execute com banco em memória e armazenamento simulado:
`python -m pytest tests/test_historico.py tests/test_historico_integracao.py -q`.
O teste de integração produz decisões e correções pelas rotas reais, confere a
sequência após reiniciar a aplicação e não usa a base de demonstração.
