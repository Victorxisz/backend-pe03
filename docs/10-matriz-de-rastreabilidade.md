# 10. Matriz de rastreabilidade do MVP

Esta matriz permite transformar uma dor em issue, implementação, teste e demonstração sem depender de uma única pessoa para “lembrar o escopo”. `F` = [funcionalidade](03-funcionalidades.md); `UC` = [caso de uso](08-casos-de-uso-mvp.md); `CT` = [caso de teste](09-casos-de-teste-mvp.md); `CA` = [critério de aceite](04-jornadas-e-aceite.md). Os IDs são estáveis: se uma regra mudar, atualizar os documentos ligados, sem reaproveitar o ID para outra função.

| Dor/resultado demonstrável | Funcionalidade | Caso de uso | Testes | Aceite |
| --- | --- | --- | --- | --- |
| Acesso identificável e restrito | F-01 | UC-01 | CT-01–04 | CA-01 |
| Uma obra concentra contexto e prazo | F-02 | UC-02 | CT-05–10 | CA-02 |
| Encontrar obra e situação rapidamente | F-03, F-04 | UC-03 | CT-11–15 | CA-02 |
| Corrigir cadastro sem apagar decisão | F-05 | UC-04 | CT-16–17 | CA-02 |
| Planejar entregas verificáveis | F-06 | UC-05 | CT-18–21 | CA-03 |
| Tornar pré-requisitos visíveis | F-07 | UC-06 | CT-22–25 | CA-03 |
| Acompanhar estado e exceção conscientemente | F-07, F-12 | UC-07 | CT-26–30 | CA-03, CA-06 |
| Evidência do trabalho não se perde | F-08 | UC-08 | CT-31–36 | CA-04 |
| Revisar antes de divulgar | F-09 | UC-09 | CT-37–40 | CA-04 |
| Preparar atualização confiável | F-10 | UC-10 | CT-41–45 | CA-04 |
| Corrigir publicação sem apagar anterior | F-11 | UC-11 | CT-46–51 | CA-05 |
| Prazo/estado têm motivo e antes/depois | F-12 | UC-12 | CT-52–59 | CA-06 |
| Explicar decisões passadas | F-13 | UC-13 | CT-60–63 | CA-06 |
| Impedimento deixa de ser conversa solta | F-14 | UC-14 | CT-64–68 | CA-07 |
| Destino da ocorrência permanece rastreável | F-15, F-16 | UC-15 | CT-69–73 | CA-07 |
| Reconhecer formalmente problema sem solução | F-15 | UC-16 | CT-74–78 | CA-07 |
| Exclusão de obra/marco sem órfãos | F-19 | UC-17 | CT-79–85 | CA-09 |
| Retirar avanço/ocorrência indevido | F-19 | UC-18 | CT-86–89 | CA-09 |
| Saber quem participa da obra | F-20 | UC-19, UC-20 | CT-90–101 | CA-10 |
| Mostrar voz do comprador sem fingir login | F-17, F-18 | UC-21 | CT-102–106 | CA-08 |
| Requisito de API externa gratuita | F-02 ou F-08 | UC-02 ou UC-08 | CT-107–111 | CA-02 ou CA-04 |

## Sugestão de divisão em entregas verticais

1. **Primeira trilha:** UC-01, UC-02, UC-03 e UC-05; uma pessoa cria obra/marco no React e os recupera do Atlas pelo Flask.
2. **Valor central:** UC-08, UC-09 e UC-10; upload real, rascunho e publicação com prévia.
3. **Confiabilidade:** UC-11 a UC-16; versões, mudanças, histórico e ocorrências.
4. **Organização complementar:** UC-06, UC-07, UC-19 a UC-21; dependências, trabalhadores e exemplos simulados.
5. **Fechamento:** UC-17/18, integração externa gratuita aprovada, segurança, EC2 e CT-111.

Cada issue pode citar um UC e seus CTs. O responsável pela interface e o responsável pela API alinham formato de entrada/saída antes de programar; outra pessoa revisa o PR. A issue só fecha com teste realizado e evidência, não apenas com endpoint criado. Se o grupo reduzir escopo por prazo, decidir explicitamente quais `P1` saem, sem apagar critérios P0 em silêncio.
