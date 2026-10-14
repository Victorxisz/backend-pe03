# 6. APIs externas: opções e decisão

**Decisão atual:** nenhuma API externa foi aprovada pelo grupo ou professor. O requisito da disciplina permanece aberto. A integração escolhida deve aparecer numa ação real da demonstração e ter tratamento para indisponibilidade; uma chamada decorativa apenas para cumprir a rubrica acrescenta pouco ao produto.

## Comparação orientada pelo problema

| Opção | Como melhora o produto | Trabalho adicional | Pontos a validar |
| --- | --- | --- | --- |
| [Cloudinary — Upload API](https://cloudinary.com/documentation/image_upload_api_reference) | Armazena e entrega as fotos, vídeos e documentos associados a avanços; resolve uma necessidade obrigatória do MVP. | Configurar conta, credenciais no Flask, upload, metadados no Atlas e acesso restrito às mídias. | Limites/condições do plano, formatos, tamanho de vídeo, privacidade e aceitação pelo professor. |
| [Amazon S3 — API de objetos](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) | Alternativa de armazenamento para todos os tipos de mídia; URLs temporárias podem controlar uploads e downloads. | Configurar bucket, IAM, URLs assinadas, permissões e custos. | Se o professor considera S3 uma “API externa” distinta da infraestrutura AWS exigida. |
| [ViaCEP — consulta de CEP](https://viacep.com.br/) | Preenche parte do endereço ao cadastrar obra e reduz erros de digitação. | Baixo: campo CEP, consulta, preenchimento e edição manual de complemento/número. | Endereços sem CEP conhecido; a integração é útil, mas periférica à dor principal. |
| [BrasilAPI — CEP v2](https://brasilapi.com.br/docs) | Também ajuda no cadastro de endereço; pode fornecer geolocalização para funções futuras. | Baixo a médio: tratar formatos e campos ausentes. | Cobertura, estabilidade e se geolocalização é necessária agora. |
| [Open-Meteo — previsão/histórico](https://open-meteo.com/en/docs) | Dá contexto climático a um possível impedimento ou planejamento. | Médio: coordenadas da obra, consulta por data e distinção entre previsão e observação. | Licença aplicável, relevância para o MVP e risco de tratar previsão como justificativa automática de atraso. |

## Recomendação para o prazo

1. **Priorizar a API de mídia** se o professor confirmar que ela satisfaz o requisito: mídia é parte essencial do fluxo `avanço → atualização`. Cloudinary tende a demandar menos infraestrutura própria; S3 combina com o EC2, mas traz configuração de acesso e uma possível dúvida acadêmica sobre o que conta como API externa.
2. **Considerar ViaCEP como segunda integração pequena**, caso o cadastro da obra inclua CEP. Ele melhora a experiência de cadastro, mas não substitui uma solução para armazenar vídeos e documentos.
3. **Deixar clima para depois da entrega**, a menos que entrevistas mostrem que explicar interrupções por chuva é uma dor prioritária. A previsão não deve marcar uma ocorrência nem alterar prazo automaticamente.

Usar duas APIs só quando cada uma cumprir uma função clara. Cada provedor externo acrescenta credenciais, falhas possíveis e testes à entrega.

## Como manter a escolha reversível

- O domínio guarda `tipo`, `nome`, `tamanho`, `referenciaExterna` e `visibilidade` da mídia, sem depender de nomes específicos do provedor.
- O Flask expõe ao React recursos próprios de mídia; o navegador não recebe segredos do provedor.
- Criar uma interface simples de armazenamento no servidor, com operações `enviar`, `obterAcesso` e `remover`. Implementar **um** provedor na primeira versão; não construir um catálogo de plugins.
- Quando o provedor falhar, o avanço não deve parecer salvo com mídia que não existe. Informar o erro e permitir nova tentativa.
- Verificar o custo, termos e limites atuais do provedor selecionado antes de ativá-lo. Não presumir que todos os tipos de arquivo tenham o mesmo limite ou o mesmo modo de acesso.

## Pergunta objetiva para o professor

> “Nosso MVP usa React + Flask + MongoDB Atlas em EC2. Se integrarmos a API da Cloudinary para armazenar e recuperar fotos, vídeos e documentos de avanços da obra, isso atende ao requisito de usar pelo menos uma API externa? Se não, uma consulta de CEP pelo ViaCEP/BrasilAPI atenderia?”

Registrar a resposta e a data em [decisões](07-plano-e-decisoes.md) antes de fixar o provedor.
