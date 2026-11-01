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

## Verificação do backend — 01/11/2026

Os 21 UCs têm implementação no backend e cobertura de regra/API. A revisão
considerou RN-01–10, os critérios de aceite e as decisões confirmadas.
O aceite visual React/EC2 continua separado, conforme a definição de pronto.

| UC | Comportamento verificado | Evidência em `tests/` |
| --- | --- | --- |
| UC-01 | Login, sessão, expiração e saída | `autenticacao/` |
| UC-02 | Cadastro e modalidades exclusivas de entrega | `obras/test_cadastro.py`, `obras/test_cadastro_atlas.py` |
| UC-03 | Consulta, filtros combinados e atraso derivado | `obras/test_consultas.py`, `obras/test_filtro_alertas.py` |
| UC-04 | Edição descritiva sem alterar prazo/estado | `obras/test_edicao.py`, `obras/test_edicao_atlas.py` |
| UC-05 | Cadastro e consulta de marco da obra | `marcos/test_cadastro.py`, `marcos/test_consultas.py` |
| UC-06 | Dependências, retirada, mesma obra e rejeição de ciclos | `marcos/test_dependencias.py` |
| UC-07 | Estado, aviso, confirmação e reabertura | `marcos/test_estado.py` |
| UC-08 | Rascunho com mídia, validação e compensação | `avancos/test_cadastro_http.py`, `avancos/test_falhas_cadastro.py`, `midias/` |
| UC-09 | Edição e retirada de rascunho, mantendo mídia | `avancos/test_edicao_rascunhos.py`, `avancos/test_exclusao_rascunhos.py` |
| UC-10 | Publicação única e prévia persistente | `avancos/test_publicacoes.py`, `avancos/test_previa.py` |
| UC-11 | Correção com motivo, versões e autoria | `avancos/test_correcao_publicada.py`, `avancos/test_versoes.py` |
| UC-12 | Replanejamento, conclusão/reabertura e histórico atômico | `mudancas/test_mudancas.py`, `obras/test_estado.py` |
| UC-13 | Histórico de obra, marco e correções | `historico/test_consultas.py`, `integracao/test_historico.py` |
| UC-14 | Ocorrência com vínculos/mídia opcionais | `test_ocorrencias.py` |
| UC-15 | Edição, resolução/reabertura e concorrência | `test_atualizacao_ocorrencias.py` |
| UC-16 | Aceitação justificada e histórico preservado | `test_aceitacao_ocorrencias.py`, `ocorrencias/test_aceitacoes.py` |
| UC-17 | Exclusão em cascata e retomada de limpeza | `test_exclusao_cascata.py` |
| UC-18 | Exclusão individual, versões, aceitações e mídias | `test_exclusao_registros.py`, `test_exclusao_interface.mjs` |
| UC-19 | Cadastro/consulta de trabalhadores com obra válida | `trabalhadores/test_cadastro.py`, `trabalhadores/test_consultas.py` |
| UC-20 | Edição, vínculos, exclusão e responsáveis consistentes | `trabalhadores/test_rotas.py`, `trabalhadores/test_responsaveis.py`, `trabalhadores/test_persistencia_atlas.py` |
| UC-21 | Carga repetível e leitura de exemplos simulados | `test_dados_simulados.py` |

Correções desta revisão:

- UC-03/D-13: acrescentado `alerta=atrasada`, separado de `estado` e combinável
  com os demais filtros. Considera conclusão efetiva nas obras concluídas.
  Filtros repetidos são rejeitados antes da consulta.
- UC-20/RN-08: excluir trabalhador ou retirar vínculo limpa a responsabilidade
  inválida das ocorrências em transação. Registros, aceitações e histórico são
  preservados. A versão aumenta para impedir gravação de formulários antigos.
  Testes reproduziram a falha anterior e verificam rollback.
- Inventário obrigatório ampliado para UC-01–21 e documentação desatualizada
  de funções já entregues corrigida.

Comandos usados, na raiz do backend com o ambiente Python ativo:

```powershell
python -m pytest --require-routes -q -p no:cacheprovider
python -m pytest -m atlas --atlas --require-routes -q -p no:cacheprovider
python -m pytest tests/integracao/test_todas_rotas.py tests/integracao/test_historico.py tests/test_dados_simulados.py --atlas --require-routes -q -p no:cacheprovider
python -m pytest tests/trabalhadores/test_responsaveis.py tests/obras/test_filtro_alertas.py --atlas -q -p no:cacheprovider
node --test tests/test_exclusao_interface.mjs
```

Resultados: suíte completa **1.407 aprovados, 50 ignorados, zero falhas**;
cenários específicos Atlas **38 aprovados, 1 ignorado**; integração HTTP,
histórico e simulados no Atlas **30 aprovados**; novas regressões no Atlas
**14 aprovados**; confirmação de exclusão JavaScript **4 aprovados**.
Os 50 ignorados da execução padrão incluem testes de Atlas executados
separadamente e integrações que exigem credenciais exclusivas.

`--atlas` usa coleções temporárias isoladas, limpas ao terminar. O fluxo
integrado exige sucesso de cada uma das 55 operações HTTP. Os testes reais
comprovam persistência após reinício, concorrência e rollback; a mídia desses
cenários é simulada. Cloudinary real exige `RUN_CLOUDINARY_TESTS=1` e credenciais
`TEST_CLOUDINARY_*`, ausentes nesta verificação. Upload/recuperação no provedor
real e o percurso React/EC2 não são declarados aprovados por esta revisão.

## Sugestão de divisão em entregas verticais

1. **Primeira trilha:** UC-01, UC-02, UC-03 e UC-05; uma pessoa cria obra/marco no React e os recupera do Atlas pelo Flask.
2. **Valor central:** UC-08, UC-09 e UC-10; upload real, rascunho e publicação com prévia.
3. **Confiabilidade:** UC-11 a UC-16; versões, mudanças, histórico e ocorrências.
4. **Organização complementar:** UC-06, UC-07, UC-19 a UC-21; dependências, trabalhadores e exemplos simulados.
5. **Fechamento:** UC-17/18, integração externa gratuita aprovada, segurança, EC2 e CT-111.

Cada issue pode citar um UC e seus CTs. O responsável pela interface e o responsável pela API alinham formato de entrada/saída antes de programar; outra pessoa revisa o PR. A issue só fecha com teste realizado e evidência, não apenas com endpoint criado. Se o grupo reduzir escopo por prazo, decidir explicitamente quais `P1` saem, sem apagar critérios P0 em silêncio.
