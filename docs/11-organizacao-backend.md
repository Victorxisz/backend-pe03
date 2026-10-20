# 11. Organização proposta do backend

**Estado:** proposta para discussão; esta estrutura **ainda não foi criada**. `backend/` abaixo representa a raiz do repositório do servidor, não uma pasta adicional obrigatória. A ideia é manter **uma aplicação Flask** dividida pelos assuntos do projeto.

```text
backend/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── auth/
│   ├── obras/
│   ├── marcos/
│   ├── avancos/
│   ├── ocorrencias/
│   ├── trabalhadores/
│   ├── historico/
│   └── integracoes/
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── wsgi.py
```

| Pasta ou arquivo | Para que serve | Exemplo no projeto |
| --- | --- | --- |
| `app/` | Reúne o código da aplicação. | Todas as rotas e regras usadas pelo Flask. |
| `app/__init__.py` | Monta a aplicação e registra seus módulos. | Conectar as rotas de obras e marcos ao Flask. |
| `app/config.py` | Lê configurações do ambiente, sem guardar segredos no código. | Ler `MONGODB_URI` e a chave de sessão. |
| `app/database.py` | Centraliza a conexão com o MongoDB Atlas. | Disponibilizar a coleção de obras aos módulos. |
| `app/auth/` | Controla entrada, saída e proteção das requisições. | Recusar criação de obra sem a sessão da construtora. |
| `app/obras/` | Cuida dos dados e regras da obra. | Criar uma casa com data exata ou intervalo de entrega. |
| `app/marcos/` | Cuida dos marcos e suas dependências. | Registrar que “Alvenaria depende de Estrutura”. |
| `app/avancos/` | Cuida de rascunhos, mídias, publicação e correções. | Publicar uma foto da fundação sem apagar versões anteriores. |
| `app/ocorrencias/` | Cuida dos problemas registrados na obra. | Aceitar uma ocorrência sem solução com justificativa. |
| `app/trabalhadores/` | Cuida do cadastro e dos vínculos dos trabalhadores. | Associar um pedreiro à obra, sem lhe dar login no MVP. |
| `app/historico/` | Guarda e consulta mudanças relevantes feitas nos outros módulos. | Mostrar prazo anterior, prazo novo, motivo, autor e data. |
| `app/integracoes/` | Isola a comunicação com serviços externos. | Consultar um CEP ou enviar uma mídia ao provedor escolhido. |
| `tests/` | Reúne testes automatizados, preferencialmente por assunto. | Testar que um marco não pode depender de si mesmo. |
| `.env.example` | Lista nomes de configurações necessárias, com valores fictícios. | `MONGODB_URI=preencher_localmente`. |
| `.gitignore` | Impede o envio de arquivos locais e segredos ao Git. | Ignorar `.env` e `__pycache__/`. |
| `requirements.txt` | Lista bibliotecas Python necessárias. | Flask e driver do MongoDB. |
| `README.md` | Explica como instalar, configurar, testar e iniciar o servidor. | Passos para um colega rodar o backend. |
| `wsgi.py` | Oferece um ponto de entrada para iniciar a aplicação no servidor. | O processo no EC2 carrega a aplicação Flask por esse arquivo. |

## Dentro de cada pasta de assunto

Não é obrigatório criar todos estes arquivos antes de haver código para eles. Quando o módulo crescer, esta divisão ajuda:

| Arquivo | Responsabilidade | Exemplo em `obras/` |
| --- | --- | --- |
| `routes.py` | Recebe pedidos HTTP e devolve respostas. | Receber `POST /obras` e responder `201` quando criada. |
| `validacoes.py` | Confere o formato e a validade dos dados recebidos. | Rejeitar intervalo de entrega com fim anterior ao início. |
| `service.py` | Aplica as regras do projeto. | Alterar um prazo somente junto do registro do motivo. |
| `repository.py` | Lê e grava dados no MongoDB. | Salvar ou buscar uma obra pelo identificador. |

**Caminho de um pedido:** `routes.py → validacoes.py → service.py → repository.py → MongoDB`. Por exemplo: ao criar uma obra, a rota recebe o formulário; a validação confere as datas; o serviço decide como criar a obra; o repositório a salva; a rota devolve o resultado ao React.

## Relação com o código atual

O repositório já tem `api.py`, `db.py`, `trabalhadores.py` e `validacoes.py` na raiz. Eles são um início real do backend, não arquivos a apagar. Se o grupo adotar esta proposta, pode mover responsabilidades **gradualmente**, preservando as rotas existentes e ajustando os testes. A organização deve acompanhar os [casos de uso](08-casos-de-uso-mvp.md) e as [regras do domínio](02-dominio-e-regras.md), sem exigir uma classe Python para cada conceito do negócio.
