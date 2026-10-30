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
| `/obras/{obraId}/trabalhadores` e `/trabalhadores/{trabalhadorId}` | `GET`, `POST`, `PATCH`, `DELETE` | F-20; a rota existente no código ainda usa outro formato e precisa convergir para o contrato escolhido |

Excluir isoladamente uma mudança já aplicada não integra o MVP; sua exclusão por cascata ocorre somente com o objeto principal e seus dependentes, após confirmação explícita na interface. O servidor deve garantir que uma falha não produza referências órfãs. Ver [decisões](07-plano-e-decisoes.md).

### Convenções compartilhadas

- `GET /obras` aceita filtros por `nome`, `estado`, `cliente`, `entregaDe`, `entregaAte`, `registroDe` e `registroAte`. Definir o significado de cada intervalo antes de implementar os filtros.
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
`mensagem`. Consulta GET da URI indicada em `Location` continua pendente.

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
