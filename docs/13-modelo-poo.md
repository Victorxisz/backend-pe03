# Modelo e organização do backend com POO

Decisões confirmadas em 30/10/2026 e responsabilidades efetivamente implementadas.
Esta página orienta a manutenção do código; o PDF é uma referência conceitual,
não uma exigência de criar uma coleção, um serviço ou uma hierarquia de herança
para cada caixa desenhada.

## Separação de responsabilidades

| Camada | Local | Responsabilidade |
| --- | --- | --- |
| Domínio | `app/dominio/` | Prazo, atraso, transições, dependências e invariantes. Não importa Flask, BSON, banco ou provedor de arquivos. |
| Aplicação | `service.py` de cada módulo | Serviços com repositórios e relógio recebidos no construtor; coordenam leitura, validação e gravação. |
| Persistência | `repository.py` e `rascunhos_repository.py` | Consultas, controle de concorrência e transações MongoDB. |
| HTTP | `routes.py`, `construtora.py`, `trabalhadores.py` | Autenticação, entrada, representação e códigos de resposta. |
| Integração | `app/integracoes/` e serviço de mídias | Upload, recuperação e limpeza de arquivos externos. |
| Inicialização | `app.create_app()` e `api.py` | Composição do Flask, extensões e registro dos blueprints. |

`db.py` preserva os nomes das coleções já utilizados e usa `BancoMongo`, definido
em `app/database.py`. Não foram executadas migrações nem alterações no Atlas.

Os módulos de serviço e repositório mantêm fachadas com os nomes das funções
anteriores para preservar os imports existentes. As implementações agora estão
nos objetos. Novos consumidores podem receber os serviços/repositórios no
construtor, sem criar uma nova conexão ou acessar `request` dentro do domínio.

## Objetos e regras

- `PrazoEntrega`: objeto imutável. Aceita data exata **ou** intervalo estimado;
  não aceita mistura, datas inexistentes ou intervalo invertido.
- `Obra`: controla prazo, ciclo de vida e conclusão. O único alerta é `atrasada`.
  Até o último dia previsto, a obra não está atrasada. Depois dele, está.
- `Marco`: controla as transições e exige motivo; dependências pendentes exigem
  confirmação para concluir, mas não bloqueiam definitivamente a decisão.
- `Dependencia` e `GrafoDependencias`: representam o vínculo e verificam ciclos,
  incluindo os indiretos. O serviço verifica pertencimento à mesma obra.
- `Mudanca`: registro com alvo, campo, antes/depois, motivo, autor e instante.
- `Avanco`: diferencia rascunho e publicado e impede edição simples de publicação.
  A edição deve manter pelo menos uma mídia.
- `Midia`: valida tipo, nome, MIME e tamanho dos metadados. A validação do conteúdo
  binário e a referência específica de Cloudinary ficam fora do domínio.
- `Construtora`: representa a empresa e sua conta, conforme a simplificação do MVP.
  Hash e tokens não são devolvidos pela representação da entidade.
- `Trabalhador`: pertence a uma construtora e pode participar de zero ou mais
  obras. Não tem login. Novos cadastros recebem `construtora_id` da sessão,
  independentemente dos dados enviados pelo cliente.

Os objetos de domínio representam as regras, enquanto os documentos persistidos
também contêm os dados descritivos e metadados necessários à apresentação.
Não usar herança entre construtora e trabalhador: seus papéis e ciclos de vida
são diferentes. Preferir composição e dependências explícitas.

## Atraso e conclusão automática

1. Em `data_exata`, o limite é `entrega.data`.
2. Em `intervalo_estimado`, o limite é `entrega.fim`.
3. Para uma obra não concluída, comparar o limite com o dia do relógio do servidor
   em UTC, consistente com os instantes de auditoria atuais.
4. Ao concluir, registrar automaticamente `data_conclusao` no servidor. Depois,
   usar essa data para avaliar se a entrega ocorreu com atraso.
5. Reabrir limpa a conclusão **atual**; as datas anteriores permanecem no histórico.
6. Uma repetição da conclusão já aplicada não altera a data nem duplica o evento.

`PATCH /obras/{id}/estado` recebe somente `estado` e `motivo`. A rota é protegida
pela mesma autenticação das demais operações de obra. Datas e autoria não são
aceitas do cliente. O PATCH descritivo continua sem aceitar prazo ou conclusão.

Estado, data de conclusão e evento em `historico_estados` são gravados juntos
no documento da obra, com comparação da revisão anterior. Assim, uma falha não
deixa estado aplicado sem histórico. O histórico de estados de marco mantém sua
persistência transacional já utilizada em `tbl_historico`.

`critica` de registros antigos é ignorado na representação e no cálculo;
novas obras não gravam esse campo. A consulta não altera documentos antigos e
não inventa data de conclusão para registros que ainda não a possuem.

## Avanços e mídia

`ServicoAvancos` concentra edição e exclusão de rascunhos. A edição revalida o
estado, a revisão e as mídias em uma transação. Arquivos antigos são removidos
somente após o commit e quando não existem outras referências. Falhas de limpeza
mantêm uma tarefa em `tbl_limpezas_midias`; isso permite retomada.
A edição está disponível no serviço; a rota HTTP PATCH de rascunho ainda não está
registrada neste checkout.

Após integrar a `main`, cadastro e consultas de avanços também passam pelo
`ServicoAvancos`. Cadastro e metadados em `tbl_midias` são persistidos na mesma
transação, para que a publicação encontre as mesmas evidências do cadastro.
O JSON mantém o contrato recebido da `main`; referências do provedor permanecem
privadas. Os testes locais simulam rollback e não comprovam uma transação real
do Atlas. A exclusão considera também tarefas de limpeza de edições anteriores
e preserva metadados referenciados por publicações ou outros registros.

`ServicoPublicacoes` fica em `app/publicacoes/`, separado de ocorrências. Os
imports antigos em `app/mudanças/ocorrencias/historico/` permanecem como aliases.
A publicação preserva verificação de mídia recuperável, snapshot e idempotência.
Não alterar os critérios de concorrência ou a compensação dos uploads ao mover
regras entre classes.

`ServicoSimulados` fica em `app/simulados/` e é somente de leitura (UC-21). O
repositório desse módulo depende apenas de `db`, para que as cascatas de UC-17 e
a exclusão de rascunho de UC-18 o importem sem ciclo com `app.avancos`. O avanço
atribuído a engenheiro simulado continua sendo um avanço comum com
`origem_simulada`: a leitura reaproveita a representação da prévia e a correção
pela construtora segue em `ServicoCorrecoes`, sem um fluxo paralelo. Não existe
serviço de escrita para comprador ou engenheiro; a carga é um procedimento em
`scripts/carregar_dados_demonstracao.py`.

## Decisões confirmadas para módulos ainda pendentes

- Ocorrência tem responsável opcional vinculado a `Trabalhador`, além de título,
  descrição, obra, marco opcional, autoria, data, estado e mídias opcionais.
- Ocorrência admite várias aceitações sem solução. Mudanças posteriores de estado
  não apagam aceitações ou transições anteriores.
- Reenvios de `POST /ocorrencias/{id}/aceitacoes` devem carregar a mesma chave
  `Idempotency-Key`; a repetição retorna a aceitação original (HTTP 200) sem
  duplicá-la. Uma nova decisão usa nova chave. Sem cabeçalho, cada POST é uma
  decisão nova. A aceitação é anexada atomicamente somente enquanto o estado é
  `sem solução`; a rota GET devolve o histórico mesmo após mudança de estado.
- Excluir um marco apaga suas ocorrências e os registros dependentes delas.
- Uma obra tem um cliente de referência, inclusive quando representa apartamentos.

Ocorrências, aceitações, correções de conteúdo publicado e exclusão completa de
obra/marco ainda não têm fluxos completos neste checkout. Esta refatoração não
os apresenta como funcionalidades disponíveis. Dados antigos de trabalhadores
sem `construtora_id` continuam legíveis pelo comportamento legado; a vinculação
histórica requer uma migração específica, sem inventar a empresa proprietária.

## Verificação

Executar `python -m pytest -q`. Os testes puros em `tests/dominio/` exercitam as
invariantes sem inicializar Flask, banco ou armazenamento. Os testes HTTP usam
banco isolado em memória. Transações locais simuladas não comprovam isolamento
real do Atlas. Testes com `--atlas` e Cloudinary continuam separados e exigem
configuração explícita.
