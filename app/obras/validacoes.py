from datetime import date
def validar_criacao_obra(dados):
      if not isinstance(dados, dict):
            return {
                  "mensagem": "Envie um objeto JSON válido.",
                  "campos": ["corpo"]
            }
      
      campos_obrigatorios = (
      "nome",
      "cliente",
      "localizacao",
      "descricao"
        )

      for campo in campos_obrigatorios:
            valor = dados.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                  return {
                        "mensagem": f"O campo '{campo}' deve ser um texto não vazio.",
                        "campos": [campo]
                  }
      tipo = dados.get("tipo")
      if tipo not in ("casa", "apartamentos"):
            return {"mensagem": "O tipo deve ser 'casa' ou 'apartamentos'.",
                    "campos": ["tipo"]
                    }

      inicio = dados.get("inicio")
      if not isinstance(inicio, str):
            return {
                  "mensagem": "Informe a data de início no formato AAAA-MM-DD.",
                  "campos": ["inicio"]
            }
      if len(inicio) != 10 or inicio[4] != "-" or inicio[7] != "-":
            return {
                  "mensagem": "Use o formato AAAA-MM-DD na data de início.",
                  "campos": ["inicio"]
            }

      numeros = inicio[:4] + inicio[5:7] + inicio[8:10]

      for caractere in numeros:
            if caractere not in "0123456789":
                  return {
                        "mensagem": "A data de início deve conter apenas números e hífens.",
                        "campos": ["inicio"]
                  }
      ano = int(inicio[:4])
      mes = int(inicio[5:7])
      dia = int(inicio[8:10])

      if ano < 1 or mes < 1 or mes > 12:
            return {
                  "mensagem": "Informe um ano e um mês válidos.",
                  "campos": ["inicio"]
            }
      limite_dias = 31

      if mes in (4, 6, 9, 11):
            limite_dias = 30
      elif mes == 2:
            limite_dias = 28

            if ano % 400 == 0 or (ano % 4 == 0 and ano % 100 != 0):
                  limite_dias = 29
      if dia < 1 or dia > limite_dias:
            return {
                  "mensagem": "O dia informado não existe nesse mês.",
                  "campos": ["inicio"]
            }
      
      entrega = dados.get("entrega")

      if not isinstance(entrega, dict):
            return {
                  "mensagem": "Informe os dados de entrega como um objeto JSON.",
                  "campos": ["entrega"]
            }
      modalidade = entrega.get("modalidade")

      if modalidade not in ("data_exata", "intervalo_estimado"):
            return {
                  "mensagem": "Informe 'data_exata' ou 'intervalo_estimado'.",
                  "campos": ["entrega.modalidade"]
            }

      if modalidade == "data_exata":
            campos_permitidos = ("modalidade", "data")
            campos_datas = ("data",)
      else:
            campos_permitidos = ("modalidade", "inicio", "fim")
            campos_datas = ("inicio", "fim")

      # Impede misturar data exata e intervalo.
      for campo in entrega:
            if campo not in campos_permitidos:
                  return {
                        "mensagem": "Informe somente os campos da modalidade escolhida.",
                        "campos": ["entrega"]
                  }

      # Verifica cada data exigida pela modalidade.
      for campo in campos_datas:
            valor = entrega.get(campo)
            nome_campo = f"entrega.{campo}"

            if not isinstance(valor, str):
                  return {
                        "mensagem": "Informe a data como texto no formato AAAA-MM-DD.",
                        "campos": [nome_campo]
                  }

            if len(valor) != 10 or valor[4] != "-" or valor[7] != "-":
                  return {
                        "mensagem": "Use o formato AAAA-MM-DD.",
                        "campos": [nome_campo]
                  }

            numeros = valor[:4] + valor[5:7] + valor[8:10]

            for caractere in numeros:
                  if caractere not in "0123456789":
                        return {
                              "mensagem": "A data deve conter apenas números e hífens.",
                              "campos": [nome_campo]
                        }

            ano = int(valor[:4])
            mes = int(valor[5:7])
            dia = int(valor[8:10])

            if ano < 1 or mes < 1 or mes > 12:
                  return {
                        "mensagem": "Informe um ano e um mês válidos.",
                        "campos": [nome_campo]
                  }

            limite_dias = 31

            if mes in (4, 6, 9, 11):
                  limite_dias = 30
            elif mes == 2:
                  limite_dias = 28

                  if ano % 400 == 0 or (ano % 4 == 0 and ano % 100 != 0):
                        limite_dias = 29

            if dia < 1 or dia > limite_dias:
                  return {
                        "mensagem": "O dia informado não existe nesse mês.",
                        "campos": [nome_campo]
                  }

      # Fora do for: compara as datas depois de validar ambas.
      if modalidade == "intervalo_estimado":
            if entrega["fim"] < entrega["inicio"]:
                  return {
                        "mensagem": "O fim do intervalo não pode ser anterior ao início.",
                        "campos": ["entrega.fim"]
                  }

      return None