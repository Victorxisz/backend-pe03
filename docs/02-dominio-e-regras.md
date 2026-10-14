# 2. Linguagem e modelo de domínio

Este documento descreve **o significado das informações para o negócio**. Ele orienta o código e as conversas da equipe; não determina como os documentos do MongoDB devem ser armazenados.

## Glossário compartilhado

| Termo | Significado no produto |
| --- | --- |
| Construtora | Empresa que administra obras e decide o que será publicado. Único perfil funcional do MVP. |
| Obra | Projeto residencial inteiro, como uma casa ou um edifício. No produto futuro, um comprador poderá estar vinculado à obra inteira. |
| Marco | Entrega verificável da obra, com período planejado e estado próprio. Ex.: estrutura do segundo pavimento. |
| Dependência | Relação “o marco A depende do marco B”, registrada entre marcos da mesma obra. |
| Avanço | Registro datado do trabalho em um marco, com descrição e ao menos uma mídia. Pode ser rascunho ou publicado. |
| Atualização | Avanço publicado pela construtora e exibido na prévia da linha do tempo. |
| Mudança | Alteração efetiva de um dado controlado da obra ou marco, com valor anterior, valor novo, motivo, autor e data. |
| Ocorrência | Problema ou impedimento identificado na obra, com acompanhamento de seu estado. |
| Aceitação sem solução | Ato registrado pela construtora que reconhece uma ocorrência sem solução, com justificativa. Não significa que o problema deixou de existir. |
| Registro simulado | Exemplo pré-carregado atribuído a engenheiro ou comprador para demonstrar o produto; não equivale a uma ação real desse perfil. |

Evitar alternar “etapa”, “tarefa” e “marco” para a mesma coisa. **Etapa** não é uma entidade do MVP. Usar “publicar” apenas para a transição de um avanço de rascunho a atualização.

## Mapa do domínio para DDD

| Área de negócio | Responsabilidade | Conceitos centrais | Prioridade |
| --- | --- | --- | --- |
| Planejamento da obra | Identificar a obra, planejar marcos e suas dependências | Obra, Prazo de Entrega, Marco, Dependência | Núcleo do MVP |
| Acompanhamento e publicação | Registrar evidências, revisar e publicar o andamento | Avanço, Mídia, Versão, Atualização | Núcleo do MVP |
| Decisões e impedimentos | Preservar mudanças e dar destino às ocorrências | Mudança, Ocorrência, Aceitação | Núcleo do MVP |
| Acesso e demonstração | Autenticar usuários e mostrar exemplos de outros perfis | Usuário, Perfil, Registro Simulado | Apoio ao MVP |
| Armazenamento externo | Guardar arquivos e devolver referências de acesso | Arquivo Externo | Apoio; provedor pendente |

**Proposta de desenho:** implementar essas áreas como módulos de uma aplicação Flask, sem transformá-las em serviços separados. `Obra`, `Marco`, `Avanço` e `Ocorrência` têm identidade e ciclo de vida próprios; mudanças e versões são registros históricos ligados ao objeto alterado. A escolha entre coleções e documentos incorporados pertence à implementação e deve preservar as regras abaixo.

### Fronteiras de consistência propostas

- **Obra:** controla sua identidade, modalidade de entrega e situação. Uma consulta de lista/filtros é uma visão de leitura, não outro objeto de negócio.
- **Marco:** controla período, estado e pertencimento à obra. A verificação de dependências consulta outros marcos da mesma obra; esse serviço deve impedir autorreferência e ciclos.
- **Avanço:** controla rascunho/publicação, mídias associadas e versões. Publicação e correção não devem produzir uma versão sem seu fato correspondente.
- **Ocorrência:** controla estado e aceitação sem solução. A justificativa é parte da aceitação, não um comentário opcional.
- **Mudança:** representa a decisão efetiva. Aplicar o valor novo e guardar o registro histórico é uma única operação de negócio; uma falha não pode deixar somente uma das duas partes persistida.

Essas são **fronteiras conceituais para DDD**, não uma exigência de uma coleção MongoDB ou classe por linha. Escolher a estrutura de persistência mais simples que sustente as invariantes e os casos de uso do MVP. O provedor de mídia deve ficar atrás de uma interface do servidor para não misturar detalhes externos às regras de publicação.

### Relações conceituais

```text
Construtora 1 ── * Obra
Obra        1 ── * Marco
Marco       0 ── * Dependência → outro Marco da mesma Obra
Marco       1 ── * Avanço
Avanço      1 ── * Mídia
Obra        1 ── * Ocorrência ── 0..1 Marco
Obra/Marco  1 ── * Mudança
Obra/Marco/Avanço 1 ── * Registro Simulado do Comprador
```

## Regras confirmadas

**RN-01 — Entrega da obra.** Ao criar a obra, a construtora escolhe **uma** modalidade: data exata ou intervalo estimado. A interface deve mostrar qual modalidade foi escolhida. A data de registro da obra é gerada pelo sistema para permitir o filtro solicitado.

**RN-02 — Estados exibidos da obra.** O produto deve permitir os rótulos planejada, em andamento, concluída, suspensa, crítica e atrasada, inclusive em filtros. **Proposta de modelagem:** separar ciclo de vida (`planejada`, `em andamento`, `concluída`, `suspensa`) de sinalização (`normal`, `crítica`, `atrasada`) para que uma obra possa estar em andamento e atrasada ao mesmo tempo. Validar com a equipe antes de fixar o contrato da API.

**RN-03 — Marco.** Pertence a exatamente uma obra. Tem nome, descrição, início previsto, fim previsto e estado `a iniciar`, `em andamento` ou `concluído`. A mudança de estado é manual no MVP; não se calcula percentual automático.

**RN-04 — Dependência.** Um marco pode declarar “depende de marco X”. Não pode depender de si mesmo, de marco de outra obra ou formar ciclo. Exibir o nome do marco relacionado. Bloquear a conclusão de um marco cujo pré-requisito não esteja concluído é **proposta**, ainda não regra confirmada.

**RN-05 — Avanço e publicação.** Um avanço pertence a um marco, tem data, descrição e ao menos uma mídia. Não há obrigação diária. Enquanto rascunho, a construtora pode editá-lo ou retirá-lo. Publicar muda seu estado e o inclui na prévia da linha do tempo.

**RN-06 — Correção publicada.** Uma correção não apaga o conteúdo anterior: registra versão anterior, nova versão, campos modificados, autor, data e motivo. Se o registro original vier de um engenheiro simulado, indicar claramente “editado pela construtora” e mostrar texto anterior e trecho modificado.

**RN-07 — Mudança efetiva.** Ao registrar mudança de prazo de obra, prazo de marco, estado de marco ou estado de finalização, a construtora informa motivo; a aplicação guarda antes/depois, autor e data, e aplica o valor novo. A alteração e seu histórico devem persistir juntos.

**RN-08 — Ocorrência.** Pertence a uma obra; vínculo com marco, responsável e mídia são opcionais. Pode começar `aberta` ou `sem solução` e depois mudar para qualquer estado permitido, incluindo `resolvida`. Uma aceitação de ocorrência sem solução exige justificativa e registro de quem a aceitou e quando. Medida compensatória não é obrigatória.

**RN-09 — Exclusão.** A exclusão definitiva foi escolhida para o MVP. Ela precisa ser explícita na interface. **Pendente:** política para excluir uma obra ou marco que ainda possua filhos ou histórico. A proposta segura é responder conflito e solicitar remoção explícita dos vínculos, evitando registros órfãos e exclusões em cascata acidentais.

**RN-10 — Dados simulados.** Dois usuários reais da construtora podem entrar. Registros atribuídos a comprador ou engenheiro são pré-carregados e sinalizados como simulação. A construtora apenas lê avaliações, compreensão e dúvidas simuladas do comprador; esses exemplos podem se vincular à obra, ao marco ou a uma atualização específica.

## Eventos de negócio úteis

Estes nomes descrevem fatos que devem aparecer no histórico; **não exigem event sourcing**:

`ObraCriada`, `MarcoCriado`, `DependenciaDefinida`, `AvancoRegistrado`, `AtualizacaoPublicada`, `AtualizacaoCorrigida`, `MudancaAplicada`, `OcorrenciaRegistrada`, `OcorrenciaResolvida`, `OcorrenciaSemSolucaoAceita`.

## Questões de modelagem ainda abertas

- O estado `atrasada` será acionado manualmente, calculado após a data final do prazo ou ambos? Para intervalo estimado, usar o fim do intervalo é a proposta.
- “Alteração de estado de finalização” significa reverter a conclusão de obra, de marco ou de ambos? Registrar em `Mudança` até a equipe fechar o detalhe.
- Qual o efeito de uma dependência não concluída sobre a conclusão do marco dependente?
- Como tratar a exclusão definitiva de objetos com filhos e históricos? A regra proposta em RN-09 evita exclusões involuntárias.
- Uma ocorrência resolvida pode ser reaberta? O usuário permitiu mudança posterior para qualquer estado; a proposta é registrar cada transição no histórico.
