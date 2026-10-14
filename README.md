# Projeto Ágil — acompanhamento de obras

Documentação de produto e desenvolvimento do MVP acadêmico, com entrega prevista para **03/11/2026**. O foco é permitir que uma construtora registre e publique o andamento de obras com evidências, histórico de mudanças e ocorrências.

> Estado atual: documentação inicial. As funcionalidades descritas ainda não representam software implementado. O protótipo visual anterior é uma referência de interface, não a aplicação funcional deste repositório.

## Comece por aqui

1. [Visão do produto e limite do MVP](docs/01-visao-e-escopo.md) — problema, valor e o que será demonstrado.
2. [Linguagem e modelo de domínio](docs/02-dominio-e-regras.md) — conceitos, relações e regras que não podem ser violadas.
3. [Funcionalidades](docs/03-funcionalidades.md) — catálogo priorizado, dividido por capacidade.
4. [Jornadas e critérios de aceite](docs/04-jornadas-e-aceite.md) — o que deve funcionar de ponta a ponta.
5. [Arquitetura e contrato inicial da API](docs/05-arquitetura-e-contratos.md) — orientação para React, Flask, MongoDB Atlas e EC2.
6. [Opções de APIs externas](docs/06-apis-externas.md) — alternativas, custos de adoção e decisão pendente.
7. [Plano de entrega e decisões](docs/07-plano-e-decisoes.md) — sequência de construção, riscos e dúvidas registradas.

## Como usar esta documentação

- Uma tarefa de desenvolvimento deve apontar para a funcionalidade (`F-xx`) e para os critérios de aceite correspondentes (`CA-xx`).
- Mudanças de escopo devem atualizar primeiro a visão do produto, depois regras, funcionalidades e contrato da API afetados.
- `Confirmado` identifica decisão do grupo informada nesta conversa; `Proposta` identifica uma recomendação de modelagem ainda revisável; `Pendente` exige decisão ou validação.
- A documentação deste repositório pode ser a fonte principal enquanto cliente e servidor ficam em repositórios separados. O outro repositório deve apontar para esta fonte e para a versão da API adotada.

## Restrições da disciplina

Servidor Flask com API REST no nível 2 de Richardson; banco MongoDB Atlas; cliente React consumindo HTTP; implantação em EC2; ao menos uma API externa; **código do cliente e do servidor em repositórios distintos**; credenciais fora do Git e fornecidas ao professor pelo canal exigido pela disciplina. O tema e a integração externa ainda precisam de validação final pelo professor.
