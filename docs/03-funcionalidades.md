# 3. Catálogo de funcionalidades

Este catálogo descreve **o que o usuário consegue fazer e por quê**. `P0` compõe a demonstração obrigatória; `P1` melhora o MVP, mas não pode atrasar o fluxo principal. Uma linha `F-xx` deve poder virar uma ou mais tarefas pequenas no GitHub.

## Acesso e visão das obras

| ID | Prioridade | Funcionalidade | Resultado para a construtora |
| --- | --- | --- | --- |
| F-01 | P0 | Entrar e sair com a conta pré-configurada da construtora | Ações ficam atribuídas à construtora autenticada; visitante não vê as obras. |
| F-02 | P0 | Criar obra residencial | Estabelece o lugar único para marcos, avanços, decisões e ocorrências. |
| F-03 | P0 | Listar e abrir obras | Permite administrar mais de uma obra sem misturar informações. |
| F-04 | P0 | Filtrar obras por nome, estado, cliente, data de entrega e data de registro | Localiza rapidamente a obra e expõe atrasos e prioridades. |
| F-05 | P1 | Editar dados descritivos da obra | Corrige cadastro; mudança de prazo deve seguir F-12. |

**Dados mínimos da obra:** identificador, nome, tipo residencial (`casa` ou `apartamentos`), localização/endereço, descrição, início, modalidade e valor do prazo de entrega, cliente de referência para filtro, estado, data de registro e autor. `Cliente de referência` pode ser um nome fictício pré-carregado no MVP; não cria login de comprador.

**Prazo:** `data_exata` armazena um dia; `intervalo_estimado` armazena início e fim. Não preencher os dois formatos simultaneamente. O nome e a descrição podem evoluir depois da criação.

## Marcos e avanço da obra

| ID | Prioridade | Funcionalidade | Resultado para a construtora |
| --- | --- | --- | --- |
| F-06 | P0 | Criar, listar e consultar marcos de uma obra | Organiza entregas verificáveis e suas datas planejadas. |
| F-07 | P0 | Editar estado de marco e registrar dependência “depende de marco X” | Torna explícita a sequência de execução. |
| F-08 | P0 | Registrar avanço em um marco com descrição e foto, vídeo ou documento | Guarda evidência vinculada ao trabalho, com frequência livre. |
| F-09 | P0 | Editar avanço em rascunho | Permite revisar a informação antes da publicação. |
| F-10 | P0 | Publicar avanço e consultar prévia da linha do tempo | Mostra exatamente qual informação foi liberada. |
| F-11 | P0 | Corrigir avanço publicado com versão anterior, autor, data, motivo e campos alterados | Mantém confiança no histórico, inclusive quando a construtora altera um registro simulado do engenheiro. |

**Dados mínimos do marco:** identificador, obra, nome, descrição, início/fim previstos, estado e zero ou mais dependências. Não há responsável obrigatório nem data real de conclusão no recorte confirmado.

**Dados mínimos do avanço:** identificador, marco, data do trabalho, descrição, mídias vinculadas, estado (`rascunho`/`publicado`), autor, data da publicação quando houver e versões posteriores. Cada mídia precisa registrar tipo, nome, referência ao arquivo e dados suficientes para exibição segura.

## Mudanças e ocorrências

| ID | Prioridade | Funcionalidade | Resultado para a construtora |
| --- | --- | --- | --- |
| F-12 | P0 | Registrar e aplicar mudança de prazo ou estado com motivo e antes/depois | Uma decisão altera o planejamento sem perder a explicação. |
| F-13 | P0 | Consultar histórico de mudanças da obra e dos marcos | Permite responder “o que mudou, quando e por quem?”. |
| F-14 | P0 | Registrar ocorrência ligada à obra e opcionalmente a um marco | Impedimentos deixam de existir apenas em conversas. |
| F-15 | P0 | Mudar estado da ocorrência e aceitar formalmente uma sem solução | Toda ocorrência pode ter encaminhamento rastreável. |
| F-16 | P1 | Editar dados descritivos da ocorrência | Corrige informações sem confundir edição com mudança de estado. |
| F-19 | P0 | Excluir definitivamente obra ou marco e todos os registros dependentes; excluir avanço ou ocorrência quando solicitado | Avisa o usuário antes da perda e evita registros órfãos. Mudança aplicada não é excluída isoladamente. |
| F-20 | P0 | Cadastrar, consultar, editar e excluir trabalhadores e seus vínculos com obras | Permite à construtora saber quem participa de cada obra, sem login de trabalhador no MVP. |

**Tipos de mudança confirmados:** prazo de obra, prazo de marco, situação de marco e estado de finalização. Em todos: objeto alvo, campo, valor anterior, valor novo, motivo, autor e data. A aplicação não deve aceitar um histórico que afirme um valor novo sem que esse valor seja aplicado.

**Dados mínimos da ocorrência:** identificador, obra, título, descrição, data de registro, estado e autor. Marco, foto/vídeo/documento e responsável são opcionais. Para `sem solução — aceita`, registrar justificativa, pessoa que aceitou e data da aceitação. A medida compensatória pode ser registrada, mas não exigida.

**Trabalhador no MVP:** nome, email, telefone, cargo, estado ativo, data de cadastro e vínculos com obras. O cadastro já iniciado no servidor não substitui login nem a autorização da construtora; listagem, validação de obra existente e integração com a interface ainda precisam ser concluídas.

## Dados simulados e transparência

| ID | Prioridade | Funcionalidade | Resultado para a demonstração |
| --- | --- | --- | --- |
| F-17 | P0 | Mostrar exemplos pré-carregados de avaliação, compreensão e dúvida de comprador | Testa se a organização da informação responde a necessidades do cliente, sem implementar seu perfil. |
| F-18 | P0 | Mostrar avanço pré-carregado atribuído a engenheiro, com indicação das edições feitas pela construtora | Demonstra a futura colaboração e a origem das informações sem fingir interação real. |

Registros simulados devem ter identificação visual e campo de origem no banco (`simulado`), além de vínculo à obra, ao marco ou à atualização específica. **Nenhum** formulário de criação de engenheiro ou comprador é necessário no MVP.

## Funcionalidades posteriores ao MVP

Estas capacidades pertencem à visão de produto, mas não às entregas `P0` ou `P1`:

| Área | Funcionalidade futura | Relação com o MVP |
| --- | --- | --- |
| Portal do comprador | Login, visão apenas da própria obra e conteúdo publicado | Reutiliza obras, marcos e atualizações. |
| Participação do comprador | Comentários quando permitidos e confirmação de ciência sobre mudanças importantes | Reutiliza histórico; confirmação de ciência não equivale a aprovação contratual. |
| Perfil do engenheiro | Registrar avanços, anexar mídias e propor alterações | Reutiliza rascunhos, mudanças e autoria. |
| Demais trabalhadores | Acesso apenas às obras vinculadas, com permissões administradas pela construtora | Exige regras de acesso configuráveis. |
| Administração | Vínculos entre pessoas e obras; configuração de aprovação e evidências obrigatórias | Expande o controle de publicação. |
| Comunicação | Mensagens e possível integração com WhatsApp | Complementa registros, sem substituí-los. |
| Documentos | Contratos, plantas e arquivos com visibilidade por perfil; indicar ao comprador quando existir conteúdo restrito | Expande mídia para acervo documental e dá transparência sobre limites de acesso. |
| Organização de mídias | Filtros por data, marco, ambiente e unidade quando houver | Facilita encontrar o histórico de uma parte específica da construção. |
| Planejamento | Tarefas, responsáveis, metas e prazos; agrupamento avançado de obras | Usa obra e marco como referência. |
| Pós-entrega | Área do comprador com documentação e acompanhamento adequado à fase posterior | Exige ciclo de vida próprio. |
| Inteligência operacional | Alertas, análises e estimativas de prazo fundamentadas | Requer dados históricos suficientes; evitar percentual artificial. |

## Dependências entre funcionalidades

`F-01 → F-02 → F-06 → F-08 → F-10` é a primeira trilha de implementação. `F-12` e `F-14` usam obra e marco já persistidos. `F-11` depende da publicação. `F-17` e `F-18` dependem de dados de exemplo vinculados a registros existentes. `F-19` exige exclusão em cascata confirmada; `F-20` depende da existência da obra. [O plano de entrega](07-plano-e-decisoes.md) transforma essa ordem em checkpoints.
