"""Consulta dos exemplos simulados de comprador e engenheiro (UC-21).

Somente leitura. Os exemplos entram pelo procedimento de demonstração
(``scripts/carregar_dados_demonstracao.py``), nunca por formulário do produto:
RN-10 não autoriza sessão de comprador ou de engenheiro. Cada exemplo carrega
alvo e origem suficientes para a interface apresentá-lo no contexto correto e
marcá-lo visivelmente como simulação.
"""

from bson import ObjectId
from bson.errors import InvalidId

from app.avancos.acesso_midias import midia_para_dict
from app.avancos.previa import representar_publicado
from app.serializacao import serializar

from .repository import ALVOS, TIPOS, RepositorioSimulados

AVISO = ("Exemplos simulados, pré-carregados para demonstração. Não são mensagens "
         "reais de comprador ou de engenheiro e não existe sessão desses perfis "
         "no MVP.")

SECOES = ("comprador", "engenheiro")
FILTROS = ("tipo", "alvo", "marco_id", "avanco_id", "secao")


class ErroSimulado(ValueError):
    def __init__(self, mensagem, status, campos=(), *, codigo="CONSULTA_INVALIDA"):
        super().__init__(mensagem)
        self.status = status
        self.campos = list(campos)
        self.codigo = codigo

    def corpo(self):
        return {"mensagem": str(self), "campos": self.campos, "codigo": self.codigo}


class ServicoSimulados:
    def __init__(self, repositorio=None):
        self.repositorio = repositorio if repositorio is not None else RepositorioSimulados()

    def consultar(self, obra_id, consulta=None):
        """Devolve os exemplos do comprador e os avanços de engenheiro da obra."""
        obra = self._obra(obra_id)
        contexto = self._contexto(obra)
        filtros = self._filtros(consulta or {}, contexto)
        secao = filtros.get("secao")

        comprador, inconsistentes = [], 0
        if secao in (None, "comprador"):
            comprador, inconsistentes = self._feedbacks(obra, contexto, filtros)
        engenheiro = []
        if secao in (None, "engenheiro"):
            engenheiro = self._avancos_simulados(contexto, filtros)

        aplicados = {campo: filtros[campo] for campo in ("tipo", "alvo", "secao")
                     if campo in filtros}
        aplicados.update({campo: str(filtros[campo])
                          for campo in ("marco_id", "avanco_id") if campo in filtros})
        corpo = {
            "obra": {"id": str(obra["_id"]), "nome": obra.get("nome"),
                     "cliente": obra.get("cliente")},
            "simulado": True,
            "somente_leitura": True,
            "aviso": AVISO,
            "filtros_aplicados": aplicados,
            "feedbacks": comprador,
            "avancos_simulados": engenheiro,
            "totais": {
                **{tipo: sum(1 for item in comprador if item["tipo"] == tipo)
                   for tipo in TIPOS},
                "feedbacks": len(comprador),
                "avancos_simulados": len(engenheiro),
            },
        }
        if inconsistentes:
            # Vínculo fora da obra não é apresentado nem contado como exemplo.
            corpo["exemplos_inconsistentes"] = inconsistentes
        return corpo

    def _obra(self, obra_id):
        obra = self.repositorio.buscar_obra(self._identificar(obra_id, "obra_id"))
        if obra is None:
            raise ErroSimulado("Obra não encontrada", 404, ["obra_id"],
                               codigo="OBRA_NAO_ENCONTRADA")
        return obra

    def _contexto(self, obra):
        """Índice dos objetos da obra; nenhum alvo de fora pode ser apresentado."""
        marcos = {documento["_id"]: documento
                  for documento in self.repositorio.listar_marcos(obra["_id"])}
        avancos = {documento["_id"]: documento
                   for documento in self.repositorio.listar_avancos(list(marcos))}
        return {"obra": obra, "marcos": marcos, "avancos": avancos}

    def _identificar(self, valor, campo):
        try:
            if not isinstance(valor, (str, ObjectId)):
                raise TypeError
            return ObjectId(valor)
        except (InvalidId, TypeError):
            raise ErroSimulado("Identificador inválido", 400, [campo],
                               codigo="ID_INVALIDO") from None

    def _filtros(self, consulta, contexto):
        desconhecidos = [campo for campo in consulta if campo not in FILTROS]
        if desconhecidos:
            raise ErroSimulado(
                "Filtro não reconhecido; use " + ", ".join(FILTROS), 422,
                sorted(desconhecidos), codigo="FILTRO_DESCONHECIDO")
        filtros = {}
        for campo, aceitos in (("tipo", TIPOS), ("alvo", ALVOS), ("secao", SECOES)):
            valor = (consulta.get(campo) or "").strip()
            if not valor:
                continue
            if valor not in aceitos:
                raise ErroSimulado(
                    "Valor inválido para " + campo + "; use " + ", ".join(aceitos),
                    422, [campo], codigo="FILTRO_INVALIDO")
            filtros[campo] = valor
        for campo, indice, nome in (("marco_id", "marcos", "Marco"),
                                    ("avanco_id", "avancos", "Atualização")):
            valor = (consulta.get(campo) or "").strip()
            if not valor:
                continue
            identificador = self._identificar(valor, campo)
            if identificador not in contexto[indice]:
                # Não existe ou pertence a outra obra: a resposta não mistura
                # contextos nem confirma a existência de um alvo de fora.
                raise ErroSimulado(nome + " não pertence à obra", 404, [campo],
                                   codigo="ALVO_FORA_DA_OBRA")
            filtros[campo] = identificador
        avanco = filtros.get("avanco_id")
        if avanco is not None and "marco_id" in filtros:
            if contexto["avancos"][avanco].get("marco_id") != filtros["marco_id"]:
                raise ErroSimulado("A atualização não pertence ao marco informado", 404,
                                   ["avanco_id", "marco_id"], codigo="ALVO_FORA_DO_MARCO")
        return filtros

    def _feedbacks(self, obra, contexto, filtros):
        consulta = {"obra_id": obra["_id"]}
        if "tipo" in filtros:
            consulta["tipo"] = filtros["tipo"]
        if "alvo" in filtros:
            consulta["alvo.tipo"] = filtros["alvo"]
        # O vínculo é exato: o exemplo do marco não aparece no painel da
        # atualização, nem o da atualização no painel do marco (CT-103). Com os
        # dois filtros, o alvo pedido é a atualização.
        if "avanco_id" in filtros:
            consulta["alvo.id"] = filtros["avanco_id"]
        elif "marco_id" in filtros:
            consulta["alvo.id"] = filtros["marco_id"]
        representados, inconsistentes = [], 0
        for documento in self.repositorio.listar_feedbacks(consulta):
            alvo = self._alvo(documento, contexto)
            if alvo is None:
                inconsistentes += 1
                continue
            representados.append(self._representar_feedback(documento, alvo))
        return representados, inconsistentes

    def _alvo(self, documento, contexto):
        """Confirma que o alvo do exemplo é um objeto desta obra."""
        alvo = documento.get("alvo")
        if not isinstance(alvo, dict):
            return None
        tipo, identificador = alvo.get("tipo"), alvo.get("id")
        if tipo == "obra":
            if identificador != contexto["obra"]["_id"]:
                return None
            return {"tipo": "obra", "id": identificador, "obra_id": identificador,
                    "marco_id": None, "avanco_id": None,
                    "rotulo": contexto["obra"].get("nome", "Obra")}
        if tipo == "marco":
            marco = contexto["marcos"].get(identificador)
            if marco is None:
                return None
            return {"tipo": "marco", "id": identificador,
                    "obra_id": contexto["obra"]["_id"], "marco_id": identificador,
                    "avanco_id": None, "rotulo": marco.get("nome", "Marco")}
        if tipo == "atualizacao":
            avanco = contexto["avancos"].get(identificador)
            if avanco is None:
                return None
            marco = contexto["marcos"].get(avanco.get("marco_id"))
            rotulo = "Atualização de " + str(avanco.get("data"))
            if marco is not None:
                rotulo += " — " + str(marco.get("nome"))
            return {"tipo": "atualizacao", "id": identificador,
                    "obra_id": contexto["obra"]["_id"],
                    "marco_id": avanco.get("marco_id"), "avanco_id": identificador,
                    "rotulo": rotulo}
        return None

    def _representar_feedback(self, documento, alvo):
        origem = dict(documento.get("origem") or {})
        origem.setdefault("simulado", True)
        origem.setdefault("perfil", "comprador")
        origem["autenticado"] = False
        return serializar({
            "id": documento["_id"],
            "simulado": True,
            "somente_leitura": True,
            "interacao_real": False,
            "tipo": documento.get("tipo"),
            "exemplo": documento.get("exemplo"),
            "origem": origem,
            "alvo": alvo,
            "conteudo": documento.get("conteudo"),
            "registrado_em": documento.get("registrado_em"),
        })

    def _avancos_simulados(self, contexto, filtros):
        """F-18: a mesma leitura da prévia, com a origem e a correção à vista."""
        representados = []
        for identificador, documento in sorted(contexto["avancos"].items(),
                                               key=lambda item: str(item[0])):
            if ("origem_simulada" not in documento
                    or documento.get("estado") == "exclusao_pendente"):
                continue
            if "marco_id" in filtros and documento.get("marco_id") != filtros["marco_id"]:
                continue
            if "avanco_id" in filtros and identificador != filtros["avanco_id"]:
                continue
            representados.append(self._representar_avanco(documento, contexto))
        return representados

    def _midias(self, avanco_id):
        representadas = []
        for midia in self.repositorio.consultar_midias(avanco_id):
            item = midia_para_dict(midia)
            item["conteudo"] = "/midias/" + item["id"] + "/conteudo"
            representadas.append(item)
        return representadas

    def _representar_avanco(self, documento, contexto):
        publicado = (documento.get("estado") == "publicado"
                     and isinstance(documento.get("publicacao"), dict)
                     and bool(documento["publicacao"]))
        if publicado:
            representacao = representar_publicado(documento)
        else:
            # Exemplo ainda sem publicação: as evidências vêm do acervo, na
            # mesma forma pública usada pelo snapshot, sem dado do provedor.
            marco = contexto["marcos"].get(documento.get("marco_id")) or {}
            representacao = {
                "id": str(documento["_id"]), "avanco_id": str(documento["_id"]),
                "estado": documento.get("estado"), "autor": documento.get("autor"),
                "data": documento.get("data"), "descricao": documento.get("descricao"),
                "marco": {"id": str(documento.get("marco_id")), "nome": marco.get("nome")},
                "midias": self._midias(documento["_id"]),
            }
        correcoes = documento.get("correcoes") or []
        representacao.update({
            "simulado": True,
            "somente_leitura": True,
            "origem_simulada": documento.get("origem_simulada"),
            # A autoria original permanece a do exemplo; a correção é da
            # construtora e não transforma o engenheiro em usuário real (RN-06).
            "autor_original": documento.get("autor"),
            "sessao_do_engenheiro": False,
            "versoes": 1 + len(correcoes),
            # Mesmo nome usado pelo histórico de UC-13 para o mesmo destino.
            "comparacao": "/avancos/" + str(documento["_id"]) + "/versoes",
            "editado_pela_construtora": bool(correcoes),
        })
        if correcoes:
            ultima = correcoes[-1]
            representacao["editado"] = True
            representacao["correcao"] = {
                "autor": ultima.get("autor"),
                "instante": ultima.get("instante"),
                "motivo": ultima.get("motivo"),
                "campos": ultima.get("campos"),
                "antes": ultima.get("antes"),
                "depois": ultima.get("depois"),
            }
        return serializar(representacao)


_servico = ServicoSimulados()

consultar_feedback_simulado = _servico.consultar
