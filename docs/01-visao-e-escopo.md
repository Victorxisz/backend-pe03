# 1. Visão do produto e limite do MVP

**Estado:** proposta de documentação baseada nas decisões do grupo até 14/10/2026.

**Prazo do MVP:** 03/11/2026.

## Problema e promessa

Em obras residenciais, informações sobre avanço, decisões e impedimentos podem ficar dispersas em conversas e arquivos. Isso dificulta para a construtora reconstruir o que ocorreu, explicar mudanças e mostrar progresso ao comprador. A hipótese do produto é que um histórico único, ligado a marcos verificáveis e acompanhado por evidências, reduza perda de contexto, retrabalho e tempo gasto preparando atualizações.

O comprador é beneficiário importante do produto futuro, mas **não terá fluxo funcional no MVP**. A primeira versão deve provar que a construtora consegue produzir um registro confiável da obra e preparar informações para publicação.

## Para quem

- **Cliente que pode contratar o produto:** construtora pequena ou média, inicialmente com obras residenciais de casas e apartamentos.
- **Usuário funcional do MVP:** pessoa da construtora autenticada; duas contas pré-configuradas bastam para a demonstração.
- **Participantes representados por dados simulados:** engenheiro e comprador. Dados de avaliação, compreensão e dúvida do comprador são exemplos pré-carregados, nunca apresentados como respostas reais.
- **Usuários futuros:** comprador, engenheiro, arquiteto, encarregado, pedreiro e outros participantes vinculados à obra.

## Recorte demonstrável

`criar obra → definir marcos → registrar avanço com foto/vídeo/documento → publicar atualização → registrar mudança e ocorrência com histórico persistente`

O sistema deve permitir listar e filtrar obras, registrar dependências entre marcos, mostrar uma prévia da linha do tempo publicada e consultar o histórico após reiniciar a aplicação. A interface deve deixar claro o que é rascunho, o que foi publicado, o que foi alterado e o que é dado simulado.

## O que torna a solução valiosa

| Dor observada | Capacidade do produto | Evidência de valor a demonstrar |
| --- | --- | --- |
| O andamento é comunicado de modo informal | Marcos ligados a avanços e mídias | Uma pessoa encontra rapidamente o último avanço e sua evidência |
| Mudanças ficam sem contexto | Registro de antes/depois, motivo, autor e data | A construtora consegue explicar por que um prazo mudou |
| Impedimentos desaparecem da conversa | Ocorrências com estado e aceitação explícita quando não há solução | Uma ocorrência permanece rastreável até sua decisão |
| É trabalhoso preparar informação para o cliente | Publicação e prévia do conteúdo | A construtora produz uma linha do tempo pronta para um futuro portal do comprador |

Rentabilidade é **hipótese**, não resultado comprovado: no futuro, a cobrança pode ser por obra ativa da construtora. Para validá-la, entrevistar construtoras sobre tempo gasto preparando atualizações, frequência de decisões perdidas e disposição a pagar pelo fluxo demonstrado.

## Limites do MVP

**Dentro:** login de duas contas da construtora, obras, marcos, dependências, avanços com três tipos de mídia, publicação, alterações versionadas, ocorrências, visualização de registros simulados do comprador, filtros e persistência no Atlas.

**Fora:** login e ações do comprador ou engenheiro; criação de dados simulados pela interface; chat; comentários do comprador; confirmação de entendimento; integração com WhatsApp; gestão financeira; porcentagem automática de avanço; planejamento de equipe; notificações; gestão completa de contratos e plantas; previsão automática de entrega; aplicativo móvel nativo.

## Medida de sucesso para 03/11

Um integrante da equipe, usando uma conta de construtora, completa a jornada de demonstração descrita em [jornadas e critérios de aceite](04-jornadas-e-aceite.md) no ambiente EC2. Os dados permanecem disponíveis no Atlas, a interface React consome o Flask por HTTP e ao menos uma API externa escolhida é chamada em uma operação real do produto. O professor confirma a adequação do tema e da API externa.

## Visão após o MVP

O portal do comprador deverá mostrar apenas sua obra e o que a construtora publicou; permitirá comentar e confirmar ciência de decisões quando essa permissão for concedida. Engenheiros e demais trabalhadores poderão registrar avanços ou propor mudanças conforme permissões configuradas pela construtora. A área do comprador poderá continuar após a entrega com funções diferentes. Esses objetivos orientam a linguagem do domínio, mas não autorizam incluir tais fluxos na entrega de 03/11.
