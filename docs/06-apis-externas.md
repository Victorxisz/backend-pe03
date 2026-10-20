# 6. APIs externas: opções e decisão

**Decisão atual (20/10/2026):** nenhuma API externa foi aprovada pelo grupo ou professor. Ela deve ser totalmente gratuita para o uso previsto no MVP, aparecer numa ação real da demonstração e ter tratamento para indisponibilidade. Gratuita não significa ilimitada; conferir limites e termos antes de ativar.

## Comparação orientada pelo problema

| Opção | Como melhora o produto | Trabalho adicional | Pontos a validar |
| --- | --- | --- | --- |
| [Cloudinary — Upload API](https://cloudinary.com/documentation/image_upload_api_reference) | Armazena e entrega fotos, vídeos e documentos; resolve uma necessidade central. | Conta, credenciais no Flask, upload, metadados no Atlas e controle de acesso. | O plano Free é US$ 0 sem cartão e 25 créditos mensais, mas tem limites de tamanho/uso; confirmar privacidade, documentos e aceite do professor. |
| [Amazon S3 — API de objetos](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) | Alternativa de armazenamento de mídia. | Bucket, IAM, URLs assinadas, permissões e custos. | Não adotar como solução “totalmente gratuita” sem prova de que todo o uso fica sem cobrança; há risco de custo. |
| [ViaCEP — consulta de CEP](https://viacep.com.br/) | Preenche parte do endereço ao cadastrar obra e reduz erros de digitação. | Baixo: campo CEP, consulta, preenchimento e edição manual. | Serviço se apresenta como gratuito, mas avisa que uso massivo pode ser bloqueado; não usá-lo para validação em lote. |
| [BrasilAPI — CEP v2](https://brasilapi.com.br/docs) | Também ajuda no cadastro de endereço; pode fornecer geolocalização para funções futuras. | Baixo a médio: tratar formatos e campos ausentes. | Cobertura, estabilidade e se geolocalização é necessária agora. |
| [Open-Meteo — previsão/histórico](https://open-meteo.com/en/docs) | Dá contexto climático a impedimentos. | Médio: coordenadas, consulta e interpretação. | [Plano gratuito apenas para uso não comercial](https://open-meteo.com/en/pricing); pode contrariar a intenção de produto rentável. Não recomendado agora. |

## Recomendação para o prazo

1. **Escolha de menor risco de custo para a exigência externa: ViaCEP.** Ele declara gratuidade, não exige chave e encaixa no cadastro da obra. Tratar falha sem impedir preenchimento manual. Confirmar com o professor se atende à rubrica.
2. **Escolha possível para mídia: Cloudinary Free**, se os [limites atuais](https://cloudinary.com/documentation/billing_and_plans) servirem ao piloto. O plano é gratuito dentro da cota, não ilimitado. Monitorar créditos e impedir uploads que excedam limites; validar acesso privado e aceitação acadêmica. Pode ser usado junto ao ViaCEP, se cada integração tiver função clara.
3. **Deixar clima para depois da entrega**: o plano gratuito do Open-Meteo é não comercial, e previsão não deve marcar ocorrência nem alterar prazo automaticamente.

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
