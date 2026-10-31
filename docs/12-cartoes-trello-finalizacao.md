# Cartões Trello para finalizar o MVP

Referência: 30/10/2026. Entrega prevista na documentação: 03/11/2026.

São **21 cartões, um para cada caso de uso**, mantendo o foco no backend dos cartões anteriores. As atividades técnicas ficam dentro do caso de uso, inclusive armazenamento e acesso a mídias. Elas não viram cartões de infraestrutura separados.

O modelo preserva **Contexto e cobertura → Arquivos previstos → Fazer → Pronto quando → Testes relacionados → Dependências**, com contexto suficiente para usar cada descrição como prompt de implementação. Os títulos agora usam os identificadores dos casos de uso.

## Orientações para usar os cartões

- Os cartões representam a cobertura completa do MVP. A existência de código ou testes não significa que a entrega passou: quem assumir deve revisar o que existe, completar lacunas e registrar evidências. Não refazer funcionalidades já corretas.
- Os caminhos são relativos à raiz deste repositório do servidor. **Editar/reutilizar** indica arquivo existente; **criar** indica destino proposto. Ao criar rotas, registrar o blueprint em `api.py` e documentar corpo, resposta e erros no contrato.
- O ponto de entrada atual é `api.py`; a conexão com Atlas está em `db.py`, que lê `MONGO_URI`. A autenticação atual usa JWT e `JWT_SECRET_KEY`, com `sessao_obrigatoria` em `app/auth/permissions.py`. Reaproveitar essa base.
- Em cada cartão, validar autenticação e conta ativa no servidor, usar IDs e vínculos reais, gerar autoria e auditoria no servidor e devolver erros HTTP coerentes. Uma falha não pode anunciar sucesso ou deixar metade de uma operação de negócio aplicada.
- Priorizar o contrato implementado quando a documentação antiga trouxer nomes anteriores, registrando qualquer ajuste acordado. Não criar aliases ou reorganizar todo o projeto apenas para coincidir com a estrutura proposta em `docs/11-organizacao-backend.md`.
- Os CT são cenários de aceite, não um relatório de execução. Testes locais com banco/provedor simulados cobrem regras e API; persistência após reinício e integração externa exigem verificações reais em ambiente de teste. Usar o isolamento já existente e não limpar dados da demonstração.
- “Pronto quando” abaixo define a entrega do backend. Nas partes dos CT que exigem React, avisos e cancelamentos são verificados junto ao frontend; nenhum cartão deve ser considerado integrado só porque passou por testes isolados da API.
- Todos os cartões contribuem para o **CT-111**, executado no EC2 com React → Flask → Atlas, reinício e chamada real à API externa. Registrar a validação final nos próprios cartões, sem criar um cartão adicional que não represente caso de uso.
- Cloudinary já foi adotada no código de mídia. O aceite dessa integração pelo professor e a execução real no ambiente publicado ainda precisam de evidência. ViaCEP permanece condicional; não incluí-la como obrigação adicional.

Fontes: [casos de uso](08-casos-de-uso-mvp.md), [regras](02-dominio-e-regras.md), [funcionalidades](03-funcionalidades.md), [contrato HTTP](05-arquitetura-e-contratos.md), [testes](09-casos-de-teste-mvp.md) e implementação atual.

---

## Cartão 01 — [UC-01] Entrar e sair da conta da construtora

**Contexto e cobertura:**

A construtora é o único ator funcional do MVP. Entrar permite consultar e administrar obras e atribuir as ações à conta autenticada; sair deve impedir que tokens daquela sessão continuem acessando os dados. Comprador, engenheiro e trabalhadores não recebem login. O objetivo deste cartão é concluir e verificar o acesso existente, sem ampliar o produto para cadastro público de usuários.

Cobre **F-01, RN-10 e CA-01**.

**Arquivos previstos:**

- Editar/reutilizar `construtora.py`, `app/auth/permissions.py`, `api.py`, `db.py`, `validacoes.py` e `.env.example` quando necessário.
- Editar/complementar `tests/autenticacao/test_autenticacao.py` e `tests/autenticacao/test_construtora.py`.

**Fazer:**

- Revisar `POST /construtora/login/`, `POST /construtora/refresh/` e `POST /construtora/logout/`, que já existem. Documentar esse contrato para o React, em vez de introduzir as rotas de sessão do planejamento antigo sem necessidade.
- Validar credenciais e conta ativa; devolver erro neutro para usuário desconhecido ou senha incorreta. Nunca devolver senha ou hash.
- Garantir que o JWT identifique a construtora e a sessão e que toda rota protegida valide tipo de conta, expiração e revogação.
- Confirmar que logout revoga a sessão no banco: tanto acesso quanto renovação anteriores devem ser recusados, inclusive após reinício.
- Aplicar a proteção às leituras, escritas e arquivos; revisar módulos que usam apenas `jwt_required()` para não aceitar conta inválida ou inativa.
- Preparar a conta de demonstração por procedimento controlado e documentado, mantendo senha e chaves reais fora do Git.

**Pronto quando:**

A conta prevista entra, consulta obras e sai; credenciais incorretas, token expirado, conta inativa e sessão revogada não permitem acesso. Reutilizar um token após logout não reabre a sessão nem permite renová-la.

**Testes relacionados:**

CT-01 a CT-04: entrada, rejeição neutra, proteção das rotas e logout efetivo. Repetir CT-03 nos endpoints dos demais cartões. O redirecionamento visual para login é validado com o frontend.

**Dependências:**

Configuração JWT e conexão com banco de teste. É a base de autenticação para UC-02 a UC-21.

---

## Cartão 02 — [UC-02] Criar obra residencial

**Contexto e cobertura:**

A obra reúne o planejamento, as evidências e as decisões de um projeto residencial. Uma casa e um edifício de apartamentos usam o mesmo fluxo de cadastro. Cada obra tem um único cliente de referência, que é um dado do cadastro e não uma conta. A entrega pode ser um dia exato ou uma janela estimada, nunca as duas modalidades simultaneamente.

Cobre **F-02, RN-01 e CA-02**.

**Arquivos previstos:**

- Editar/reutilizar `app/obras/routes.py`, `app/obras/service.py`, `app/obras/validacoes.py` e `app/obras/repository.py`.
- Complementar `tests/obras/test_cadastro.py`, `tests/obras/test_cadastro_atlas.py` e os testes de cadastro existentes em `tests/obras/test_validacoes_cadastro.py`, evitando duplicação.
- Atualizar `docs/05-arquitetura-e-contratos.md` se houver ajuste de contrato.

**Fazer:**

- Revisar `POST /obras`, exigindo `nome`, `tipo`, `cliente`, `localizacao`, `descricao`, `inicio` e `entrega`. Usar os campos atuais `cliente` e `data_registro`, em vez dos nomes antigos.
- Aceitar `tipo` como `casa` ou `apartamentos`. Validar textos não vazios e dias existentes em `AAAA-MM-DD`.
- Em `data_exata`, aceitar somente modalidade e data; em `intervalo_estimado`, modalidade, início e fim. Rejeitar mistura, modalidade ausente e fim anterior ao início; intervalo de um dia é permitido.
- Gerar ID, `autor` autenticado e `data_registro` UTC no servidor, iniciando `estado="planejada"` e `critica=false`. Rejeitar esses campos controlados quando enviados no corpo.
- Retornar `201`, representação persistida e `Location` que possa ser consultada. Falha do banco não deve produzir obra fictícia ou resposta de sucesso.
- Se ViaCEP vier a ser adotada, manter preenchimento manual em caso de erro; não tornar essa integração uma nova dependência obrigatória deste cadastro.

**Pronto quando:**

Casa com prazo exato e apartamentos com intervalo válido são criados e recuperados do Atlas após reinício. Entradas inválidas não acrescentam documentos, e autoria não pode ser escolhida pelo cliente HTTP.

**Testes relacionados:**

CT-05 a CT-10: modalidades, validações, persistência e falha do Atlas. CT-107/108 somente se ViaCEP for adotada. A consulta HTTP de confirmação usa UC-03.

**Dependências:**

UC-01. UC-03 para validar o endereço retornado em `Location` e a releitura completa.

---

## Cartão 03 — [UC-03] Listar, filtrar e consultar obras

**Contexto e cobertura:**

A construtora precisa localizar obras pelo cliente, prazo e situação, sem misturar os registros de projetos diferentes. O ciclo de vida da obra e seus alertas são informações distintas: uma obra pode estar em andamento e atrasada ao mesmo tempo. A consulta informa a situação persistida e os alertas calculados; não altera planejamento ou histórico.

Cobre **F-03, F-04, RN-02 e CA-02**.

**Arquivos previstos:**

- Editar/reutilizar `app/obras/routes.py`, `app/obras/service.py` e `app/obras/repository.py`.
- Complementar `tests/obras/test_consultas.py` e testes de consulta/persistência já existentes.

**Fazer:**

- Revisar `GET /obras` e `GET /obras/{obraId}`. Preservar o formato atual da lista `{"obras": [...]}` e documentar campos do detalhe.
- Combinar por interseção `nome`, `cliente`, `estado`, `entregaDe`, `entregaAte`, `registroDe` e `registroAte`. Nome/cliente usam busca parcial literal, sem diferenciar maiúsculas.
- Manter limites inclusivos: registro considera dia UTC; entrega estimada considera o fim do intervalo. Validar filtros desconhecidos, datas impossíveis e intervalos invertidos antes da consulta.
- Distinguir `planejada`, `em andamento`, `concluída` e `suspensa` dos alertas. Calcular atraso somente depois do limite final, sem permitir edição direta.
- Para obra concluída, fechar com UC-12 o contrato da data efetiva de conclusão e calcular o atraso histórico por ela. A implementação atual evita usar o relógio de hoje nesse caso; isso ainda não comprova o cálculo histórico completo.
- Retornar lista vazia para ausência de resultados, `400` para ID malformado e `404` para obra ausente. O detalhe deve oferecer os dados/vínculos necessários para consultar marcos, avanços e ocorrências pelos respectivos endpoints.

**Pronto quando:**

Filtros isolados e combinados retornam somente as obras esperadas; lista vazia não é erro; consultas não modificam o banco. O alerta não aparece no próprio dia limite, e obra concluída não passa a atrasada apenas porque o tempo avançou.

**Testes relacionados:**

CT-11 a CT-15: listagem, filtros, atraso e erros. Acrescentar cenários de obra concluída conforme o contrato fechado com UC-12. Usar relógio controlado nos testes de datas.

**Dependências:**

UC-01 e dados de UC-02. A parte de atraso histórico de obra concluída depende da definição de conclusão em UC-12; os demais filtros podem ser concluídos antes.

---

## Cartão 04 — [UC-04] Editar dados descritivos da obra

**Contexto e cobertura:**

A construtora pode corrigir nome, endereço, descrição ou cliente sem que isso represente uma decisão de replanejamento. Alterar prazo ou concluir uma obra tem outro significado: precisa de motivo e histórico. Este cartão mantém essa separação, impedindo que uma edição comum contorne o fluxo de mudanças.

Cobre **F-05 e CA-02**. É item **P1**, preservado no conjunto completo de cartões.

**Arquivos previstos:**

- Editar/reutilizar `app/obras/routes.py`, `app/obras/service.py`, `app/obras/repository.py` e validações pertinentes.
- Complementar `tests/obras/test_edicao.py` e `tests/obras/test_edicao_atlas.py`.

**Fazer:**

- Revisar `PATCH /obras/{obraId}` para aceitar somente `nome`, `descricao`, `localizacao` e `cliente` no fluxo descritivo.
- Atualizar apenas os campos enviados e preservar os demais. Rejeitar texto vazio, JSON inválido/vazio e campos desconhecidos conforme o contrato existente.
- Manter um único cliente de referência; mudar o texto do cliente não cria usuário ou lista de compradores.
- Impedir alteração de entrega, início de planejamento, ciclo de vida, conclusão, alertas ou autoria por este fluxo. Prazo e situação seguem UC-12.
- Validar ID, existência e sessão. Não substituir o documento inteiro nem apagar dependências e metadados internos ao atualizar poucos campos.
- Retornar os dados atualizados e tratar falha de persistência sem anunciar edição concluída.

**Pronto quando:**

Uma correção parcial persiste e aparece na releitura, preservando campos omitidos. Enviar prazo ou conclusão pelo endpoint descritivo não altera a obra nem cria um histórico que não corresponda a uma mudança real.

**Testes relacionados:**

CT-16 e CT-17: edição parcial persistente e impossibilidade de alterar planejamento sem motivo/histórico. Verificar também IDs e falha do banco com os testes existentes.

**Dependências:**

UC-01, UC-02 e UC-03. UC-12 é o fluxo complementar de planejamento; a rejeição desses campos deve funcionar mesmo antes dele.

---

## Cartão 05 — [UC-05] Criar e consultar marco

**Contexto e cobertura:**

Um marco é uma entrega verificável dentro da obra, como Fundação ou Estrutura. Tem período previsto e estado próprio; não é uma nova obra nem uma entidade chamada etapa. Este cartão reúne cadastro, listagem e consulta individual, permitindo planejar e reencontrar a entrega em um único caso de uso.

Cobre **F-06, RN-03 e CA-03**.

**Arquivos previstos:**

- Editar/reutilizar `app/marcos/routes.py`, `app/marcos/service.py`, `app/marcos/validacoes.py`, `app/marcos/repository.py` e `app/obras/repository.py` conforme os acessos atuais.
- Complementar `tests/marcos/test_cadastro.py` e `tests/marcos/test_consultas.py`.

**Fazer:**

- Revisar `POST /obras/{obraId}/marcos`, `GET /obras/{obraId}/marcos` e a consulta individual existente `GET /obras/{obraId}/marcos/{marcoId}`.
- Usar `nome`, `descricao`, `inicio_previsto` e `fim_previsto`, validando campos obrigatórios, datas e período não invertido.
- Confirmar existência da obra e gerar vínculo a exatamente uma obra, com estado inicial `a iniciar`.
- Retornar `201`, ID e `Location` na criação; a URI deve corresponder à consulta individual atual, sem impor `/marcos/{id}` apenas porque aparece na proposta antiga.
- Na consulta individual, conferir também o pertencimento à obra informada. Obra A não pode expor o marco de B pelo caminho de A.
- Distinguir obra sem marcos, obra inexistente e marco inexistente. Serializar IDs para JSON e preservar o formato da listagem já utilizado.
- Reaproveitar a leitura de dependências de UC-06; revisar a aplicação de `sessao_obrigatoria` também na criação.

**Pronto quando:**

Um marco válido é criado, listado e aberto pelo endereço informado, inclusive após reinício. Dados inválidos e cruzamento de IDs de obras não criam nem revelam marco incorreto.

**Testes relacionados:**

CT-18 a CT-21: cadastro/consulta, validação, isolamento entre obras e persistência. CT-22 complementa a exibição das dependências com UC-06.

**Dependências:**

UC-01 e UC-02. UC-06 complementa os vínculos de dependência, sem bloquear a criação de marco sem dependências.

---

## Cartão 06 — [UC-06] Definir ou retirar dependência entre marcos

**Contexto e cobertura:**

“Alvenaria depende de Estrutura” explica a sequência planejada do trabalho. A relação é entre marcos da mesma obra e não pode produzir ciclos. Retirar a dependência muda o vínculo de planejamento e preserva os dois marcos. A dependência será usada para avisar sobre uma conclusão antecipada em UC-07.

Cobre a gestão de dependências de **F-07, RN-04 e CA-03**.

**Arquivos previstos:**

- Editar/reutilizar `app/marcos/routes.py`, `app/marcos/service.py`, `app/marcos/dependencias.py` e `app/marcos/repository.py`.
- Complementar `tests/marcos/test_dependencias.py` e a consulta de marcos quando necessário.

**Fazer:**

- Revisar `GET` e `POST /marcos/{marcoId}/dependencias` e `DELETE /marcos/{marcoId}/dependencias/{dependenciaId}`.
- Receber `depende_de_id` na criação; verificar ambos os marcos e a mesma obra. Devolver o identificador do vínculo e os nomes que a interface precisa exibir.
- Rejeitar autorreferência, duplicação e ciclos diretos ou indiretos, como A → B → C → A.
- Reaproveitar o armazenamento atual `dependencias_marcos` na obra e o controle de concorrência do repositório. Não introduzir uma segunda fonte de vínculos.
- Revalidar alterações concorrentes para impedir que duas relações, individualmente válidas, produzam um ciclo quando gravadas juntas.
- Retirar somente o vínculo selecionado, conferindo que pertence ao marco indicado. Não apagar o marco pré-requisito nem outros vínculos.
- Uniformizar proteção da construtora e documentar `404`/`409` e o corpo das respostas de conflito.

**Pronto quando:**

Adicionar, consultar e retirar uma dependência funciona após recarregar. Relações inválidas não alteram o grafo, e a remoção preserva os marcos envolvidos e os demais vínculos.

**Testes relacionados:**

CT-22 a CT-25: vínculo, validações, ciclo indireto e remoção. Complementar com concorrência usando a estrutura de testes existente quando necessário para preservar a regra.

**Dependências:**

UC-01 e UC-05. UC-07 consome esse grafo para avisar sobre pendências.

---

## Cartão 07 — [UC-07] Alterar estado do marco e reabri-lo

**Contexto e cobertura:**

A construtora informa o andamento real do marco e pode voltar a trabalhar em uma entrega antes concluída. Um pré-requisito pendente exige uma decisão consciente: o sistema avisa, mas a construtora pode prosseguir. Tanto a conclusão quanto a reabertura precisam de motivo e trilha, sem apagar decisões anteriores.

Cobre a mudança de estado de **F-07**, a parte correspondente de **F-12**, **RN-04, RN-07 e CA-03/06**.

**Arquivos previstos:**

- Editar/reutilizar `app/marcos/routes.py`, `app/marcos/service.py`, `app/marcos/validacoes.py`, `app/marcos/repository.py` e `app/historico/repository.py`.
- Complementar `tests/marcos/test_estado.py`.

**Fazer:**

- Revisar `PATCH /marcos/{marcoId}` para `estado` e `motivo`, aceitando `a iniciar`, `em andamento` e `concluído`, inclusive reabertura.
- Ao concluir com pré-requisitos pendentes, manter o estado e retornar `409`, `codigo="DEPENDENCIAS_PENDENTES"` e a identificação das pendências.
- Aceitar nova requisição com `confirmar_dependencias=true`; revalidar as condições no servidor antes de concluir.
- Guardar antes/depois, motivo, autor autenticado, instante UTC e as pendências confirmadas. Não apagar as dependências ao permitir a conclusão.
- Persistir estado e evento como uma operação consistente. Reaproveitar a estratégia existente e verificar que falhas e concorrência não geram histórico falso ou estado sem trilha.
- Não criar uma segunda implementação de transição para UC-12: seu fluxo de mudança de estado deve chamar a mesma regra.
- Expor o evento para leitura em UC-13 e revisar a proteção da conta ativa nesta rota.

**Pronto quando:**

A primeira tentativa com pendências apenas avisa; cancelar preserva o estado; confirmar conclui com histórico. Reabrir mantém a conclusão anterior registrada, e falha de persistência não deixa uma alteração isolada.

**Testes relacionados:**

CT-26 a CT-30: transição, aviso/cancelamento, confirmação, reabertura e falha ao gravar histórico. O cancelamento do diálogo é validado com React; a API garante ausência de alteração antes de confirmar.

**Dependências:**

UC-01, UC-05 e UC-06. UC-13 conclui a consulta unificada do histórico, mas a gravação deve funcionar neste cartão.

---

## Cartão 08 — [UC-08] Registrar avanço com mídia como rascunho

**Contexto e cobertura:**

Um avanço descreve trabalho realizado em um marco e inclui uma evidência recuperável. Ele nasce como rascunho para revisão, fora da linha do tempo publicada. Não existe obrigação de registrar todo dia. Foto, vídeo e documento são opções de mídia: cada avanço exige ao menos um arquivo válido, não necessariamente um de cada tipo.

Cobre **F-08, RN-05 e CA-04**, incluindo a infraestrutura de mídia necessária ao caso de uso.

**Arquivos previstos:**

- Criar `app/avancos/routes.py`, `app/avancos/service.py` e completar `app/avancos/validacoes.py`, atualmente sem implementação.
- Editar/reutilizar `app/avancos/repository.py`, `midias.py`, `acesso_midias.py`, `midias_routes.py`, `app/integracoes/armazenamento.py` e `app/config.py`.
- Complementar `tests/midias/test_armazenamento.py`, `tests/midias/test_acesso.py` e criar `tests/avancos/test_cadastro_contrato.py` para o fluxo de rascunho. Registrar novas rotas em `api.py`.

**Fazer:**

- Implementar `POST /marcos/{marcoId}/avancos`, com dados e arquivos em `multipart/form-data`; documentar os nomes dos campos enviados pelo React.
- Exigir marco existente, data do trabalho válida, descrição não vazia e ao menos uma mídia. Gerar autoria/data de registro no servidor e estado `rascunho`.
- Implementar `GET /marcos/{marcoId}/avancos` e `GET /avancos/{avancoId}`, validando vínculos e distinguindo lista vazia de alvo inexistente.
- Reutilizar `ServicoMidias`: JPEG/PNG, MP4 e PDF, com os limites atuais configuráveis de 10/100/10 MiB. Validar conteúdo e tamanho, não apenas extensão.
- Salvar avanço e metadados coerentemente no Atlas depois dos uploads. Não persistir URL temporária como referência permanente.
- Reutilizar `GET /avancos/{avancoId}/midias`, `GET /midias/{midiaId}` e `/midias/{midiaId}/conteudo` para acesso autenticado, inclusive fora da tela.
- Se upload ou banco falhar, preservar o resultado anterior, compensar arquivos novos e guardar pendências de limpeza de modo durável. Verificar como recuperar interrupção do processo entre upload e persistência.
- Confirmar que o rascunho não aparece na prévia de UC-10 e que os arquivos continuam disponíveis após reinício.

**Pronto quando:**

O avanço é criado e consultado com evidência real de cada tipo suportado, permanece rascunho e não depende de memória local. Arquivo inválido, ausência de mídia ou falha externa não produz rascunho falsamente completo.

**Testes relacionados:**

CT-31 a CT-36: arquivos, dados obrigatórios, limites, falhas e frequência livre. CT-03: acesso protegido. CT-109/110: upload/recuperação e falha real/controlada da integração adotada. CT-42 verifica exclusão de rascunhos da prévia com UC-10.

**Dependências:**

UC-01 e UC-05; configuração Cloudinary em ambiente de teste. UC-10 complementa a validação da prévia, sem bloquear o registro do rascunho.

---

## Cartão 09 — [UC-09] Editar ou retirar avanço em rascunho

**Contexto e cobertura:**

Antes de publicar, a construtora pode corrigir a data, o texto e as evidências ou descartar o registro. A revisão mantém ao menos uma mídia válida. Essa liberdade termina na publicação: corrigir um conteúdo divulgado exige motivo e preservação da versão anterior em UC-11.

Cobre **F-09**, retirada de rascunho relacionada a **F-19**, **RN-05 e CA-04/09**.

**Arquivos previstos:**

- Criar/completar `app/avancos/routes.py` e `service.py` previstos em UC-08.
- Editar/reutilizar `app/avancos/repository.py`, `validacoes.py`, `midias.py` e `revisoes.py`.
- Criar `tests/avancos/test_edicao_rascunhos.py` e `tests/avancos/test_exclusao_rascunhos.py`.

**Fazer:**

- Implementar o ramo de rascunho de `PATCH /avancos/{avancoId}`: atualizar somente data, descrição e mídias enviadas, preservando autoria, vínculo e estado.
- Validar o conjunto final de mídias antes de salvar. Não permitir retirar a última sem substituição válida.
- Usar o controle de revisão existente para não sobrescrever edição concorrente ou editar como rascunho algo que acabou de ser publicado.
- Na substituição de arquivos, salvar a nova composição antes de limpar referências antigas sem uso; em falha, preservar o rascunho anterior e tratar os arquivos novos.
- Implementar `DELETE /avancos/{avancoId}` para rascunho, com remoção de metadados e arquivos exclusivos. Reutilizar o mecanismo de limpeza que também servirá à UC-18.
- Preparar o frontend para identificar o alvo e pedir confirmação antes de enviar DELETE; cancelamento não envia a requisição destrutiva.
- Restringir a edição simples ao estado rascunho. Uma publicação enviada ao mesmo PATCH deve seguir UC-11, exigindo motivo e versão, ou ser recusada enquanto esse fluxo não existir.
- Não retornar exclusão plenamente concluída se a limpeza externa ficar pendente; registrar a pendência para recuperação.

**Pronto quando:**

Edição válida persiste mantendo o estado rascunho; exclusão confirmada remove o registro e arquivos exclusivos. A tentativa de remover a última mídia ou contornar o versionamento de publicação é recusada sem corromper dados.

**Testes relacionados:**

CT-37 a CT-40: edição, última mídia, cancelamento/exclusão e proteção do publicado. CT-42 confirma permanência fora da prévia. As partes visuais são validadas com o frontend.

**Dependências:**

UC-01 e UC-08. Alinhar a implementação compartilhada de PATCH com UC-11 e DELETE com UC-18, sem criar rotas concorrentes.

---

## Cartão 10 — [UC-10] Publicar avanço e ver prévia

**Contexto e cobertura:**

Publicar declara que a construtora revisou o avanço e o liberou para compor a linha do tempo da obra. A prévia é consultada pela própria construtora para mostrar o que um futuro portal do comprador receberia. Ela não cria acesso real de comprador e não deve conter rascunhos ou evidências indisponíveis.

Cobre **F-10, RN-05 e CA-04**.

**Arquivos previstos:**

- Editar/reutilizar a implementação existente em `app/mudanças/ocorrencias/historico/routes.py`, `service.py`, `repository.py` e `validacoes.py`.
- Reutilizar serviços de mídia em `app/avancos/` e complementar `tests/avancos/test_publicacoes.py`.
- Se a equipe mover publicação para `app/avancos/`, fazer a migração com imports e registro em `api.py` na mesma entrega, preservando o contrato. A mudança de pasta não é requisito deste cartão.

**Fazer:**

- Revisar `POST /avancos/{avancoId}/publicacoes`, `GET /avancos/{avancoId}/publicacoes` e `GET /obras/{obraId}/previa`, que já existem.
- Verificar estado rascunho, conteúdo obrigatório, mídias recuperáveis e vínculos válidos entre avanço, marco e obra antes de publicar.
- Registrar autoria e instante da publicação no servidor e atualizar estado/fato de publicação de forma consistente.
- Evitar duplicação ao repetir requisição ou publicar concorrentemente. Documentar a resposta de repetição sem gerar novo fato.
- Retornar na prévia somente publicações da obra, com texto atual, data, contexto do marco, indicação de simulação/edição quando houver e acesso protegido às mídias.
- Documentar ordenação temporal e critério de desempate; retornar estado vazio válido para obra sem publicações.
- Garantir que exclusões e correções posteriores sejam refletidas na prévia, sem entradas fantasmas ou versões atuais incorretas.

**Pronto quando:**

Rascunho válido publicado aparece uma vez na prévia e continua consultável após reinício, com mídia que abre. Outro rascunho permanece ausente, e falha na validação ou persistência não o transforma parcialmente em publicado.

**Testes relacionados:**

CT-41 a CT-45: publicação, separação de rascunhos, mídia indisponível, repetição e persistência. CT-109 complementa recuperação dos arquivos no ambiente implantado.

**Dependências:**

UC-01 e UC-08. UC-09 fornece o fluxo de revisão, mas rascunho já válido pode ser publicado sem passar por edição.

---

## Cartão 11 — [UC-11] Corrigir atualização publicada

**Contexto e cobertura:**

Uma atualização já divulgada pode conter erro, mas corrigi-la não pode apagar o que foi informado antes. A construtora precisa justificar a correção e permitir comparar versões. Quando o original é um exemplo de engenheiro simulado, a origem continua preservada e a nova intervenção é atribuída à construtora.

Cobre **F-11, RN-06 e CA-05**.

**Arquivos previstos:**

- Criar/completar `app/avancos/routes.py`, `service.py` e `validacoes.py`; editar/reutilizar `repository.py`, `revisoes.py` e `midias.py`.
- Editar a leitura de publicação em `app/mudanças/ocorrencias/historico/` e o histórico em `app/historico/` quando necessário.
- Criar `tests/test_correcao_publicacoes.py`; complementar testes de publicação e acesso às mídias.

**Fazer:**

- Implementar o ramo publicado de `PATCH /avancos/{avancoId}`, compartilhando a rota com UC-09 e exigindo `motivo` não vazio.
- Permitir correção do texto e/ou mídias, mantendo uma composição válida. Definir os campos editáveis no contrato e rejeitar alterações de autoria original, vínculo e estado por esse fluxo.
- Preservar a versão anterior e registrar nova representação, campos alterados, motivo, autor da correção e instante. Recusar correção sem mudança efetiva.
- Gravar versão e conteúdo atual de modo consistente, com verificação de revisão para não perder correções simultâneas.
- Manter arquivos utilizados pelas versões anteriores; limpar somente novos uploads sem uso quando a operação falhar.
- Implementar `GET /avancos/{avancoId}/versoes` e devolver dados suficientes para comparação de texto/mídia e destaque dos campos alterados.
- Fazer a prévia refletir a versão vigente e indicar edição. Para original simulado, preservar origem e autoria original e informar a edição pela construtora.
- Publicar o evento de correção no contrato de leitura de UC-13, reaproveitando a versão registrada, sem gerar histórias contraditórias.

**Pronto quando:**

Uma publicação corrigida mostra a versão atual e permite consultar as anteriores em ordem. Duas correções não sobrescrevem a primeira; falha de banco/mídia mantém a publicação anterior intacta.

**Testes relacionados:**

CT-46 a CT-51: texto, mídia, motivo/alteração efetiva, falhas, origem simulada e cadeia de versões. CT-50 usa um exemplo preparado conforme UC-21; um registro de teste permite implementar antes da carga completa.

**Dependências:**

UC-01, UC-08 e UC-10. Compartilhar PATCH com UC-09; UC-21 fornece o exemplo integrado de engenheiro simulado.

---

## Cartão 12 — [UC-12] Alterar prazo ou situação de obra/marco

**Contexto e cobertura:**

Replanejar muda um compromisso ou a situação atual da execução. A decisão precisa aplicar o novo valor e explicar o anterior, o motivo e quem decidiu. Concluir e reabrir são decisões reversíveis com trilha preservada. Uma mudança não é apenas uma anotação de histórico: ela modifica efetivamente o objeto alvo.

Cobre **F-12, RN-01, RN-02, RN-07 e CA-06**.

**Arquivos previstos:**

- Criar `app/mudanças/routes.py`, `service.py`, `repository.py` e `validacoes.py`, sem sobrescrever o submódulo existente de publicação.
- Editar/reutilizar `app/obras/service.py`, `repository.py`, `app/marcos/service.py`, `repository.py` e `app/historico/repository.py`.
- Criar `tests/mudancas/test_mudancas.py`; complementar testes de estado de marco e alertas de obra. Registrar o blueprint em `api.py`.

**Fazer:**

- Implementar `POST /obras/{obraId}/mudancas`, documentando alvo, campo, novo valor e motivo. O servidor deve ler o valor anterior real; não confiar no antes enviado pelo navegador.
- Abranger prazo exato/intervalo da obra, período previsto do marco, estado de marco e ciclo de vida/conclusão da obra. Validar que o alvo pertence à obra.
- Reutilizar as validações de modalidade e período. Ao trocar a modalidade, retirar campos antigos incompatíveis da representação atual, preservando-os no histórico.
- Reutilizar UC-07 para estado de marco, inclusive aviso de dependência e confirmação. Impedir mudança por rota alternativa que pule essa regra.
- Para obra, aceitar os estados confirmados `planejada`, `em andamento`, `concluída` e `suspensa`, com motivo. Definir e documentar o campo de data efetiva de conclusão e sua regra de preenchimento/reabertura antes de fechar o cálculo histórico de atraso.
- Persistir alteração e evento antes/depois, motivo, autor e instante em uma operação consistente. Rejeitar valor inválido e proteger contra sobrescrita de versão concorrente.
- Impedir envio de `atrasada` como estado editável; recalcular alertas na consulta pelo planejamento vigente.
- Não oferecer exclusão isolada de mudança aplicada. O valor atual e a trilha devem permanecer coerentes em falhas e reinícios.

**Pronto quando:**

Alterar prazo, concluir ou reabrir atualiza o objeto e preserva o histórico. Falhar entre as gravações não deixa somente uma metade aplicada. O atraso acompanha o novo prazo e usa a conclusão efetiva para a avaliação histórica da obra concluída.

**Testes relacionados:**

CT-52 a CT-59: modalidades, prazo do marco, conclusão/reabertura, alerta derivado, validações e consistência. CT-26 a CT-30 também valem se o estado de marco for alterado por este caminho. Complementar CT-14 para obra concluída.

**Dependências:**

UC-01, UC-02 e UC-05; UC-07 para a transição de marco. Alinhar a data de conclusão com UC-03. Essa decisão deve ficar documentada, sem ser tratada como contrato já confirmado.

---

## Cartão 13 — [UC-13] Consultar histórico de mudanças e versões

**Contexto e cobertura:**

O histórico responde o que mudou, quando, por quem e por quê. A construtora deve conseguir acompanhar decisões sucessivas sem que a última esconda as anteriores. A leitura reúne alterações de obra, marcos e publicações, preservando o contexto e permitindo abrir a comparação correspondente.

Cobre **F-13, RN-06, RN-07 e CA-05/06**.

**Arquivos previstos:**

- Criar `app/historico/routes.py` e `service.py`; complementar `app/historico/repository.py`.
- Reutilizar os leitores de mudanças e versões de `app/mudanças/` e `app/avancos/`, criados nos cartões correspondentes.
- Criar `tests/historico/test_consultas.py` e registrar as rotas em `api.py`.

**Fazer:**

- Implementar `GET /obras/{obraId}/mudancas` e `GET /mudancas/{mudancaId}`. Definir se a listagem unifica correções de publicação ou referencia suas versões, deixando isso explícito para o React.
- Reunir os eventos já produzidos por UC-07, UC-11 e UC-12 sem recriá-los com informações diferentes.
- Normalizar a resposta para informar tipo de evento, alvo, campo(s), antes/depois, motivo, autor, instante e identificadores para consulta/comparação.
- Ordenar por instante com desempate estável, preservando duas mudanças consecutivas no mesmo campo. Não sobrescrever entradas antigas para representar somente o estado atual.
- Conferir obra e vínculos ao buscar eventos. Distinguir obra inexistente de obra existente sem histórico, que retorna lista vazia.
- Impedir edição/exclusão isolada da trilha aplicada. A remoção junto ao alvo segue UC-17/18.
- Não confundir a pasta atual de publicação `app/mudanças/ocorrencias/historico/` com um histórico de domínio completo: ela hoje atende publicação/prévia, não substitui este caso.

**Pronto quando:**

Uma obra com mudanças de prazo, estado de marco e correção publicada apresenta a sequência correta e permite comparar versões. Consultar não modifica registros, e histórico vazio não é tratado como erro.

**Testes relacionados:**

CT-60 a CT-63: consulta unificada, preservação de sucessivas mudanças, estado vazio e rejeição da exclusão isolada. Reutilizar CT-46/51 para conferir ligações às versões.

**Dependências:**

UC-01 e UC-02 para a leitura; UC-07, UC-11 e UC-12 como produtores dos eventos para validar a cobertura completa. A estrutura de consulta pode avançar com registros de teste.

---

## Cartão 14 — [UC-14] Registrar ocorrência

**Contexto e cobertura:**

Uma ocorrência registra um problema ou impedimento da obra, mesmo quando ainda não há solução. Ela pertence à obra e pode estar ligada a um marco, responsável e evidência, mas esses complementos são opcionais. Criar uma ocorrência como sem solução não significa que a construtora a aceitou; essa decisão pertence à UC-16.

Cobre **F-14, RN-08 e CA-07**.

**Arquivos previstos:**

- Criar `app/ocorrencias/__init__.py`, `routes.py`, `service.py`, `repository.py` e `validacoes.py`. Esse é o destino proposto para o módulo de negócio; não mover a publicação existente para cá.
- Reutilizar `app/integracoes/armazenamento.py` e a validação/limpeza de mídia existente, adaptando vínculos sem fingir que ocorrência é avanço.
- Criar `tests/test_ocorrencias.py`; atualizar `db.py` se necessário e registrar o blueprint em `api.py`.

**Fazer:**

- Implementar `POST /obras/{obraId}/ocorrencias`, `GET /obras/{obraId}/ocorrencias` e `GET /ocorrencias/{ocorrenciaId}`.
- Exigir título e descrição não vazios e estado inicial `aberta` ou `sem solução`. Gerar ID, autoria e data de registro no servidor.
- Aceitar marco, responsável e mídia ausentes. Quando informados, validar a existência e o vínculo aplicável, especialmente que o marco pertence à mesma obra.
- Documentar a referência de responsável de acordo com o cadastro de trabalhadores. Não impor responsável obrigatório nem criar novo perfil autenticável.
- Definir o formato de envio com mídia opcional, reutilizando validação de conteúdo, acesso protegido e metadados do armazenamento existente.
- Salvar ocorrência e vínculos coerentemente. Falha no arquivo ou no banco não deve produzir registro aparentemente completo; tratar uploads sem uso.
- Na consulta, diferenciar lista vazia de obra inexistente e retornar a ocorrência somente no contexto correto.

**Pronto quando:**

Uma ocorrência é criada sem opcionais e outra com marco/mídia, ambas recuperáveis após reinício. Marco de outra obra e estado inicial não permitido são rejeitados. `sem solução` continua sem aceitação até UC-16.

**Testes relacionados:**

CT-64 a CT-68: criação mínima, opcionais, validação dos vínculos/campos e persistência. Repetir CT-03 nos novos endpoints.

**Dependências:**

UC-01 e UC-02; UC-05 se houver marco; infraestrutura de mídia de UC-08 se houver arquivo. UC-19 é necessária para validar um responsável referenciado como trabalhador.

---

## Cartão 15 — [UC-15] Atualizar, resolver ou reabrir ocorrência

**Contexto e cobertura:**

A ocorrência acompanha o problema ao longo do tempo: pode ser corrigida, resolvida e reaberta. Corrigir o texto não é uma transição de estado. Resolver posteriormente uma ocorrência antes aceita sem solução não elimina a decisão anterior, que continua importante para explicar o acompanhamento.

Cobre **F-15**, edição descritiva de **F-16**, **RN-08 e CA-07**. A edição descritiva é P1; o acompanhamento de estado é P0.

**Arquivos previstos:**

- Editar/completar `app/ocorrencias/routes.py`, `service.py`, `validacoes.py` e `repository.py`, previstos em UC-14.
- Reutilizar `app/historico/repository.py` se adotado como armazenamento dos eventos da ocorrência.
- Criar `tests/test_atualizacao_ocorrencias.py`.

**Fazer:**

- Implementar `PATCH /ocorrencias/{ocorrenciaId}`, separando os campos de descrição dos comandos de transição no contrato.
- Atualizar apenas os campos descritivos enviados, validando vínculos opcionais e preservando estado quando não for solicitada transição.
- Aceitar os estados confirmados `aberta`, `resolvida` e `sem solução`; permitir resolução e reabertura. Não inventar estados adicionais.
- Exigir motivo para transição e registrar estado anterior, novo estado, motivo, autor e instante no servidor.
- Persistir estado e evento juntos, sem perda de transições concorrentes. Entrada inválida ou falha de banco deve preservar o estado e sua trilha.
- Manter as aceitações anteriores de UC-16 como fatos históricos; não apresentar aceitação antiga como se fosse uma resolução ou aceitação automática de um novo episódio.
- Expor a sequência de transições no detalhe ou em consulta documentada de histórico da ocorrência.

**Pronto quando:**

Uma ocorrência aberta pode ser resolvida e reaberta com motivos registrados. Edição de título/descrição não muda estado silenciosamente, e a sequência de decisões permanece após novas transições e reinício.

**Testes relacionados:**

CT-69 a CT-73: resolução, reabertura, edição descritiva, transição inválida e preservação de aceitação anterior. CT-73 é completado em conjunto com UC-16.

**Dependências:**

UC-01 e UC-14. UC-16 fornece o cenário de aceitação para a verificação conjunta; não bloqueia as transições básicas.

---

## Cartão 16 — [UC-16] Aceitar ocorrência sem solução

**Contexto e cobertura:**

Aceitar sem solução registra que a construtora reconheceu o problema e decidiu conviver com ele naquele momento. Isso não resolve nem apaga a ocorrência. A justificativa é obrigatória para que a decisão seja compreensível; uma medida compensatória pode existir, mas sua ausência não impede a aceitação.

Cobre a aceitação formal de **F-15, RN-08 e CA-07**.

**Arquivos previstos:**

- Editar/completar `app/ocorrencias/routes.py`, `service.py`, `validacoes.py` e `repository.py`.
- Criar `tests/ocorrencias/test_aceitacoes.py`; complementar as consultas de histórico/detalhe.

**Fazer:**

- Implementar `POST /ocorrencias/{ocorrenciaId}/aceitacoes` e `GET` no mesmo recurso.
- Validar existência da ocorrência e estado atual `sem solução` no momento da gravação. Não aceitar ocorrência aberta ou resolvida.
- Exigir justificativa não vazia e aceitar medida compensatória opcional. Gerar identidade da conta que aceitou e instante no servidor.
- Registrar a aceitação como fato ligado à ocorrência, preservando seu estado de problema sem solução; não criar um quarto estado apenas para juntar essas informações.
- Garantir consistência com transição concorrente: não gravar aceitação baseada em um estado que deixou de ser válido durante a operação.
- Documentar o tratamento de reenvio para evitar aceitação duplicada acidental; não sobrescrever uma aceitação anterior para esconder a história.
- Devolver justificativa, autoria e data na leitura. Resolução ou reabertura posterior preserva o registro antigo, sem tratá-lo como decisão atual para qualquer novo estado.

**Pronto quando:**

Uma ocorrência sem solução é aceita com justificativa e sem medida compensatória, e a decisão reaparece após reinício. Ausência de justificativa ou estado inadequado não cria aceitação nem altera a ocorrência.

**Testes relacionados:**

CT-74 a CT-78: aceitação válida, justificativa obrigatória, estado incompatível, compensação opcional e releitura. CT-73 confirma a preservação após resolver/reabrir em UC-15.

**Dependências:**

UC-01 e UC-14. UC-15 é necessária para validar a preservação em transições posteriores.

---

## Cartão 17 — [UC-17] Excluir obra ou marco com todos os dependentes

**Contexto e cobertura:**

Excluir uma obra ou marco é uma remoção definitiva do conjunto dependente, incluindo a trilha que só tem sentido naquele objeto. A interface precisa identificar o alvo e a extensão da perda antes de confirmar. A API deve tratar a cascata inteira, preservando outros projetos e sem deixar arquivos ou referências esquecidos.

Cobre a exclusão em cascata de **F-19, RN-09 e CA-09**.

**Arquivos previstos:**

- Editar `app/obras/routes.py`, `repository.py`, `app/marcos/routes.py`, `repository.py` e os repositórios dos dependentes.
- Criar `app/obras/exclusoes.py` e `app/marcos/exclusoes.py` como destinos propostos para orquestrar a cascata, evitando duplicação entre as rotas.
- Reutilizar armazenamento de mídia e os vínculos de `trabalhadores.py`. Criar `tests/test_exclusao_cascata.py`.

**Fazer:**

- Implementar `DELETE /obras/{obraId}` e `DELETE /marcos/{marcoId}`, validando sessão, existência e vínculos antes de qualquer remoção.
- Documentar o protocolo de confirmação com React. A tela mostra nome e extensão da perda; cancelar não envia DELETE. Se o contrato usar campo de confirmação no servidor, validá-lo explicitamente e cobri-lo em teste.
- Mapear e remover obra/marco, avanços, publicações, versões, mídias, mudanças, ocorrências e respectivos históricos/aceitações e exemplos simulados dependentes.
- Ao excluir marco, retirar também relações em que outros marcos dependem dele, preservando esses outros marcos.
- Alinhar e registrar a política de ocorrência ligada ao marco: a proposta atual é removê-la na cascata. A documentação ainda pede confirmação dessa decisão; não apresentar como decisão já aprovada.
- Ao excluir obra, remover seu vínculo dos trabalhadores. Preservar cadastro e vínculo B quando a pessoa também pertence a B; a documentação trata essa política como proposta a confirmar. Não excluir o trabalhador globalmente por um vínculo removido.
- Integrar a limpeza externa sem apagar arquivos ainda referenciados fora do conjunto. Usar estratégia consistente no Atlas e pendências duráveis/repetíveis para Cloudinary.
- Em falha parcial ou resultado indeterminado, retornar erro/pendência rastreável e permitir recuperação; `204` somente quando a exclusão estiver concluída conforme o contrato.

**Pronto quando:**

Excluir obra remove seus dependentes e vínculos exclusivos; excluir marco preserva outros marcos e retira referências ao alvo. Reinício não restaura os dados, e falha externa não é apresentada como cascata completamente concluída.

**Testes relacionados:**

CT-79 a CT-85: confirmação, cascata, ausência de órfãos, dependências, inexistência, falha externa e persistência da exclusão. CT-100: trabalhador com mais de uma obra. Fechar as políticas pendentes antes de tratar CT-82/100 como contrato final.

**Dependências:**

UC-01 e os módulos dos dados a remover: UC-02, UC-05/06, UC-08/10/11, UC-12/13, UC-14/16, UC-19/20 e UC-21. A implementação pode avançar por conjunto; o aceite exige a cascata completa e as políticas registradas.

---

## Cartão 18 — [UC-18] Excluir avanço ou ocorrência individualmente

**Contexto e cobertura:**

A construtora pode retirar um registro indevido sem apagar o marco ou a obra inteira. Um avanço publicado excluído sai da prévia com suas versões e mídias; uma ocorrência excluída leva seu histórico e aceitações. A remoção precisa preservar registros vizinhos e informar claramente o que será perdido.

Cobre a exclusão individual de **F-19 e CA-09**.

**Arquivos previstos:**

- Editar/completar `app/avancos/routes.py`, `service.py`, `repository.py`, `app/ocorrencias/routes.py`, `service.py` e `repository.py`.
- Reutilizar o mecanismo de limpeza de mídias e os repositórios de versões/histórico/publicação.
- Criar `tests/test_exclusao_registros.py`; compartilhar os testes/regras de exclusão de rascunho com UC-09.

**Fazer:**

- Implementar `DELETE /avancos/{avancoId}` para avanço publicado, reutilizando o mesmo endpoint e a regra de rascunho de UC-09; implementar `DELETE /ocorrencias/{ocorrenciaId}`.
- Validar ID, existência e cadeia real de vínculos. Se a requisição levar um contexto de obra/marco, conferir a correspondência antes de excluir; não confiar em IDs ou referências fornecidos separadamente.
- Remover versões, fato de publicação, mídias exclusivas e exemplos diretamente dependentes do avanço. Atualizar a prévia para que o item desapareça.
- Remover histórico de transições e aceitações da ocorrência e suas mídias exclusivas, preservando obra, marco e outras ocorrências.
- Aplicar a confirmação na interface antes da requisição, identificando o alvo e os dependentes. Cancelar não executa mutação.
- Não apagar arquivo ainda utilizado por outro registro fora do conjunto; tratar falha externa com pendência durável e sem sucesso falso.
- Tornar a recuperação/repetição segura, com resposta de inexistência ou repetição documentada, sem atingir um registro diferente.

**Pronto quando:**

Avanço/ocorrência confirmados desaparecem das consultas após reinício e não deixam versões, aceitações ou arquivos exclusivos órfãos. Registros da mesma obra e de outra obra permanecem intactos.

**Testes relacionados:**

CT-86 a CT-89: confirmação/cancelamento, remoção de publicação, ocorrência com aceitação, manipulação de vínculos e persistência. Reutilizar CT-39 para o ramo de rascunho e CT-84 para falha de mídia.

**Dependências:**

UC-01, UC-08/09, UC-10/11 e UC-14/16, conforme o registro excluído. Compartilhar limpeza com UC-17; não exigir que UC-17 esteja concluída para implementar exclusão individual.

---

## Cartão 19 — [UC-19] Cadastrar e consultar trabalhadores da obra

**Contexto e cobertura:**

O cadastro permite saber quem participa de cada obra, com dados de contato e cargo. É administrado pela construtora e não concede login ao trabalhador. A pessoa pode participar de mais de uma obra; a listagem deve refletir vínculos existentes, sem apresentar alguém em um projeto ao qual não está associado.

Cobre cadastro e leitura de **F-20 e CA-10**.

**Arquivos previstos:**

- Editar/reutilizar `trabalhadores.py` e `validacoes.py`, mantendo a implementação atual em vez de exigir migração para `app/trabalhadores/`.
- Complementar `tests/trabalhadores/test_cadastro.py`, `test_consultas.py`, `test_rotas.py` e `test_persistencia_atlas.py`.

**Fazer:**

- Revisar `POST /trabalhadores/obra/{obraId}/` e `GET /trabalhadores/obra/{obraId}/`, já existentes. Documentar esses caminhos reais para o frontend; a rota proposta `/obras/{id}/trabalhadores` não deve ser presumida implementada.
- Exigir nome, email, telefone com DDD e cargo; reutilizar validação/normalização atual, incluindo telefone com 10 ou 11 dígitos.
- Validar a obra pelo identificador atual do MongoDB e sua existência antes do cadastro. Atualizar a referência antiga de CT-93 a “código positivo” para o contrato real de ID, sem enfraquecer o teste de obra inexistente.
- Gerar ID, estado ativo e data de cadastro no servidor; adicionar o vínculo à obra e persistir no Atlas.
- Disponibilizar consulta individual por identificador, criando `GET /trabalhadores/{trabalhadorId}/` se necessária para abrir o detalhe e para o endereço retornado na criação.
- Distinguir obra sem trabalhadores, obra inexistente, trabalhador ausente e falha no banco. Preservar os filtros já existentes sem usá-los como substituto do detalhe por ID.
- Manter proteção da construtora em todas as rotas. Não gerar token, senha ou sessão de trabalhador.

**Pronto quando:**

Um trabalhador válido é cadastrado, listado na obra e consultado após reinício. Não aparece em obra sem vínculo. Campo inválido, obra ausente ou requisição sem sessão não cria nem expõe cadastro.

**Testes relacionados:**

CT-90 a CT-95: cadastro, validações, existência da obra, consulta persistente e autenticação. Registrar a adequação de CT-93 ao formato de ID efetivamente utilizado.

**Dependências:**

UC-01 e UC-02. UC-20 complementa manutenção e remoção de vínculos.

---

## Cartão 20 — [UC-20] Editar vínculos/dados e excluir trabalhador

**Contexto e cobertura:**

A equipe da obra muda: a construtora precisa corrigir contatos, cargos e vínculos sem recriar a pessoa. Um trabalhador pode ficar temporariamente sem obra. Excluir o cadastro é diferente de retirá-lo de uma obra, e uma exclusão de obra não deve eliminar sua participação em outra.

Cobre manutenção e exclusão de **F-20 e CA-10**.

**Arquivos previstos:**

- Editar/reutilizar `trabalhadores.py` e `validacoes.py`.
- Complementar `tests/trabalhadores/test_rotas.py` e `test_persistencia_atlas.py`; criar `tests/trabalhadores/test_manutencao.py` se os cenários não couberem nos arquivos existentes.
- Integrar a retirada de vínculos com o mecanismo de exclusão de obra de UC-17.

**Fazer:**

- Revisar `PATCH /trabalhadores/{trabalhadorId}/` e `DELETE /trabalhadores/{trabalhadorId}/`, existentes.
- Permitir atualização parcial dos campos aceitos no contrato, reutilizando normalização de nome, telefone e cargo; preservar os não enviados.
- Receber a lista de obras como substituição explícita dos vínculos, validando todos os IDs e a existência de cada obra antes de salvar.
- Permitir lista vazia e impedir duplicação de vínculos. Rejeitar JSON vazio, campos desconhecidos e referências inválidas sem atualização parcial.
- Na exclusão, validar alvo e proteger a requisição. A interface identifica o trabalhador e pede confirmação antes de enviar DELETE.
- Reutilizar uma operação de retirada de vínculo ao excluir obra A, preservando cadastro e obra B. Registrar a política proposta com UC-17 antes de encerrar CT-100.
- Revisar referências de responsável em ocorrências ao remover cadastro: documentar o tratamento adotado para não deixar referência pendente nem apagar a autoria histórica de decisões.
- Tratar falha de banco sem sucesso falso e comprovar a permanência da edição/exclusão após reinício. Nenhum fluxo cria autenticação de trabalhador.

**Pronto quando:**

Dados e vínculos são atualizados parcialmente, inclusive lista vazia. Cadastro excluído continua ausente após reinício, e excluir uma obra não elimina o vínculo válido com outra.

**Testes relacionados:**

CT-96 a CT-101: edição, troca/retirada de vínculos, entradas inválidas, confirmação, cascata da obra e persistência. CT-100 é executado com UC-17, após registrar a política.

**Dependências:**

UC-01, UC-02 e UC-19. UC-17 completa o cenário de exclusão de obra; UC-14 deve ser considerada se responsável usar referência a trabalhador.

---

## Cartão 21 — [UC-21] Consultar dados simulados do comprador e do engenheiro

**Contexto e cobertura:**

O MVP demonstra como avaliações, dúvidas e registros de outros participantes poderiam contextualizar a obra no futuro. Esses exemplos são pré-carregados e precisam ser apresentados como simulação. Não representam comentários reais nem autorizam login de comprador/engenheiro. O avanço do engenheiro simulado pode ser corrigido pela construtora preservando a origem.

Cobre **F-17, F-18, RN-10 e CA-08**.

**Arquivos previstos:**

- Criar `app/simulados/__init__.py`, `routes.py`, `service.py` e `repository.py` como destino proposto para a consulta.
- Criar `scripts/carregar_dados_demonstracao.py` e `tests/test_dados_simulados.py`; registrar o blueprint em `api.py`.
- Reutilizar `app/avancos/` e a leitura de prévia/publicação para autoria/origem simulada e correção.

**Fazer:**

- Preparar carga repetível de exemplos fictícios de avaliação, compreensão e dúvida do comprador, ligados a obra, marco ou atualização específica.
- Preparar avanço atribuído a engenheiro simulado, com campos explícitos de origem, identidade fictícia e vínculos válidos. A carga não deve duplicar exemplos ao ser repetida nem remover dados alheios ao cenário.
- Implementar `GET /obras/{obraId}/feedback-simulado` com informações de alvo e origem suficientes para a interface apresentar cada exemplo no contexto correto.
- Documentar filtros/consultas por marco ou atualização, quando necessários. Validar que o alvo pertence à obra; não misturar feedbacks de objetos diferentes.
- Expor `simulado` de forma inequívoca nas respostas. Para avanço corrigido, preservar autoria original, versões e autoria da construtora na correção.
- Não criar endpoint funcional para comprador enviar mensagem/avaliação, nem cadastro ou login desses perfis. A carga ocorre por procedimento de demonstração, não por formulário do produto.
- Integrar remoção dos exemplos à exclusão dos objetos correspondentes em UC-17/18 e retornar lista vazia quando não houver exemplos.

**Pronto quando:**

Cada exemplo aparece somente no contexto vinculado, marcado como simulado, e o avanço do engenheiro mantém essa origem após correção. Reexecutar a carga não duplica dados; excluir o alvo não deixa exemplo órfão.

**Testes relacionados:**

CT-102 a CT-106: tipos/origem, contexto correto, engenheiro simulado, impossibilidade de interação real e exclusão dos dependentes. CT-50 verifica a correção do avanço simulado com UC-11. A marcação visual é validada com o frontend.

**Dependências:**

UC-01, UC-02, UC-05 e UC-08/10 para os objetos de exemplo. UC-11 para a correção integrada; UC-17/18 para verificar a limpeza dos exemplos após exclusão.

---

## Ordem prática para fechar o projeto

1. Revisar a base existente de UC-01 a UC-07 e UC-19/20; resolver os contratos que afetam outros cartões. Existência de implementação não equivale a conclusão validada.
2. Concluir o fluxo de rascunho UC-08/09 e integrá-lo à publicação UC-10, já existente; em seguida, correção UC-11.
3. Concluir mudanças UC-12 e sua consulta em UC-13; fechar a data efetiva de conclusão para o cálculo de UC-03.
4. Concluir ocorrências UC-14/15/16 e carregar os exemplos de UC-21. Esses trabalhos podem avançar em paralelo ao fluxo de publicação quando as dependências correspondentes existirem.
5. Fechar UC-17/18 e os cenários de vínculos de UC-20 com todos os tipos de dependentes presentes; registrar as políticas pendentes antes do aceite.
6. Executar CT-111 no ambiente publicado e registrar por cartão o resultado, responsável, data e evidência. Priorizar correções de P0 antes de polir os trechos P1 de UC-04/15.

Esta ordem organiza o trabalho dentro dos 21 cartões. Não acrescenta casos de uso ao escopo nem comprova que os CT foram executados nesta revisão.
