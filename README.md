# Projeto Ágil — acompanhamento de obras

Documentação de produto e desenvolvimento do MVP acadêmico, com entrega prevista para **03/11/2026**. O foco é permitir que uma construtora registre e publique o andamento de obras com evidências, histórico de mudanças e ocorrências.

> Estado atual: especificação do MVP e implementação parcial. Este repositório já contém rotas Flask de trabalhadores; os demais fluxos descritos são requisitos, não funcionalidades presumidamente prontas. O protótipo visual anterior é apenas referência de interface.

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
