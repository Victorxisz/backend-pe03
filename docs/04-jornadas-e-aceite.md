# 4. Jornadas e critérios de aceite

Os critérios abaixo descrevem resultados observáveis no navegador e no servidor. A equipe pode criar uma issue para cada critério ou agrupá-los em entregas pequenas. A ordem segue o caminho de valor, não camadas técnicas isoladas.

## Jornada principal de demonstração

**Cenário fictício:** a construtora Horizonte entra com sua conta, cria a obra residencial *Residencial Aurora*; planeja os marcos *Fundação*, *Estrutura* e *Alvenaria*; cadastra um trabalhador; registra avanço com foto, vídeo e documento; publica uma atualização; altera o prazo de *Estrutura* com motivo; registra uma ocorrência sem solução e aceita sua condição com justificativa. Após reiniciar a aplicação, a mesma conta consulta o histórico.

O cenário deve usar registros fictícios explicitamente identificados. Um dado de avaliação ou dúvida do comprador pré-carregado pode ser exibido como contexto, mas não deve parecer enviado ao vivo.

## Critérios de aceite por entrega

### CA-01 — Acesso (`F-01`)

- A conta pré-configurada da construtora consegue entrar e sair.
- Uma pessoa sem sessão não consulta nem altera dados das obras pela interface **ou diretamente pela API**.
- Um registro novo identifica a conta que realizou a ação; senhas e chaves não ficam no Git.

### CA-02 — Obra e busca (`F-02` a `F-05`)

- A construtora cria casa ou obra de apartamentos com nome, localização, descrição, data de início e prazo **exato ou em intervalo**.
- Não é possível informar simultaneamente os dois formatos de prazo nem um intervalo cujo fim preceda o início.
- Após criar a obra, ela aparece na lista; permanece após atualizar a página ou reiniciar o servidor.
- É possível filtrar por nome, situação, cliente de referência, data de entrega e data de registro. Os filtros mostram claramente quando não há resultados.
- Os estados planejada, em andamento, concluída e suspensa são separados do único alerta atrasada, calculado conforme RN-02. A conclusão efetiva é registrada automaticamente pelo servidor.

### CA-03 — Marcos e dependências (`F-06` e `F-07`)

- Um marco com nome, descrição e período previsto pode ser criado e consultado dentro da obra correta.
- A construtora muda manualmente seu estado entre `a iniciar`, `em andamento` e `concluído`.
- A relação “Alvenaria depende de Estrutura” aparece nos detalhes. O servidor rejeita dependência do próprio marco, de outra obra ou que forme ciclo.
- Ao concluir Alvenaria antes de Estrutura, a interface avisa sobre a dependência e permite prosseguir.

### CA-04 — Evidências e publicação (`F-08` a `F-10`)

- Um avanço com data, descrição e ao menos uma mídia é vinculado a um marco. Fotos, vídeos e documentos podem ser enviados, recuperados e identificados pelo tipo.
- O avanço nasce como rascunho e pode ser corrigido ou retirado antes da publicação.
- Ao publicar, o servidor registra quem publicou e quando; o avanço aparece na prévia da linha do tempo publicada. Rascunhos não aparecem nessa prévia.
- A publicação continua visível após reiniciar o servidor.

### CA-05 — Correção publicada (`F-11`)

- A construtora informa motivo para corrigir uma atualização publicada.
- A consulta mostra versão atual, anterior, campos alterados, autor e data de cada edição.
- Se um avanço pré-carregado atribuído ao engenheiro for alterado, a interface sinaliza “editado pela construtora”, exibe o texto anterior e destaca onde ocorreu a alteração.

### CA-06 — Mudança aplicada (`F-12` e `F-13`)

- A construtora altera prazo de obra, prazo de marco ou estado previsto, informando motivo.
- O valor novo aparece no cadastro; o valor anterior e o contexto permanecem no histórico, com autor e data.
- Se a alteração não puder ser aplicada, o servidor não salva um histórico que afirme que ela ocorreu.

### CA-07 — Ocorrência e aceitação (`F-14` a `F-16`)

- É possível registrar ocorrência na obra como `aberta` ou `sem solução`, com título, descrição e data. Marco, mídia e responsável podem ficar vazios.
- A ocorrência pode mudar de estado; cada mudança relevante registra autor e data. Uma ocorrência pode ser resolvida ou posteriormente reclassificada.
- Para registrar a aceitação de uma ocorrência sem solução, a construtora informa justificativa. A interface mostra quem aceitou e quando. Não exige medida compensatória.
- A ocorrência permanece consultável após atualizar a página ou reiniciar o servidor.

### CA-08 — Dados simulados (`F-17` e `F-18`)

- Exemplos de avaliação, compreensão e dúvida do comprador são pré-carregados e aparecem associados à obra, ao marco ou a uma atualização específica.
- Os exemplos são identificados como **simulados** e não podem ser atribuídos a um comprador autenticado.
- Um avanço de engenheiro simulado pode ser mostrado, mas não existe login ou criação de avanço pelo perfil de engenheiro no MVP.

### CA-09 — Exclusão definitiva (`F-19`, RN-09)

- Obra e marco podem ser excluídos definitivamente junto com seus registros dependentes. A interface identifica o alvo, informa a perda do histórico e pede confirmação.
- Cancelar a confirmação não altera dados. Confirmar remove o conjunto e não deixa referências órfãs, inclusive mídias externas e dados simulados associados.
- A exclusão isolada de mudança já aplicada não está definida como ação do MVP; o histórico deve permanecer íntegro enquanto o objeto principal existir.

### CA-10 — Trabalhadores (`F-20`)

- A construtora cadastra trabalhador com nome, email, telefone e cargo e vincula-o a uma obra existente; lista e consulta os cadastrados por obra.
- Pode corrigir os dados, alterar vínculos e excluir o trabalhador, com confirmação. Trabalhador não recebe login no MVP.
- A API rejeita dados inválidos e vínculo com obra inexistente; os dados permanecem após reinício.

## Telas mínimas sugeridas

1. Login.
2. Lista de obras com filtros e criação.
3. Detalhe da obra com seus marcos, mudanças, ocorrências e prazo.
4. Detalhe do marco com dependências e avanços.
5. Registro/revisão de avanço e anexos.
6. Prévia de atualizações publicadas e versões.
7. Registro e acompanhamento de ocorrência.
8. Histórico de mudanças e registros simulados do comprador.

É aceitável combinar algumas dessas telas em abas ou painéis. O protótipo visual anterior serve como referência para hierarquia e navegação, mas a equipe deve priorizar estados reais da aplicação (vazio, carregando, erro, rascunho e publicado) antes de polimento.

## Demonstração final e verificação

Executar CA-01 a CA-08 **no endereço implantado em EC2**, com o React chamando o Flask por HTTP. Confirmar a persistência no MongoDB Atlas e uma chamada real à API externa escolhida. A entrega só está pronta quando outra pessoa da equipe consegue repetir o roteiro a partir do README de cada repositório, sem depender do computador de quem desenvolveu.
