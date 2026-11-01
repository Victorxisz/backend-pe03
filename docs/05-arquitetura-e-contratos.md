# 5. Arquitetura e contrato inicial da API

Este é um **contrato de trabalho proposto** para que cliente e servidor possam avançar em paralelo. Rotas e campos devem ser revisados juntos antes de virar código; as regras de negócio dos documentos anteriores têm precedência sobre exemplos técnicos aqui.

## Fronteiras e entrega

```text
Navegador (React)
       │ HTTP/JSON
       ▼
Servidor (Flask, EC2) ─────► MongoDB Atlas
       │
       └────────────────────► API(s) externa(s) escolhida(s)
```

- **Dois repositórios:** um para React, outro para Flask. A documentação de produto pode ficar neste repositório e ser referenciada pelo outro.
- **Um servidor lógico Flask:** módulos de obras, marcos, avanços, mudanças, ocorrências e autenticação; não há necessidade de microsserviços.
- **Dados de domínio no Atlas:** nunca assumir que um estado React ou um arquivo local é a fonte persistente.
- **Mídias:** guardar metadados e referências no Atlas; o local dos arquivos depende da integração escolhida. O acesso aos arquivos deve respeitar o login, inclusive quando o link é aberto fora da interface.
- **Implantação:** cliente React e API Flask acessíveis no EC2. A equipe deve decidir o domínio, processo de execução e configuração de rede antes do deploy. O ambiente publicado deve usar as mesmas regras de negócio do ambiente local.

O Flask documenta *blueprints* e *application factories* para organizar componentes e inicializar a aplicação; o PyMongo é o driver oficial para conexão Python–Atlas. [Flask — blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) · [Flask — factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) · [MongoDB — PyMongo](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/get-started/).

## Nível 2 de Richardson

Cada recurso tem URI própria. `GET` consulta, `POST` cria, `PATCH` modifica e `DELETE` remove quando permitido. Retornar códigos HTTP que expressem o resultado, em vez de responder `200` para todo caso: `201` na criação, `204` em exclusão sem corpo, `400/422` para dados inválidos, `401` sem autenticação, `403` sem permissão, `404` quando não encontrado e `409` em conflito de estado ou dependência. Essa é a característica central do nível 2 descrita por [Martin Fowler](https://martinfowler.com/articles/richardsonMaturityModel.html).

### Recursos propostos

As rotas usam diretamente os caminhos dos recursos, sem prefixo de versão ou
aliases. Para obras, a coleção usa `/obras` e uma obra específica usa
`/obras/{obraId}`; os métodos HTTP distinguem as operações. Identificadores são
opacos para o cliente; o React não deve depender do formato interno `_id` do MongoDB.

| Recurso | Métodos previstos | Funcionalidade |
| --- | --- | --- |
| `/sessoes` e `/sessoes/atual` | `POST`, `GET`, `DELETE` | F-01 |
| `/obras` e `/obras/{obraId}` | `GET`, `POST`, `PATCH`, `DELETE` | F-02 a F-05, F-19 |
| `/obras/{obraId}/marcos` e `/marcos/{marcoId}` | `GET`, `POST`, `PATCH`, `DELETE` | F-06, F-07, F-19 |
| `/marcos/{marcoId}/dependencias` e `/marcos/{marcoId}/dependencias/{dependenciaId}` | `GET`, `POST`, `DELETE` | F-07 |
| `/marcos/{marcoId}/avancos` e `/avancos/{avancoId}` | `GET`, `POST`, `PATCH`, `DELETE` | F-08, F-09, F-19 |
| `/avancos/{avancoId}/midias` e `/midias/{midiaId}` | `GET`, `POST`, `DELETE` | F-08, F-19 |
| `/avancos/{avancoId}/publicacoes` | `GET`, `POST` | F-10; publicação é um fato registrado |
| `/avancos/{avancoId}/versoes` | `GET` | F-11; correções são enviadas em `PATCH /avancos/{id}` com motivo |
| `/obras/{obraId}/mudancas` e `/mudancas/{mudancaId}` | `GET`, `POST` | F-12, F-13; sem exclusão isolada no MVP |
| `/obras/{obraId}/ocorrencias` e `/ocorrencias/{ocorrenciaId}` | `GET`, `POST`, `PATCH`, `DELETE` | F-14 a F-16, F-19 |
| `/ocorrencias/{ocorrenciaId}/aceitacoes` | `GET`, `POST` | F-15 |
| `/obras/{obraId}/previa` | `GET` | F-10; apenas avanços publicados |
| `/obras/{obraId}/feedback-simulado` | `GET` | F-17; leitura apenas |
| `/trabalhadores/obra/{obraId}/` e `/trabalhadores/{trabalhadorId}/` | `GET`, `POST`, `PATCH`, `DELETE` | F-20; caminhos implementados em UC-19/UC-20, com barra final. A proposta `/obras/{obraId}/trabalhadores` **não** foi implementada; o contrato real está no [README](../README.md#trabalhadores-da-obra--uc-19) |

Excluir isoladamente uma mudança já aplicada não integra o MVP; sua exclusão por cascata ocorre somente com o objeto principal e seus dependentes, após confirmação explícita na interface. O servidor deve garantir que uma falha não produza referências órfãs. Ver [decisões](07-plano-e-decisoes.md).

`DELETE /obras/{obraId}` e `DELETE /marcos/{marcoId}` estão implementados em
UC-17. O contrato — protocolo de confirmação com o React, corpo
`{"confirmar": true}` validado no servidor, códigos de resposta, o que a cascata
remove e as pendências de limpeza externa — está no
[README](../README.md#uc-17--excluir-obra-ou-marco-com-os-dependentes-ct-79-a-ct-85-ct-100).
Duas políticas da cascata seguem como proposta a confirmar (P-08 e P-09).

### Convenções compartilhadas

O contrato implementado de `POST /obras/{obraId}/mudancas` (UC-12), incluindo
versão obrigatória, campos por alvo, confirmação de dependências, armazenamento
atômico e data efetiva de conclusão, está no [README](../README.md#replanejamento-e-situação--uc-12).
Os métodos `GET` de mudanças estão implementados em UC-13; o contrato de
listagem unificada, comparação e inconsistências está no
[README](../README.md#histórico-de-mudanças).

- `GET /obras` aceita filtros por `nome`, `estado`, `alerta`, `cliente`, `entregaDe`, `entregaAte`, `registroDe` e `registroAte`, combinados por interseção. `alerta=atrasada` é derivado do prazo e da conclusão efetiva, separado do ciclo de vida (D-13). Os intervalos são inclusivos; registro usa o dia em UTC e entrega estimada usa o fim do intervalo. Filtros repetidos ou inválidos retornam `422` antes da consulta.
- Datas de dia usam `AAAA-MM-DD`; instantes de auditoria usam formato ISO 8601 com fuso explícito.
- Uma criação retorna `201 Created`, a representação criada e `Location` com sua URI.
- Mensagem de erro usa estrutura estável, por exemplo `{ "codigo": "PRAZO_INVALIDO", "mensagem": "O fim do intervalo deve ser posterior ao início.", "campos": ["entrega.fim"] }`.
- Todas as rotas que alteram dados validam autenticação no servidor. O React pode esconder botões, mas isso não substitui autorização na API.
- Paginação, ordenação e tamanho máximo de arquivos devem ser fechados antes de integrar grandes listas e vídeos; os valores podem ser modestos no MVP.

### Cadastro de obra — contrato implementado

`POST /obras` exige token de acesso em
`Authorization: Bearer <token>`. Os campos obrigatórios são `nome`, `tipo`,
`cliente`, `localizacao`, `descricao`, `inicio` e `entrega`. Os textos devem ser
não vazios; `tipo` aceita `casa` ou `apartamentos`.

O servidor gera `autor` com o ID da construtora autenticada e `data_registro`
com o instante UTC, além de iniciar `estado` como `planejada`. O único alerta,
`atrasada`, é derivado do prazo e não é armazenado como campo editável.
Campos controlados pelo servidor e campos desconhecidos são rejeitados no corpo
da requisição. Os nomes antigos `cliente_referencia` e `criado_em` não fazem
parte deste contrato; usar `cliente` e `data_registro`, respectivamente.

A criação retorna `201`, os dados persistidos, `id` textual e `Location` com
`/obras/{id}`. Dados inválidos, inclusive JSON malformado,
retornam `422` com `mensagem` e `campos`; falha de gravação retorna `500` com
`mensagem`. A consulta GET da URI indicada em `Location` está implementada e
retorna o cadastro persistido com os alertas calculados no servidor.

Exemplo de corpo:

```json
{
  "nome": "Residencial Aurora",
  "tipo": "apartamentos",
  "cliente": "Cliente de referência",
  "localizacao": "Campinas, SP",
  "descricao": "Construção residencial",
  "inicio": "2026-10-15",
  "entrega": {
    "modalidade": "intervalo_estimado",
    "inicio": "2027-06-01",
    "fim": "2027-08-31"
  }
}
```

Quando a modalidade for `data_exata`, `entrega` contém somente `modalidade` e
`data`. Em `intervalo_estimado`, contém somente `modalidade`, `inicio` e `fim`;
o fim não pode ser anterior ao início (o mesmo dia é aceito). Todas as datas
devem ser dias existentes em `AAAA-MM-DD`. Não é permitido misturar as modalidades.

## Atualização de ocorrências — UC-15

`PATCH /ocorrencias/{ocorrenciaId}` exige sessão de construtora ativa e
`Content-Type: application/json`. O comando separa a edição descritiva da
transição. A `versao` inteira não negativa vem da consulta atual da ocorrência:

```json
{
  "versao": 0,
  "alteracoes": {"titulo": "Infiltração na fachada"},
  "transicao": {"estado": "resolvida", "motivo": "Reparo e inspeção concluídos"}
}
```

Informe `alteracoes`, `transicao` ou ambos. `alteracoes` aceita somente os campos
enviados de `titulo`, `descricao`, `marco_id` e `responsavel_id`; deve ser um
objeto não vazio. Título e descrição exigem texto preenchido. Os vínculos
opcionais aceitam `null` ou texto vazio para retirada. Marco informado deve
pertencer à obra; responsável deve ser trabalhador cadastrado, vinculado à
mesma obra e compatível com a construtora autenticada. Obra, autoria, registro,
mídias, aceitações e histórico não são editáveis por este comando.

`transicao` exige `estado` e `motivo` preenchido. Os únicos estados permitidos
são `aberta`, `resolvida` e `sem solução`; qualquer mudança entre eles é
permitida, inclusive resolução posterior de ocorrência aceita e reabertura.
Estado não pode ser enviado em `alteracoes` nem na raiz. Autoria, ID e instante
UTC do evento são gerados pelo servidor. Edição descritiva não muda estado nem
acrescenta transição. Pedidos válidos sem mudança efetiva retornam o registro
atual sem novo evento ou incremento de versão; a versão ainda deve coincidir.

Sucesso retorna `200` com a ocorrência atualizada. `GET /ocorrencias/{id}` e a
lista da obra incluem `versao`, `episodio` e `historico_estados`, em ordem de
gravação. Cada evento possui `id`, `estado_anterior`, `novo_estado`, `motivo`,
`autor`, `instante`, `episodio_anterior` e `episodio`. A ordem do array preserva
a sequência mesmo quando os instantes são iguais. Registros anteriores à UC-15
começam na versão e episódio `0`, sem inventar eventos históricos.

Estado, edição e append do evento são persistidos em **uma atualização atômica**
de `tbl_ocorrencias`, condicionada ao estado e à versão lidos. Cada alteração
efetiva incrementa `versao`. Versão desatualizada ou disputa durante a gravação
retorna `409`; o cliente deve consultar novamente e reapresentar sua decisão.
Não há sobrescrita silenciosa nem gravação separada no histórico da obra.
`episodio` incrementa apenas numa transição de estado; é um identificador de
contexto da decisão, não um novo estado de negócio.

`aceitacoes` continua sendo o histórico completo e imutável de decisões da
UC-16. Novas aceitações recebem o `episodio` lido e são anexadas somente se
esse episódio ainda estiver em `sem solução`. `aceitacoes_do_estado_atual`
contém somente as decisões desse episódio enquanto o estado for `sem solução`;
fica vazio após resolver/reabrir ou retornar a `sem solução` em outro episódio.
Aceitações legadas sem episódio são do episódio `0`. Reenviar a mesma chave
`Idempotency-Key` com os mesmos textos devolve a decisão original, sem aceitar
um episódio novo; outro conteúdo com a mesma chave retorna conflito.
As consultas e o registro de aceitação verificam também o contexto da obra.

IDs malformados retornam `400`; ocorrência, obra ou vínculo não encontrado ou
inacessível, `404`; formato de corpo não suportado, `415`; dados inválidos,
`422`; falha de banco, `503`. Uma rejeição do banco mantém todos os valores
anteriores. Em timeout de resultado desconhecido, consulte antes de tentar
novamente: a atualização inteira pode ter sido confirmada; estado e trilha
nunca são gravados separadamente. Os erros não anunciam sucesso.

Testes CT-69 a CT-73 e CT-03:
`python -m pytest tests/test_atualizacao_ocorrencias.py -q`.
Os cenários `-m atlas --atlas` comprovam a disputa entre duas requisições no
MongoDB real e a releitura de transições e aceitações em outro processo, usando
somente as coleções temporárias isoladas da execução.

## Aceitar ocorrência sem solução — UC-16

`POST /ocorrencias/{ocorrenciaId}/aceitacoes` recebe `application/json` e exige
sessão de construtora ativa. A ocorrência e seu contexto devem existir e estar
acessíveis. Ocorrência sem vínculo com obra também retorna `404`, tanto no
detalhe quanto no registro e na consulta de aceitações. O corpo aceita somente:

```json
{
  "justificativa": "Limitação técnica constatada; manteremos acompanhamento.",
  "medida_compensatoria": null
}
```

`justificativa` deve ser texto não vazio. `medida_compensatoria` pode ser omitida
ou `null`; quando informada como texto, deve estar preenchida. Os textos são
aparados. ID da aceitação, autoria da conta autenticada, instante UTC em `data`
e episódio são gerados pelo servidor; campos enviados para forjá-los são
rejeitados. Uma aceitação é uma nova decisão, sem mudar `estado`, título,
descrição, versão, mídia ou histórico de transições da ocorrência.

O backend usa a ocorrência lida na validação como contexto esperado da escrita.
A aceitação é anexada atomicamente em `aceitacoes`, condicionada a `estado:
sem solução` e ao mesmo `episodio`. Se uma transição acontecer nesse intervalo,
inclusive resolver e retornar a `sem solução`, a decisão antiga não é gravada
no episódio novo. Uma disputa pode terminar com a aceitação antes da resolução,
preservada como histórica, ou com `409` após a resolução. Nenhum quarto estado
é criado. Novas decisões em `aberta` ou `resolvida` retornam `409`.

**Reenvio:** a interface deve gerar uma `Idempotency-Key` para cada confirmação
explícita e reutilizá-la em todo retry, inclusive após timeout ou reinício.
Use UUID ou outra chave de 1 a 128 caracteres ASCII, começando por letra ou
número; os demais caracteres podem incluir `.`, `_`, `:` e `-`. Cabeçalho
presente mas vazio ou inválido retorna `422`, sem criar uma decisão.

A primeira gravação retorna `201`. Mesma chave, mesmos textos normalizados e
mesma autoria retornam `200` com a decisão original, incluindo o mesmo ID e
instante, sem duplicar. Mesma chave com outro conteúdo retorna `409`; nenhuma
aceitação anterior é sobrescrita. Uma decisão nova exige chave nova. Sem o
cabeçalho, cada POST válido representa uma decisão nova, inclusive se o texto
for igual; não use essa modalidade para retries automáticos.

Repetir uma chave antiga após resolver ou reabrir devolve a decisão histórica,
sem aceitar o estado atual nem um episódio novo. Isso é uma consulta do
resultado anterior, sem escrita; uma chave nova ainda exige estado atual
`sem solução`. O filtro de chave na própria atualização do documento impede
duplicação também em requisições simultâneas. Chaves distintas preservam as
duas decisões válidas em vez de substituir uma pela outra.

`GET /ocorrencias/{ocorrenciaId}/aceitacoes` retorna um array de decisões em
ordem de gravação, vazio quando nenhuma foi registrada. Cada nova aceitação
contém `id`, `justificativa`, `autor`, `data`, `episodio` e, quando informados,
`medida_compensatoria` e `chave_reenvio`. O POST inclui `Location` para essa
consulta. Registros antigos sem ID/episódio mantêm seus dados originais; não se
inventam autoria ou instantes. O detalhe da ocorrência também devolve todas
as `aceitacoes` históricas e, separadamente, `aceitacoes_do_estado_atual`.
Resolver/reabrir preserva o array histórico, sem reaplicar decisões antigas.

IDs inválidos retornam `400`; ocorrência/contexto inexistente ou inacessível,
`404`; estado/episódio incompatível ou chave usada com outro conteúdo, `409`;
formato não suportado, `415`; campos/chave inválidos, `422`; banco indisponível,
`503`. A leitura com falha não devolve lista vazia. Um timeout pode ocorrer
depois da gravação; reenviar a mesma chave confirma o resultado sem duplicar.
Respostas são protegidas por sessão e `Cache-Control: private, no-store`.

CT-74 a CT-78, CT-73, autenticação e falhas:
`python -m pytest tests/test_aceitacao_ocorrencias.py -q`.
Persistência em outro processo e concorrência no MongoDB real:
`python -m pytest tests/test_aceitacao_ocorrencias.py -m atlas --atlas -q`.
Os testes reais usam e removem apenas as coleções temporárias isoladas da
execução; UC-16 não precisa de chamadas ao serviço de mídia.

## Segurança e configuração

- Manter URI do Atlas, segredos da sessão, credenciais da API externa e credenciais de AWS em variáveis de ambiente do servidor; nunca no código React, no Git ou em exemplos reais.
- Versionar apenas `.env.example` com nomes de variáveis e valores fictícios. Os arquivos reais de credenciais serão entregues pelo Blackboard conforme a exigência da disciplina.
- Proteger a conta de demonstração com senha não exposta no repositório. Dados simulados devem usar pessoas e obras fictícias.
- Não expor o Atlas diretamente ao navegador. Configurar o acesso de rede para que o servidor no EC2 consiga conectar ao cluster.
- Se o cliente e a API usarem origens diferentes, configurar CORS apenas para a origem do cliente implantado; preferir uma origem única se isso simplificar a implantação.
- A documentação da AWS descreve *security groups* como controle de tráfego da instância. Abrir apenas as portas exigidas pelo serviço publicado e pela administração autorizada. [AWS EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html).

## Testes mínimos com valor

1. Regras de prazo exato/intervalo e dependências sem ciclo.
2. Publicação não expõe rascunho na prévia.
3. Correção publicada preserva versão anterior.
4. Mudança atualiza valor e histórico em conjunto.
5. Ocorrência sem solução não pode ser aceita sem justificativa.
6. Usuário sem sessão não modifica nem lê obras pela API.
7. Integração React → Flask → Atlas funciona no EC2 com mídia recuperável.

Esses testes cobrem riscos reais do produto; não precisam replicar cada linha de implementação.

## Refatoração com POO e conclusão de obra

A organização efetiva e o contrato `PATCH /obras/{id}/estado` estão em [modelo com POO](13-modelo-poo.md). A conclusão registra a data do servidor e mantém histórico junto ao estado.
