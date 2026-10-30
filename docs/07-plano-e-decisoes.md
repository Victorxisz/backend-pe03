# 7. Plano de entrega e registro de decisões

Esta página é a referência para manter o escopo de **03/11/2026** sob controle. Ela não substitui o quadro de tarefas: registra a sequência de valor, o que conta como pronto e o que ainda precisa de decisão.

## Ordem de construção

| Até | Resultado demonstrável | Funcionalidades |
| --- | --- | --- |
| 16/10 | Repositórios de cliente e servidor definidos, contrato HTTP inicial acordado, professor consultado sobre tema e API externa, uma conta de demonstração planejada | Base de F-01 |
| 20/10 | React cria uma obra e um marco por HTTP; Flask salva no Atlas e devolve os dados; ambos aparecem após recarregar | F-01 a F-03, F-06 |
| 24/10 | Marcos com dependências, filtros essenciais, avanço com os três tipos de mídia e publicação visível na prévia | F-04, F-07 a F-10 |
| 28/10 | Correção versionada, mudança aplicada com histórico e ocorrência com aceitação sem solução | F-11 a F-15 |
| 30/10 | Fluxo principal completo e integrado no EC2; política de exclusão decidida; congelar novas funcionalidades | CA-01 a CA-07, F-19 |
| 02/11 | Corrigir falhas, testar o login, persistência, API externa, dados simulados e roteiro de apresentação | CA-01 a CA-10 |
| 03/11 | Demonstração repetível e entrega dos dois repositórios e das credenciais pelo canal exigido | MVP |

As datas são **metas de controle**, não estimativas garantidas. Se o primeiro caminho React → Flask → Atlas não funcionar até 20/10, reduzir itens P1 antes de ampliar telas. Publicar no EC2 cedo o suficiente para descobrir problemas de rede, configuração e arquivos antes da última semana.

## Trabalho em equipe sem gerente central

- Manter um quadro único para issues dos **dois repositórios**, com colunas `A fazer`, `Pronto`, `Em andamento`, `Em revisão` e `Concluído`.
- Cada issue indica `F-xx`, `CA-xx`, dono, resultado observável e dependências. Quem a assume atualiza seu estado.
- Dividir o trabalho em entregas verticais: uma parte da tela, da API e da persistência que funcione junta. Evitar considerar “backend pronto” se ainda não existe uso pelo React.
- Pedir que outra pessoa revise cada entrega, especialmente regras de prazo, histórico e permissões.
- Fazer demonstração semanal do que está integrado; uma pessoa diferente facilita cada reunião. Prioridades mudam por decisão do grupo, registrada no quadro.

### Modelo curto de issue

```text
Título: [F-06] Criar marco dentro de uma obra
Valor: a construtora consegue planejar uma entrega verificável.
Critérios: CA-03 — criar, consultar após recarregar, rejeitar período inválido.
Dependência: F-02 — obra criada.
Pronto quando: React usa a API Flask no ambiente integrado; dado persiste no Atlas;
outra pessoa revisou; documentação do contrato foi atualizada se mudou.
```

## Definição de pronto

Uma funcionalidade só está concluída quando: (1) segue a regra de domínio; (2) funciona pela interface com resposta real da API; (3) persiste no Atlas quando deve; (4) apresenta estado de erro compreensível; (5) não expõe credenciais nem dados de outra sessão; (6) foi revisada por outra pessoa; e (7) pode ser repetida na demonstração. Para mídia, também é necessário abrir o arquivo depois do envio. Para API externa, registrar uma chamada bem-sucedida e o comportamento quando ela falha.

## Decisões confirmadas

| ID | Decisão | Consequência |
| --- | --- | --- |
| D-01 | Uma construtora fictícia, com obras residenciais de casas e apartamentos | Escopo comercial inicial claro; modelo pode evoluir depois. |
| D-02 | Apenas o perfil da construtora é funcional no MVP, com uma conta | Engenheiro e comprador aparecem como dados simulados, não como logins. |
| D-03 | Obra aceita data exata **ou** intervalo estimado de entrega | Prazo precisa ser representado como escolha explícita. |
| D-04 | Marcos pertencem diretamente à obra; podem depender de outro marco | Sem entidade “etapa” no MVP. |
| D-05 | Avanço aceita foto, vídeo e documento, sem frequência diária obrigatória | Armazenamento de mídia é parte do fluxo central. |
| D-06 | Construtora publica avanços; correção publicada mantém versão anterior e autoria | Rascunho e conteúdo publicado têm tratamentos distintos. |
| D-07 | Mudanças alteram prazo/estado e guardam antes, depois, motivo, data e autor | História e valor atual precisam ser consistentes. |
| D-08 | Ocorrência pode iniciar aberta ou sem solução e mudar de estado; aceitação sem solução exige justificativa | Registrar quem aceitou e quando. |
| D-09 | Excluir obra ou marco remove também todos os dependentes, após aviso e confirmação | Implementação deve evitar órfãos e tratar arquivos externos. Mudança aplicada não é excluída isoladamente. |
| D-10 | Código do React e do Flask ficará em repositórios diferentes; ambos já existem no GitHub | Esta documentação pode ser referenciada pelos dois. |
| D-11 | Avaliações, compreensão e dúvidas do comprador serão pré-carregadas e associadas à obra, marco ou atualização | Mostrar origem simulada; não implementar comentários reais. |
| D-12 | Uma obra tem um cliente de referência no MVP | Não criar vínculo de vários compradores nem login de cliente. |
| D-13 | Crítica e atrasada foram unificadas no único alerta atrasada; ele deriva do prazo vencido | Filtrar ciclo de vida e alertas separadamente. |
| D-14 | Dependência pendente gera aviso, não bloqueio de conclusão | A decisão de prosseguir fica com a construtora. |
| D-15 | Obra e marco concluídos podem ser reabertos | Guardar antes/depois, motivo, autor e data. |
| D-16 | Cadastrar trabalhadores entra no MVP, como ação da construtora | Trabalhador não autentica; a rota existente deve ser integrada a obras reais. |
| D-17 | A API externa deve permitir uso totalmente gratuito para o MVP | Limites e termos de uso precisam ser conferidos antes da escolha; o professor ainda valida. |

## Pendências que podem mudar o contrato

| ID | Decisão necessária | Recomendação para destravar | Prazo sugerido |
| --- | --- | --- | --- |
| P-01 | Professor validar o tema e dizer quais APIs externas atendem à exigência | Apresentar Cloudinary para mídia e ViaCEP como alternativa complementar | Antes de integrar mídia |
| P-02 | Escolher provedor de armazenamento de foto, vídeo e documento | Comparar Cloudinary e S3 por acesso privado, limites e esforço; implementar um primeiro | 17/10 |
| P-03 | Definir exclusão isolada de um registro histórico já aplicado, se algum dia necessária | Fora do MVP; preservar histórico enquanto objeto principal existir | Após o MVP |
| P-04 | Resolvida em 30/10: conclusão efetiva automática no servidor | Usar a conclusão para atraso histórico; preservar conclusões anteriores ao reabrir | Confirmada |
| P-07 | Fixar tamanho máximo, tipos MIME e política de acesso às mídias | Usar valores pequenos no MVP e URLs de acesso restrito/temporário | Antes de F-08 |

## Riscos que merecem atenção cedo

- **Três tipos de mídia em prazo curto:** testar pelo menos um arquivo real de cada tipo no ambiente publicado antes de polir a interface.
- **Histórico versus exclusão definitiva:** uma exclusão em cascata precisa retirar dados internos e arquivos externos de forma consistente; não expor exclusão isolada de mudança aplicada.
- **Estado da obra:** uma obra pode estar em andamento e atrasada ao mesmo tempo; não gravar tudo num enum único.
- **API externa sem aval:** uma integração tecnicamente funcional pode não atender à rubrica. Obter resposta do professor enquanto o fluxo principal é construído.
- **Protótipo visual anterior:** reutilizar padrões de navegação e conteúdo, mas substituir simulações por operações reais e estados de erro/carregamento.
