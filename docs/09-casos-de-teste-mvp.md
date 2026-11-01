# 9. Casos de teste do MVP

**Versão de trabalho: 20/10/2026.** Este é um roteiro executável pela equipe, não um relatório de testes já aprovados. IDs `CT-xx` remetem aos [casos de uso](08-casos-de-uso-mvp.md). Priorizar testes automáticos de regra/API e um percurso real React → Flask → Atlas no EC2. Para cada caso, guardar `status` (não executado, passou, falhou, bloqueado), data, responsável e evidência na issue/PR; não marcar “passou” apenas porque a tela parece correta.

## Preparação e critérios transversais

**Dados-base:** conta fictícia `construtora_horizonte`, obra A “Residencial Aurora” com cliente fictício “Cliente Aurora”, obra B “Casa Ipê” com cliente “Cliente Ipê”; marcos Fundação, Estrutura e Alvenaria; arquivos pequenos de foto, vídeo e PDF sem dados reais. Criar IDs a partir das respostas da API, não fixá-los nos testes. Usar banco de teste separado do banco de demonstração e limpar apenas os registros criados pelo teste.

**Camadas:** `R` = regra isolada; `A` = API Flask + Atlas; `I` = interface React + API; `E` = ambiente EC2 e serviços externos. Os testes abaixo indicam a camada mínima; nos fluxos P0, repetir ao menos um caminho também na interface. Toda escrita bem-sucedida deve sobreviver a nova consulta e reinício; toda rejeição deve deixar o valor anterior intacto. Erros HTTP devem usar códigos coerentes (`401`, `404`, `409`, `422`, `5xx` conforme o caso), jamais `200` com erro escondido no corpo.

**Critério de segurança comum:** repetir leituras e escritas protegidas sem sessão. Nenhum endpoint novo fica fora da autenticação só porque a UI esconde o botão. Não registrar senha, URI Atlas ou chave externa em logs, respostas, Git ou screenshots. **Critério de autoria:** instante e autor são produzidos no servidor. **Critério de simulação:** nenhum exemplo é apresentado como atividade real de comprador ou engenheiro.

## Acesso — UC-01

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-01 | A/I | Entrar com a única conta configurada e abrir obras. | Sessão criada; lista acessível; não há seleção de segundo usuário funcional. |
| CT-02 | A/I | Tentar senha errada e usuário inexistente. | Acesso recusado com mensagem neutra; nenhuma sessão criada. |
| CT-03 | A | Chamar leitura, criação, edição e exclusão sem sessão ou após expirar. | Todas recusadas com `401`; nenhum dado retornado ou alterado. |
| CT-04 | A/I | Sair e tentar repetir uma requisição protegida; inspecionar configuração versionada. | Sessão invalidada; acesso recusado; segredo real ausente do Git. |

## Obra e filtros — UC-02 a UC-04

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-05 | A/I | Criar casa com data exata e um cliente de referência. | `201`, ID e local do recurso; modalidade e cliente salvos; data de registro/autoria geradas no servidor. |
| CT-06 | A/I | Criar apartamentos com intervalo estimado válido. | Obra salva com início/fim do intervalo, sem campo de data exata. |
| CT-07 | A | Enviar data exata e intervalo juntos; depois não enviar modalidade. | Ambas as tentativas rejeitadas; nenhuma obra parcial. |
| CT-08 | A | Enviar intervalo com fim anterior ao início, data impossível e nome vazio. | Cada entrada rejeitada com campos indicados; lista não cresce. |
| CT-09 | A/I | Criar obra, recarregar navegador e reiniciar Flask. | Obra recuperada do Atlas, sem depender de estado local do React. |
| CT-10 | A/I | Simular falha do Atlas durante criação. | Mensagem de erro; interface não anuncia sucesso nem inclui obra fictícia. |
| CT-11 | A/I | Listar duas obras e abrir cada uma pelo ID. | Dados e cliente corretos; marcos de A não aparecem em B. |
| CT-12 | A/I | Filtrar separadamente por nome, cliente, registro e entrega. | Cada filtro retorna somente resultados correspondentes. |
| CT-13 | A/I | Combinar filtros e aplicar combinação sem resultados. | Interseção correta; estado vazio claro, não erro de rede. |
| CT-14 | R/A | Com relógio controlado, testar data exata futura, no dia e vencida; intervalo antes/do fim/depois do fim. | `Atrasada` somente quando o limite final já passou; não existe botão/API de edição direta desse alerta. |
| CT-15 | A/I | Consultar obra inexistente e informar datas de filtro inválidas. | `404` ou validação apropriada; nada de dados de outra obra. |
| CT-16 | A/I | Corrigir nome, endereço, descrição e cliente de referência. | Apenas campos enviados mudam; continua havendo um único cliente; persistência confirmada. |
| CT-17 | A | Tentar trocar prazo ou conclusão pelo endpoint de edição descritiva. | Servidor rejeita ou direciona ao fluxo de mudança; não há alteração sem motivo/histórico. |

## Marcos e dependências — UC-05 a UC-07

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-18 | A/I | Criar marco com nome, descrição, início e fim previstos em A. | Estado inicial `a iniciar`; pertence a A e reaparece na lista. |
| CT-19 | A | Tentar período invertido, nome vazio e obra inexistente. | Rejeição sem marco órfão. |
| CT-20 | A/I | Criar marco em A e consultar marcos de B. | Marco de A não aparece em B. |
| CT-21 | A | Reiniciar Flask e consultar marco. | Dados persistentes no Atlas. |
| CT-22 | A/I | Definir “Alvenaria depende de Estrutura”. | Relação persistida e texto visível no detalhe. |
| CT-23 | R/A | Tentar dependência de si mesmo, de marco de B e duplicada. | Rejeição ou idempotência controlada para duplicada; nunca vínculo inválido. |
| CT-24 | R/A | Criar A→B e B→C; tentar C→A. | Ciclo rejeitado sem alterar dependências existentes. |
| CT-25 | A/I | Retirar dependência válida e recarregar. | Relação some; demais marcos preservados. |
| CT-26 | A/I | Passar marco de `a iniciar` a `em andamento`, informando motivo. | Estado e registro antes/depois, autor/data persistem. |
| CT-27 | I/A | Concluir Alvenaria com Estrutura ainda pendente, cancelar no aviso. | Aviso cita Estrutura; Alvenaria permanece não concluída. |
| CT-28 | I/A | Repetir CT-27 e confirmar que deseja prosseguir. | Conclusão permitida; histórico registra a decisão; dependência continua visível. |
| CT-29 | A/I | Concluir marco e depois reabri-lo com motivo. | Novo estado não concluído; conclusão anterior e reabertura preservadas no histórico. |
| CT-30 | A | Falhar gravação de histórico durante mudança de estado. | Estado antigo permanece ou operação é recuperada integralmente; nunca estado sem trilha. |

## Avanço, mídia, publicação e correção — UC-08 a UC-11

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-31 | A/I | Criar avanço com foto e data/descrição em um marco. | Rascunho salvo, foto abre, vínculo e tipo corretos. |
| CT-32 | A/I | Repetir com vídeo e documento PDF. | Ambos enviados/recuperados e tipados corretamente. |
| CT-33 | A | Criar avanço sem mídia ou sem descrição/data válida. | Rejeição, nenhum rascunho incompleto. |
| CT-34 | A/E | Enviar formato ou tamanho acima do limite configurado. | Rejeição clara; nada armazenado como mídia válida. |
| CT-35 | A/E | Fazer provedor de mídia falhar no upload. | Não há avanço “salvo” apontando para arquivo ausente; usuário pode tentar novamente. |
| CT-36 | A/I | Criar avanços em dias não consecutivos. | Aceitos; nenhuma obrigação diária é aplicada. |
| CT-37 | A/I | Editar data, texto e mídia de rascunho, mantendo uma mídia. | Rascunho atualizado, ainda fora da prévia. |
| CT-38 | A | Tentar remover última mídia do rascunho. | Rejeição ou pedido de outra mídia; registro continua válido. |
| CT-39 | I/A | Cancelar exclusão de rascunho; depois confirmar. | Cancelamento preserva; confirmação remove registro e arquivos exclusivos. |
| CT-40 | A | Tentar usar edição simples de rascunho em publicação. | Bloqueio; correção exige UC-11 e motivo. |
| CT-41 | A/I | Publicar rascunho válido. | Publicação registra autor/data e aparece na prévia com marco e mídia. |
| CT-42 | A/I | Consultar prévia antes de publicar outro rascunho. | Apenas conteúdo publicado aparece. |
| CT-43 | A | Publicar rascunho sem mídia recuperável ou já excluído. | Publicação recusada sem entrada fantasma. |
| CT-44 | A | Repetir requisição de publicação já concluída. | Não surgem publicações duplicadas. |
| CT-45 | A/I | Reiniciar Flask e abrir prévia. | Publicação e mídia continuam consultáveis. |
| CT-46 | A/I | Corrigir texto publicado com motivo. | Versão nova visível; anterior, campo alterado, autor/data e motivo consultáveis. |
| CT-47 | A/I | Corrigir mídia publicada. | Nova referência funciona; versão anterior permanece rastreável conforme política de retenção da mídia. |
| CT-48 | A | Tentar correção sem motivo ou sem mudança de conteúdo. | Nenhuma versão nova. |
| CT-49 | A | Simular falha ao gravar versão. | Publicação anterior intacta; não há versão parcial. |
| CT-50 | I | Corrigir avanço pré-carregado com autoria simulada de engenheiro. | Mostra origem simulada, “editado pela construtora”, texto anterior e destaque da alteração. |
| CT-51 | A/I | Corrigir a mesma publicação duas vezes. | Cadeia de versões ordenada; cada anterior permanece acessível. |

## Mudanças e histórico — UC-12 e UC-13

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-52 | A/I | Mudar prazo exato da obra com motivo. | Valor atual novo e histórico anterior/novo, autor/data/motivo. |
| CT-53 | A/I | Trocar modalidade de prazo para intervalo válido. | Só modalidade nova é atual; histórico conserva modalidade anterior. |
| CT-54 | A/I | Alterar período previsto do marco com motivo. | Marco e histórico consistentes. |
| CT-55 | A/I | Concluir e reabrir obra com motivo. | Ambos os fatos preservados; ciclo de vida atual correto. |
| CT-56 | A | Tentar editar `atrasada` diretamente. | Rejeição; alerta permanece derivado do prazo. |
| CT-57 | A | Tentar mudar prazo/estado com motivo vazio ou valor inválido. | Nada muda; não há histórico falso. |
| CT-58 | R/A | Simular falha entre atualização do valor e gravação do histórico. | Operação atômica ou compensada; jamais somente uma metade persistida. |
| CT-59 | R/A | Com relógio controlado, alterar prazo de uma obra vencida. | Alerta de atraso recalculado pelo novo limite, preservando no histórico o prazo anterior. |
| CT-60 | A/I | Abrir histórico com mudanças de obra, marco e atualização. | Alvo, campo, antes/depois, autor, instante e motivo corretos. |
| CT-61 | A | Aplicar duas mudanças no mesmo campo. | Duas entradas ordenadas, sem sobrescrever a primeira. |
| CT-62 | I | Abrir histórico de obra sem mudanças. | Estado vazio adequado, sem erro. |
| CT-63 | A | Tentar remover isoladamente mudança aplicada. | Ação indisponível/rejeitada no MVP; valor atual e trilha permanecem. |

## Ocorrências — UC-14 a UC-16

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-64 | A/I | Criar ocorrência `aberta` com título/descrição, sem opcionais. | Salva e aparece na obra. |
| CT-65 | A/I | Criar ocorrência `sem solução` vinculada a marco e mídia. | Vínculos e mídia corretos; ainda não é “aceita” automaticamente. |
| CT-66 | A | Usar marco de outra obra ou inexistente. | Rejeição; nenhuma ocorrência vinculada incorretamente. |
| CT-67 | A | Omitir título/descrição ou usar estado inicial não permitido. | Rejeição com mensagem de campo. |
| CT-68 | A/I | Reiniciar Flask e consultar ocorrência. | Estado e vínculos persistentes. |
| CT-69 | A/I | Resolver ocorrência aberta, informando motivo. | Estado `resolvida`; transição com autor/data no histórico. |
| CT-70 | A/I | Reabrir ocorrência resolvida. | Novo estado permitido e histórico de resolução preservado. |
| CT-71 | A/I | Corrigir título/descrição sem trocar estado. | Dados descritivos atualizados; estado não muda silenciosamente. |
| CT-72 | A | Tentar estado desconhecido ou transição sem motivo. | Rejeição; estado e histórico intactos. |
| CT-73 | A | Aceitar sem solução, depois resolver/reabrir. | Aceitação anterior continua histórica, sem fixar o estado para sempre. |
| CT-74 | A/I | Aceitar ocorrência `sem solução` com justificativa. | Aceitação registra justificativa, conta e instante. |
| CT-75 | A | Tentar aceitar sem justificativa. | Rejeição; ocorrência não aparece como aceita. |
| CT-76 | A | Tentar aceitar ocorrência `aberta` ou `resolvida`. | Rejeição; não cria aceitação indevida. |
| CT-77 | A/I | Aceitar sem medida compensatória. | Permitido; campo opcional não impede conclusão. |
| CT-78 | A/I | Recarregar após aceitação. | Histórico mostra aceitação e que ela não equivale a resolução. |

## Exclusões — UC-17 e UC-18

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-79 | I | Acionar exclusão de obra com marcos, avanços, versões e ocorrência; cancelar. | Aviso identifica obra e perda; nada é excluído. |
| CT-80 | A/I | Confirmar exclusão da mesma obra. | Obra, marcos, avanços, versões, mudanças, ocorrências, exemplos dependentes e mídias deixam de ser acessíveis. |
| CT-81 | A | Consultar todas as coleções/recursos após CT-80. | Nenhuma referência órfã à obra. |
| CT-82 | I/A | Excluir marco referenciado por dependência de outro marco. | Aviso aparece; marco, seus dependentes e vínculo de dependência são removidos; outro marco permanece. |
| CT-83 | A | Tentar excluir ID inexistente ou repetir exclusão. | Resposta coerente; nenhum outro objeto afetado. |
| CT-84 | A/E | Forçar erro durante remoção de arquivos externos. | Operação não é relatada como plenamente concluída; erro/pendência técnica fica rastreável para limpeza. |
| CT-85 | A | Reiniciar após exclusão e consultar IDs antigos. | Dados permanecem ausentes; não foram só escondidos no React. |
| CT-86 | I/A | Cancelar e depois confirmar exclusão de avanço publicado. | Cancelar preserva; confirmar remove avanço, versões e mídias da prévia. |
| CT-87 | A | Excluir ocorrência com aceitação. | Ocorrência e histórico direto removidos, sem referência órfã. |
| CT-88 | A | Tentar excluir avanço/ocorrência de outra obra com ID manipulado. | A API valida vínculo/ID; não exclui alvo incorreto. |
| CT-89 | A/I | Excluir registro e recarregar. | Continua ausente após reinício; feedback claro ao usuário. |

## Trabalhadores — UC-19 e UC-20

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-90 | A/I | Cadastrar trabalhador com nome, email, telefone DDD e cargo em obra existente. | `201`, ID, vínculo, ativo e data de cadastro; visível na obra. |
| CT-91 | A | Omitir cada campo obrigatório e enviar JSON que não é objeto. | `422`; nenhum trabalhador criado. |
| CT-92 | A | Enviar email inválido, telefone sem 10/11 dígitos ou com caracteres vedados. | `422`; mensagem adequada. |
| CT-93 | A | Tentar cadastrar em obra inexistente ou com identificador fora do formato de ID do MongoDB (texto, número, tamanho errado). | Identificador malformado `400`; obra ausente `404`; não cria trabalhador órfão. |
| CT-94 | A/I | Listar a obra e abrir o detalhe `GET /trabalhadores/{trabalhadorId}/` após reinício. | Cadastro persistente na lista e no detalhe; outra obra não mostra vínculo inexistente. |
| CT-95 | A | Chamar rotas de trabalhador sem sessão. | `401`; nenhum cadastro, leitura, edição ou exclusão. |
| CT-96 | A/I | Corrigir nome, cargo e telefone de trabalhador. | Só campos enviados mudam; telefone normalizado; cargo padronizado. |
| CT-97 | A/I | Trocar vínculos de obra A para B; depois enviar lista vazia. | Lista substituída corretamente; nenhuma obra inexistente aceita. |
| CT-98 | A | Atualizar com JSON vazio, campo desconhecido, ID inválido ou inexistente. | `422`, `400` ou `404` conforme o caso; registro intacto. |
| CT-99 | I/A | Acionar exclusão de trabalhador e cancelar; depois confirmar. | Aviso identifica pessoa; cancelar preserva; confirmar remove cadastro. |
| CT-100 | A | Excluir obra A de trabalhador ligado a A e B. | Vínculo A removido; cadastro e vínculo B preservados. |
| CT-101 | A/I | Excluir trabalhador e reiniciar. | Trabalhador continua ausente; nenhum login foi criado para ele. |

## Dados simulados — UC-21

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-102 | A/I | Abrir exemplos de avaliação, compreensão e dúvida ligados à obra. | Tipos corretos, cliente fictício de referência e marca `simulado`. |
| CT-103 | A/I | Abrir exemplo ligado a marco e outro à atualização específica. | Cada um aparece só no contexto correspondente. |
| CT-104 | A/I | Abrir avanço simulado do engenheiro. | Origem simulada explícita; não há sessão de engenheiro. |
| CT-105 | A | Tentar criar feedback de comprador pela API do MVP. | Não existe endpoint funcional ou recebe negação; não atribui mensagem real ao comprador. |
| CT-106 | A | Excluir objeto ao qual exemplo estava ligado. | Exemplo dependente removido; nenhuma referência órfã. |

## API externa e implantação — condicionais

Executar CT-107/108 se ViaCEP for escolhido; CT-109/110 se Cloudinary Free for escolhido. CT-111 é obrigatório para qualquer escolha. Não inventar comportamento de serviço não adotado.

| ID | Camada | Preparação e execução | Resultado esperado |
| --- | --- | --- | --- |
| CT-107 | A/I/E | Consultar CEP válido durante UC-02, com chamada real ao ViaCEP. | Endereço sugerido pelos campos recebidos; usuário pode completar número/complemento. |
| CT-108 | A/I | CEP inexistente, erro ou timeout do ViaCEP. | Aviso compreensível; cadastro manual da obra continua possível; não há valor falso. |
| CT-109 | A/I/E | Enviar foto, vídeo e documento válidos pelo provedor escolhido. | Arquivos recuperáveis no ambiente implantado; metadados do Atlas apontam ao objeto correto. |
| CT-110 | A/E | Simular indisponibilidade/cota/limite da Cloudinary. | Erro controlado; sem cobrança autorizada e sem avanço ou publicação falsamente completos. |
| CT-111 | E | No endereço EC2, executar UC-01→02→05→08→10→12→14→16; recarregar/reiniciar, chamar API externa real e inspecionar segredos. | React usa Flask por HTTP; Atlas mantém dados; mídia abre; API externa responde ou falha com fallback; credenciais fora do Git/navegador. |

## Pendências que não devem virar “resultado esperado” inventado

- Professor ainda precisa validar tema e qual integração externa satisfaz a disciplina.
- Grupo ainda precisa fixar limite/tipos exatos de arquivo e política de acesso às mídias.
- Estados adicionais de ocorrência além de `aberta`, `resolvida` e `sem solução` não foram definidos.
- Para obra concluída, cálculo histórico de atraso usa a data efetiva automática; conclusão e reabertura são verificadas também em `tests/obras/test_estado.py`.
- A rota de trabalhadores já existente no repositório cobre parte de CT-90/96/99, mas **não** implica que listagem, autenticação, verificação de obra e cascata já funcionem. Listagem por obra, detalhe por ID, sessão obrigatória e verificação da obra foram implementados em UC-19; a cascata de CT-100 continua pendente.
- CT-93 foi escrito quando o vínculo de obra usava código numérico. O cadastro usa o `_id` do MongoDB (`ObjectId` de 24 caracteres hexadecimais), então "código não positivo" passou a significar identificador fora desse formato, que retorna `400`. A obra inexistente continua verificada em separado, com `404` e sem gravação.
- Confirmado em 30/10: CT-82 remove as ocorrências do marco. CT-100 preserva o trabalhador vinculado à construtora e às demais obras; a exclusão completa de obra/marco continua pendente de implementação.
