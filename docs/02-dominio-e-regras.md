# 2. Linguagem e modelo de domínio

Este documento descreve **o significado das informações para o negócio**. Ele orienta o código e as conversas da equipe; não determina como os documentos do MongoDB devem ser armazenados.

## Glossário compartilhado

| Termo | Significado no produto |
| --- | --- |
| Construtora | Empresa que administra obras e decide o que será publicado. Único perfil funcional do MVP. |
| Cliente de referência | Nome do comprador ligado à obra inteira; há um por obra no MVP e não corresponde a uma conta de acesso. |
| Obra | Projeto residencial inteiro, como uma casa ou um edifício, com um cliente de referência no MVP. |
| Trabalhador | Pessoa cadastrada pela construtora e vinculável a obras; não possui login no MVP. |
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
| Acesso e demonstração | Autenticar a construtora, cadastrar trabalhadores e mostrar exemplos de outros perfis | Usuário, Trabalhador, Registro Simulado | Apoio ao MVP |
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
Construtora 1 ── * Trabalhador
Obra        * ── * Trabalhador (vínculo cadastrado pela construtora)
```

## Regras confirmadas

**RN-01 — Entrega da obra.** Ao criar a obra, a construtora escolhe **uma** modalidade: data exata ou intervalo estimado. A interface deve mostrar qual modalidade foi escolhida. A data de registro da obra é gerada pelo sistema para permitir o filtro solicitado.

**RN-02 — Estado e alerta de atraso.** O ciclo de vida (`planejada`, `em andamento`, `concluída`, `suspensa`) é distinto do único alerta `atrasada`. Crítica e atrasada foram unificadas por decisão do grupo em 30/10/2026. O atraso é calculado somente após a data exata ou o fim do intervalo estimado; não pode ser marcado manualmente. A conclusão registra automaticamente a data efetiva no servidor, usada no cálculo histórico do atraso. Uma reabertura limpa a conclusão atual e preserva a anterior no histórico.

**RN-03 — Marco.** Pertence a exatamente uma obra. Tem nome, descrição, início previsto, fim previsto e estado `a iniciar`, `em andamento` ou `concluído`. A mudança de estado é manual no MVP; não se calcula percentual automático.

**RN-04 — Dependência.** Um marco pode declarar “depende de marco X”. Não pode depender de si mesmo, de marco de outra obra ou formar ciclo. Exibir o nome do marco relacionado. Se a construtora concluir o marco com pré-requisito não concluído, o sistema avisa, mas não impede a conclusão.

**RN-05 — Avanço e publicação.** Um avanço pertence a um marco, tem data, descrição e ao menos uma mídia. Não há obrigação diária. Enquanto rascunho, a construtora pode editá-lo ou retirá-lo. Publicar muda seu estado e o inclui na prévia da linha do tempo.

**RN-06 — Correção publicada.** Uma correção não apaga o conteúdo anterior: registra versão anterior, nova versão, campos modificados, autor, data e motivo. Se o registro original vier de um engenheiro simulado, indicar claramente “editado pela construtora” e mostrar texto anterior e trecho modificado.

**RN-07 — Mudança efetiva.** Ao registrar mudança de prazo de obra, prazo de marco, estado de marco ou estado de finalização, a construtora informa motivo; a aplicação guarda antes/depois, autor e data, e aplica o valor novo. A alteração e seu histórico devem persistir juntos. Obra e marco concluídos podem ser reabertos com motivo registrado.

**RN-08 — Ocorrência.** Pertence a uma obra; vínculo com marco, responsável e mídia são opcionais. O responsável, quando informado, é um trabalhador cadastrado. Pode começar `aberta` ou `sem solução` e depois mudar para qualquer estado permitido, incluindo `resolvida`. Uma ocorrência pode ter várias aceitações preservadas no histórico. Uma aceitação de ocorrência sem solução exige justificativa e registro de quem a aceitou e quando. Medida compensatória não é obrigatória.

**RN-09 — Exclusão.** A exclusão definitiva de obra ou marco remove junto todos os registros dependentes, inclusive histórico e dados simulados associados. Antes da ação a interface mostra o nome do alvo, a extensão da perda e pede confirmação. Nenhuma referência órfã pode permanecer. Exclusão isolada de mudança já aplicada não faz parte do fluxo definido: sua retirada sem reverter o valor destruiria a explicação histórica.

**RN-10 — Dados simulados.** Uma conta da construtora pode entrar. Registros atribuídos a comprador ou engenheiro são pré-carregados e sinalizados como simulação. A construtora apenas lê avaliações, compreensão e dúvidas simuladas do comprador; esses exemplos podem se vincular à obra, ao marco ou a uma atualização específica.

## Eventos de negócio úteis

Estes nomes descrevem fatos que devem aparecer no histórico; **não exigem event sourcing**:

`ObraCriada`, `MarcoCriado`, `DependenciaDefinida`, `AvancoRegistrado`, `AtualizacaoPublicada`, `AtualizacaoCorrigida`, `MudancaAplicada`, `OcorrenciaRegistrada`, `OcorrenciaResolvida`, `OcorrenciaSemSolucaoAceita`.

## Questões de modelagem ainda abertas

- Quais estados adicionais de ocorrência serão exibidos além de `aberta`, `resolvida` e `sem solução`? A transição é reversível e deve preservar o histórico.
- Qual formato e limite de mídia o provedor gratuito escolhido permite?
- Qual tratamento técnico garante remoção consistente de arquivos externos em exclusões em cascata?

## Organização implementada

Ver [modelo com POO e decisões de 30/10](13-modelo-poo.md). Ao excluir marco, suas ocorrências também são excluídas; responsáveis são trabalhadores. Cadastro, edição, transições, aceitações e exclusão completa estão implementados. UC-17/18 usam transação para os documentos e diário durável para a limpeza externa; somente respondem sucesso após concluir a limpeza. Excluir trabalhador ou retirá-lo da obra preserva as ocorrências e remove a responsabilidade inválida, mantendo aceitações e histórico. O [contrato UC-15](05-arquitetura-e-contratos.md#atualização-de-ocorrências--uc-15) distingue aceitações históricas das decisões do episódio atual.
