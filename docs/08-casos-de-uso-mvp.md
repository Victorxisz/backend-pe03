# 8. Casos de uso do MVP

**Versão de trabalho: 20/10/2026.** Estes casos descrevem o comportamento esperado, não afirmam que ele já foi implementado. Abrangem apenas o MVP. O ator humano é sempre a **Construtora**, representada por **uma conta funcional**. Comprador, engenheiro e trabalhadores não fazem login. O cliente de referência é único por obra. Dados atribuídos a comprador ou engenheiro são simulados e pré-carregados.

## Como ler e implementar

Cada caso contém objetivo, gatilho, condições, caminho principal, desvios e resultado. Um passo de interface só está entregue quando React envia a requisição ao Flask, o Flask aplica a regra e o Atlas preserva o resultado. `RN-xx`, `F-xx`, `CA-xx` e `CT-xx` apontam para regras, funcionalidades, aceite e testes. Mensagens ao usuário devem ser claras; códigos HTTP e nomes de rotas finais ficam no [contrato da API](05-arquitetura-e-contratos.md).

**Condições comuns:** exceto UC-01, a construtora está autenticada; o servidor valida a sessão em toda leitura e escrita. IDs não encontrados não podem alterar outros registros. Falhas de banco ou de serviço externo não podem produzir sucesso falso. Datas de auditoria e autoria são geradas pelo servidor, não confiadas ao navegador. Excluir é definitivo e exige confirmação explícita na interface.

## Acesso, obra e busca

### UC-01 — Entrar e sair da conta da construtora

**Valor / vínculo:** restringir dados da obra e atribuir ações (`F-01`, `RN-10`, `CA-01`). **Gatilho:** abrir a aplicação ou escolher “Sair”. **Pré-condição:** a conta de demonstração foi configurada fora do Git.

**Fluxo principal:** 1. A construtora informa identificação e senha. 2. O React envia os dados ao Flask. 3. O servidor valida credenciais, abre a sessão e devolve o estado autenticado. 4. A interface mostra a lista de obras. Para sair, a construtora aciona “Sair”; a sessão é invalidada e a interface volta ao login.

**Desvios:** credenciais erradas mostram erro genérico sem revelar qual campo falhou; sessão vencida exige novo login; acesso direto a rota protegida ou requisição sem sessão é recusado pelo servidor. **Pós-condição:** ações posteriores registram a conta da construtora como autora; após sair não se consulta obra pela API. **Testes:** CT-01 a CT-04.

### UC-02 — Criar obra residencial

**Valor / vínculo:** abrir o histórico único da obra (`F-02`, `RN-01`, `CA-02`). **Gatilho:** “Nova obra”. **Pré-condição:** sessão ativa.

**Fluxo principal:** 1. A construtora escolhe casa ou apartamentos. 2. Informa nome, localização/endereço, descrição, início e um cliente de referência. 3. Escolhe **data exata** ou **intervalo estimado** e preenche somente os campos da modalidade escolhida. 4. Revisa e confirma. 5. O servidor valida, gera ID, data de registro e autoria, salva no Atlas e retorna a obra. 6. A interface abre seu detalhe.

**Desvios:** campos obrigatórios ausentes, datas inválidas, modalidades simultâneas ou intervalo invertido não criam obra e indicam o campo; falha de persistência não mostra sucesso. CEP pode ser completado pela API externa se escolhida, mas falha nela não bloqueia preenchimento manual. **Pós-condição:** a obra aparece na lista e continua após recarregar. **Testes:** CT-05 a CT-10.

### UC-03 — Listar, filtrar e consultar obras

**Valor / vínculo:** localizar obras e prioridades (`F-03`, `F-04`, `RN-02`, `CA-02`). **Gatilho:** abrir painel ou aplicar filtro. **Pré-condição:** obras podem existir ou não.

**Fluxo principal:** 1. O React consulta a lista. 2. Mostra nome, cliente, modalidade de entrega, prazo, ciclo de vida e alertas. 3. A construtora combina filtros por nome, estado, cliente, entrega e registro. 4. O servidor aplica filtros aos dados persistidos e devolve resultados. 5. Selecionar obra abre seus marcos, avanços, mudanças e ocorrências.

**Desvios:** lista ou filtro sem resultados mostra estado vazio; filtro inválido é rejeitado sem buscar dados incorretos; obra excluída ou ID desconhecido mostra “não encontrada”. `Atrasada` é derivado do vencimento da data exata ou fim do intervalo, jamais editado manualmente. **Pós-condição:** consulta não altera dados. **Testes:** CT-11 a CT-15.

### UC-04 — Editar dados descritivos da obra

**Valor / vínculo:** corrigir cadastro sem mascarar mudança de prazo (`F-05`, `CA-02`). **Gatilho:** “Editar obra”. **Pré-condição:** obra existente.

**Fluxo principal:** 1. A interface carrega dados atuais. 2. A construtora altera nome, descrição, endereço ou cliente de referência. 3. O servidor valida e salva somente os campos permitidos. 4. A interface mostra o dado atualizado.

**Desvios:** alteração de prazo, ciclo de vida ou conclusão é redirecionada a UC-12; cliente de referência continua sendo um só; dados inválidos não são salvos. **Pós-condição:** cadastro corrigido persiste. **Testes:** CT-16 e CT-17.

## Marcos, evidências e publicação

### UC-05 — Criar e consultar marco

**Valor / vínculo:** decompor a obra em entregas observáveis (`F-06`, `RN-03`, `CA-03`). **Gatilho:** “Novo marco” no detalhe da obra. **Pré-condição:** obra existente.

**Fluxo principal:** 1. A construtora informa nome, descrição e início/fim previstos. 2. O servidor valida o período, associa o marco à obra e salva estado inicial `a iniciar`. 3. A interface lista o marco dentro da obra e permite abrir seus detalhes.

**Desvios:** datas invertidas, campos obrigatórios ausentes ou obra inexistente impedem criação; marco de outra obra não aparece no detalhe atual. **Pós-condição:** marco persistente e vinculado a exatamente uma obra. **Testes:** CT-18 a CT-21.

### UC-06 — Definir ou retirar dependência entre marcos

**Valor / vínculo:** tornar explícita a sequência da obra (`F-07`, `RN-04`, `CA-03`). **Gatilho:** “Adicionar dependência” ou “Retirar”. **Pré-condição:** ambos os marcos existem.

**Fluxo principal:** 1. A construtora escolhe “Marco A depende de Marco B”. 2. O servidor confirma que ambos pertencem à mesma obra e que não surge ciclo. 3. Salva a relação. 4. O detalhe de A exibe “depende de B”. Para retirar, a construtora confirma o vínculo; o servidor o remove.

**Desvios:** autorreferência, outra obra, duplicação ou ciclo são rejeitados; marco inexistente não cria vínculo. **Pós-condição:** grafo de dependências válido. **Testes:** CT-22 a CT-25.

### UC-07 — Alterar estado do marco e reabri-lo

**Valor / vínculo:** acompanhar conclusão real sem ocultar exceções (`F-07`, `F-12`, `RN-04`, `RN-07`, `CA-03`, `CA-06`). **Gatilho:** selecionar novo estado.

**Fluxo principal:** 1. A construtora escolhe `a iniciar`, `em andamento` ou `concluído`, inclusive para reabrir marco concluído. 2. Informa motivo da mudança. 3. Se marcar `concluído` e houver dependência pendente, a interface mostra aviso identificando-a e pede decisão de prosseguir. 4. Após confirmar, o servidor aplica o estado e registra antes/depois, motivo, autor e data. 5. A interface mostra novo estado e histórico.

**Desvios:** cancelar após aviso mantém o estado anterior; tentativa de concluir pela API sem respeitar o protocolo de aviso/confirmar deve receber resposta que permita à interface mostrar o aviso antes de confirmar; falha ao gravar histórico não pode deixar estado alterado isoladamente. **Pós-condição:** estado e trilha de decisão coerentes. **Testes:** CT-26 a CT-30.

### UC-08 — Registrar avanço com mídia como rascunho

**Valor / vínculo:** ligar evidência a um marco (`F-08`, `RN-05`, `CA-04`). **Gatilho:** “Registrar avanço”. **Pré-condição:** marco existente; serviço de mídia configurado.

**Fluxo principal:** 1. A construtora informa data do trabalho e descrição. 2. Envia ao menos uma foto, vídeo ou documento. 3. O servidor valida tipos e limites, armazena arquivo, vincula referências ao avanço e salva-o como `rascunho`. 4. A interface mostra detalhes e permite abrir a mídia.

**Desvios:** falta de mídia, formato/tamanho inválido ou falha no armazenamento impede rascunho aparentemente completo; se uma etapa falhar, a aplicação informa o problema e trata arquivo temporário/órfão. Não há obrigação diária. **Pós-condição:** rascunho persistente e ausente da prévia publicada. **Testes:** CT-31 a CT-36.

### UC-09 — Editar ou retirar avanço em rascunho

**Valor / vínculo:** revisar antes de divulgar (`F-09`, `RN-05`, `CA-04`). **Gatilho:** “Editar rascunho” ou “Excluir rascunho”. **Pré-condição:** avanço não publicado.

**Fluxo principal:** 1. A construtora abre o rascunho. 2. Ajusta data, descrição ou mídias, mantendo ao menos uma mídia, e salva; ou confirma sua exclusão. 3. O servidor grava a edição ou remove o rascunho e arquivos exclusivos. 4. A interface atualiza a lista.

**Desvios:** rascunho já publicado não usa esta edição; vai para UC-11. Cancelar exclusão não muda dados. **Pós-condição:** rascunho válido ou removido, sem publicação acidental. **Testes:** CT-37 a CT-40.

### UC-10 — Publicar avanço e ver prévia

**Valor / vínculo:** produzir a linha do tempo que futuramente chegará ao comprador (`F-10`, `RN-05`, `CA-04`). **Gatilho:** “Publicar”. **Pré-condição:** rascunho válido com mídia recuperável.

**Fluxo principal:** 1. A construtora revisa conteúdo e confirma publicação. 2. O servidor registra autor e instante, muda estado para `publicado` e salva. 3. A prévia da obra mostra a atualização em ordem temporal, com mídia e contexto do marco. 4. A construtora pode consultá-la após reinício.

**Desvios:** rascunho incompleto ou mídia indisponível impede publicação; tentativa duplicada não cria duas publicações; rascunhos não aparecem na prévia. **Pós-condição:** publicação persistente e distinguível de rascunho. **Testes:** CT-41 a CT-45.

### UC-11 — Corrigir atualização publicada

**Valor / vínculo:** corrigir sem apagar a história (`F-11`, `RN-06`, `CA-05`). **Gatilho:** “Corrigir atualização”. **Pré-condição:** avanço publicado.

**Fluxo principal:** 1. A interface exibe versão atual. 2. A construtora modifica texto e/ou mídia e informa motivo. 3. O servidor preserva versão anterior, calcula campos alterados e registra nova versão, autoria e instante. 4. A prévia mostra a versão atual com sinal de edição; os detalhes permitem comparar texto anterior e trecho alterado.

**Desvios:** motivo vazio ou nenhuma alteração não cria versão; falha de mídia ou banco não substitui a versão atual; se o registro original era de engenheiro simulado, mostrar “editado pela construtora” sem transformar o engenheiro em usuário real. **Pós-condição:** versão anterior consultável e versão atual consistente. **Testes:** CT-46 a CT-51.

## Mudanças, ocorrências e histórico

### UC-12 — Alterar prazo ou situação de obra/marco

**Valor / vínculo:** transformar decisão em dado atual e explicação permanente (`F-12`, `RN-01`, `RN-02`, `RN-07`, `CA-06`). **Gatilho:** “Registrar mudança”. **Pré-condição:** obra ou marco existente.

**Fluxo principal:** 1. A construtora escolhe alvo e campo: prazo de obra (data exata ou intervalo), prazo de marco, estado do marco ou ciclo de vida/finalização da obra. 2. A interface mostra valor anterior. 3. Ela informa novo valor e motivo. 4. O servidor valida, aplica a mudança e grava antes/depois, motivo, autor e data na mesma operação de negócio. 5. A interface mostra novo valor e histórico; obra e marco concluídos podem ser reabertos.

**Desvios:** não se edita `atrasada` diretamente; o alerta é recalculado do prazo. Valor inválido ou motivo vazio é rejeitado. Se a gravação do histórico falhar, o valor atual não pode ficar alterado sozinho. **Pós-condição:** planejamento atual e história coerentes. **Testes:** CT-52 a CT-59.

### UC-13 — Consultar histórico de mudanças e versões

**Valor / vínculo:** responder quem mudou o quê e por quê (`F-13`, `RN-06`, `RN-07`, `CA-05`, `CA-06`). **Gatilho:** abrir “Histórico”. **Pré-condição:** obra existente.

**Fluxo principal:** 1. O servidor consulta alterações de obra, marcos e atualizações. 2. A interface exibe data, autor, alvo, campo, valor anterior, novo valor e motivo, com ligação ao objeto atual. 3. A construtora abre uma entrada para comparar versões.

**Desvios:** histórico vazio tem estado próprio; registro antigo não é sobrescrito por alteração posterior; histórico de objeto excluído junto com obra/marco não aparece mais, conforme RN-09. **Pós-condição:** consulta sem alteração. **Testes:** CT-60 a CT-63.

### UC-14 — Registrar ocorrência

**Valor / vínculo:** tirar impedimentos das conversas soltas (`F-14`, `RN-08`, `CA-07`). **Gatilho:** “Nova ocorrência”. **Pré-condição:** obra existente.

**Fluxo principal:** 1. A construtora informa título, descrição e escolhe estado inicial `aberta` ou `sem solução`. 2. Pode vincular marco, responsável e mídia. 3. O servidor verifica vínculos e salva data, autoria e estado. 4. A ocorrência aparece no detalhe da obra.

**Desvios:** marco de outra obra é rejeitado; opcionais vazios são aceitos; falha de mídia ou banco não gera ocorrência aparentemente completa. **Pós-condição:** ocorrência persistente e rastreável. **Testes:** CT-64 a CT-68.

### UC-15 — Atualizar, resolver ou reabrir ocorrência

**Valor / vínculo:** acompanhar encaminhamento sem tratar estados como finais imutáveis (`F-15`, `F-16`, `RN-08`, `CA-07`). **Gatilho:** “Editar ocorrência” ou “Mudar estado”. **Pré-condição:** ocorrência existente.

**Fluxo principal:** 1. A construtora corrige dados descritivos ou escolhe novo estado permitido. 2. Informa motivo para a transição de estado. 3. O servidor registra o estado anterior, novo estado, autor e instante e atualiza o atual. 4. Pode ocorrer `aberta → resolvida`, `sem solução → resolvida` ou reabertura posterior; aceitação anterior continua no histórico.

**Desvios:** estado fora do conjunto implementado é rejeitado; histórico não desaparece ao reclassificar. O conjunto exato de estados além dos três confirmados está em aberto e **não deve ser inventado**. **Pós-condição:** estado atual e trilha de transições consistentes. **Testes:** CT-69 a CT-73.

### UC-16 — Aceitar ocorrência sem solução

**Valor / vínculo:** registrar decisão consciente da construtora (`F-15`, `RN-08`, `CA-07`). **Gatilho:** “Aceitar sem solução”. **Pré-condição:** ocorrência no estado `sem solução`.

**Fluxo principal:** 1. A interface explica que aceitação não elimina o problema. 2. A construtora escreve justificativa; pode registrar medida compensatória, mas não é obrigada. 3. Confirma. 4. O servidor grava justificativa, conta que aceitou e instante. 5. A interface mostra a aceitação no histórico.

**Desvios:** justificativa vazia ou ocorrência em outro estado impede a ação; uma mudança posterior de estado não apaga a aceitação antiga. **Pós-condição:** aceitação persistente e auditável. **Testes:** CT-74 a CT-78.

## Exclusão, trabalhadores e exemplos simulados

### UC-17 — Excluir obra ou marco com todos os dependentes

**Valor / vínculo:** permitir remoção definitiva sem resíduos invisíveis (`F-19`, `RN-09`, `CA-09`). **Gatilho:** “Excluir obra” ou “Excluir marco”. **Pré-condição:** alvo existente.

**Fluxo principal:** 1. A interface lista o alvo e avisa que marcos, avanços, versões, mudanças, ocorrências vinculadas, mídias e dados simulados dependentes serão perdidos. 2. A construtora confirma explicitamente. 3. O servidor remove o conjunto e trata arquivos externos associados. 4. A interface volta à lista e não apresenta registros órfãos.

**Desvios:** cancelar mantém tudo; alvo inexistente não remove nada; falha parcial não deve ser reportada como sucesso. Ao excluir um marco, vínculos de dependência em outros marcos da mesma obra também são removidos; ocorrências vinculadas ao marco seguem a política de exclusão de dependentes. **Pós-condição:** alvo e dependentes ausentes. Exclusão isolada de mudança aplicada não é oferecida. **Testes:** CT-79 a CT-85.

### UC-18 — Excluir avanço ou ocorrência individualmente

**Valor / vínculo:** corrigir registro indevido (`F-19`, `CA-09`). **Gatilho:** “Excluir” no registro. **Pré-condição:** registro existente.

**Fluxo principal:** 1. A interface avisa o que desaparecerá: versões e mídias do avanço, ou histórico e aceitação da ocorrência. 2. A construtora confirma. 3. O servidor remove o registro e dependentes diretos. 4. A listagem é atualizada.

**Desvios:** cancelar mantém dados; publicação excluída desaparece da prévia; falha de remoção externa é comunicada e tratada, sem sucesso falso. **Pós-condição:** sem órfãos. **Testes:** CT-86 a CT-89.

### UC-19 — Cadastrar e consultar trabalhadores da obra

**Valor / vínculo:** saber quem participa da obra (`F-20`, `CA-10`). **Gatilho:** “Adicionar trabalhador”. **Pré-condição:** obra existente.

**Fluxo principal:** 1. A construtora informa nome, email, telefone com DDD e cargo. 2. O servidor valida, cria o trabalhador com vínculo à obra, status ativo e data de cadastro. 3. A interface lista trabalhadores da obra e permite consultar seus dados. Trabalhador não ganha sessão.

**Desvios:** dados inválidos ou obra inexistente são rejeitados; cadastro com erro no banco não aparece como salvo. A implementação atual possui `POST /trabalhadores/obra/{codigo_obra}/`, mas ainda precisa de leitura, autenticação e validação de existência da obra para satisfazer este caso. **Pós-condição:** trabalhador persistente e vinculado. **Testes:** CT-90 a CT-95.

### UC-20 — Editar vínculos/dados e excluir trabalhador

**Valor / vínculo:** manter equipe da obra atualizada (`F-20`, `CA-10`). **Gatilho:** “Editar” ou “Excluir trabalhador”. **Pré-condição:** trabalhador existente.

**Fluxo principal:** 1. A construtora altera campos ou lista de obras às quais o trabalhador está vinculado, podendo deixar a lista vazia; o servidor verifica se obras existem e salva. 2. Para excluir, a interface identifica o trabalhador e pede confirmação. 3. O servidor remove o cadastro e a interface atualiza a listagem.

**Desvios:** ID inválido/inexistente, obra inexistente, campo inválido ou cancelamento não alteram dados; exclusão de obra deve remover o vínculo do trabalhador sem necessariamente apagar seu cadastro se ainda houver outras obras. **Pós-condição:** vínculos consistentes e sem login de trabalhador. **Testes:** CT-96 a CT-101.

### UC-21 — Consultar dados simulados do comprador e do engenheiro

**Valor / vínculo:** demonstrar transparência futura sem fingir interação real (`F-17`, `F-18`, `RN-10`, `CA-08`). **Gatilho:** abrir painel de contexto da obra, marco ou atualização. **Pré-condição:** exemplos foram pré-carregados.

**Fluxo principal:** 1. O servidor devolve avaliação, compreensão ou dúvida simulada do comprador vinculada ao objeto correto, e eventual avanço simulado atribuído ao engenheiro. 2. A interface marca visivelmente `simulado`. 3. Se a construtora corrigiu publicação originada desse exemplo de engenheiro, mostra autoria original, edição pela construtora e texto anterior.

**Desvios:** não há formulário de criação, login ou comentário real desses perfis; dado ausente mostra estado vazio; vínculo a objeto excluído não pode permanecer. **Pós-condição:** somente leitura, sem atribuir ação a pessoa real. **Testes:** CT-102 a CT-106.

## Integração externa e resultado mínimo

A API externa escolhida deve participar de uma ação real. Se ViaCEP for adotado, UC-02 inclui consulta de CEP com retorno útil e fallback manual. Se Cloudinary Free for adotada, UC-08/UC-10 incluem upload e recuperação. O grupo e o professor ainda precisam aprovar a escolha; portanto, os testes condicionais estão em CT-107 a CT-111. O plano gratuito deve ser suficiente **sem cobrança** para o cenário de avaliação.

**Caminho de demonstração:** UC-01 → UC-02 → UC-05 → UC-06 → UC-19 → UC-08 → UC-10 → UC-11 → UC-12 → UC-14 → UC-16 → UC-13 → UC-03. Executá-lo depois de reiniciar o servidor confirma persistência. Exclusões (UC-17/18/20) devem ser demonstradas sobre dados descartáveis, após preservar o cenário principal.

## Pontos de desenho propostos, não decisões atribuídas ao grupo

- Ao excluir uma obra, **proposta:** retirar apenas o vínculo de trabalhadores também vinculados a outras obras; não apagar a pessoa de todas as obras. Confirmar antes de implementar UC-17/20.
- Ao excluir um marco, **proposta:** remover a ocorrência ligada a ele junto com os registros dependentes, conforme “apagar tudo junto”. Confirmar se o grupo prefere preservar a ocorrência na obra sem o marco.
- O aviso de dependência deve existir também quando a alteração vier diretamente pela API. O formato exato da confirmação HTTP ainda será definido no contrato.
- Excluir arquivos de provedor externo junto de dados no Atlas requer estratégia de recuperação de falha; o comportamento visível está especificado, a técnica ainda não.
