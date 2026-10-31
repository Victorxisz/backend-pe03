"""Edição transacional e retenção das referências usadas por outras publicações."""

from copy import deepcopy

from bson import ObjectId
import db

from .revisoes import ConflitoRascunho, registrar_alteracao


class RepositorioRascunhos:
    def __init__(self, banco=None, cliente=None):
        self.banco = banco if banco is not None else db.banco_dados
        self.cliente = cliente if cliente is not None else db.cliente_mongo

    def inserir_com_midias(self, documento, midias):
        if not midias:
            raise ValueError("O avanço precisa de pelo menos uma mídia")
        novo = {**deepcopy(documento), "_id": ObjectId()}
        evidencias = [{**deepcopy(midia), "_id": ObjectId(), "avanco_id": novo["_id"],
                       "data_envio": novo["data_registro"]} for midia in midias]

        def gravar(sessao):
            self.banco["tbl_avancos"].insert_one(deepcopy(novo), session=sessao)
            self.banco["tbl_midias"].insert_many(deepcopy(evidencias), session=sessao)
            return novo["_id"]

        with self.cliente.start_session() as sessao:
            return sessao.with_transaction(gravar)

    def _contem(self, valor, *, ids=(), referencia=None):
        from .midias import ErroMidia, chave_arquivo

        if isinstance(valor, dict):
            if referencia is not None:
                try:
                    if chave_arquivo(valor) == referencia:
                        return True
                except ErroMidia:
                    pass
            return any(self._contem(item, ids=ids, referencia=referencia) for item in valor.values())
        if isinstance(valor, list):
            return any(self._contem(item, ids=ids, referencia=referencia) for item in valor)
        return isinstance(valor, (str, ObjectId)) and str(valor) in ids

    def _referenciada_por_id(self, midia_id, sessao):
        for nome in self.banco.list_collection_names():
            if nome in {"tbl_midias", "tbl_limpezas_midias"}:
                continue
            for documento in self.banco[nome].find({}, session=sessao):
                if self._contem(documento, ids={str(midia_id)}):
                    return True
        return False

    def salvar_edicao(self, documento, alteracoes, midias_anteriores, ids_manter, novas_midias, operacao_id=None):
        if set(alteracoes) - {"data", "descricao"}:
            raise ValueError("A edição não pode alterar campos protegidos")
        ids_anteriores = {midia["_id"] for midia in midias_anteriores}
        ids_manter = set(ids_manter)
        if (not ids_manter.issubset(ids_anteriores)
                or not ids_manter and not novas_midias
                or any(midia.get("avanco_id") != documento["_id"] for midia in midias_anteriores)):
            raise ValueError("Conjunto de mídias inconsistente")
        removidas = [midia for midia in midias_anteriores if midia["_id"] not in ids_manter]
        mantidas = [midia for midia in midias_anteriores if midia["_id"] in ids_manter]

        def gravar(sessao):
            registrar_alteracao(documento, sessao, colecao=self.banco["tbl_avancos"])
            atuais = list(self.banco["tbl_midias"].find({"avanco_id": documento["_id"]}, session=sessao))
            if sorted(atuais, key=lambda m: str(m["_id"])) != sorted(midias_anteriores, key=lambda m: str(m["_id"])):
                raise ConflitoRascunho("As mídias do rascunho foram alteradas")
            for midia in removidas:
                if self._referenciada_por_id(midia["_id"], sessao):
                    raise ConflitoRascunho("A mídia é referenciada por uma publicação ou histórico")
                self.banco["tbl_limpezas_midias"].update_one(
                    {"_id": midia["_id"]}, {"$setOnInsert": {
                        "avanco_id": documento["_id"], "midia": deepcopy(midia),
                    }},
                    upsert=True, session=sessao,
                )
            for midia in mantidas:
                filtro = {k: v for k, v in midia.items() if k != "_versao_edicao"}
                resultado = self.banco["tbl_midias"].update_one(
                    filtro, {"$inc": {"_versao_edicao": 1}}, session=sessao,
                )
                if resultado.matched_count != 1:
                    raise ConflitoRascunho("Uma mídia foi alterada")
            if removidas:
                resultado = self.banco["tbl_midias"].delete_many(
                    {"avanco_id": documento["_id"], "_id": {"$in": [midia["_id"] for midia in removidas]}}, session=sessao,
                )
                if resultado.deleted_count != len(removidas):
                    raise ConflitoRascunho("Uma mídia foi alterada durante a edição")
            if novas_midias:
                novas = [{**deepcopy(midia), "_id": ObjectId(), "avanco_id": documento["_id"]}
                         for midia in novas_midias]
                self.banco["tbl_midias"].insert_many(novas, session=sessao)
            if alteracoes:
                self.banco["tbl_avancos"].update_one(
                    {"_id": documento["_id"]}, {"$set": alteracoes}, session=sessao,
                )
            if operacao_id is not None:
                resultado = self.banco["tbl_uploads_pendentes"].update_one(
                    {"_id": operacao_id, "estado": "pendente"},
                    {"$set": {"estado": "concluida"}}, session=sessao,
                )
                if resultado.matched_count != 1:
                    raise ConflitoRascunho("Operação de upload indisponível")
            return self.banco["tbl_avancos"].find_one({"_id": documento["_id"]}, session=sessao), removidas

        confirmado = False
        try:
            with self.cliente.start_session() as sessao:
                resultado = sessao.with_transaction(gravar)
                confirmado = True
                return resultado
        except Exception:
            if not confirmado:
                raise
            # Um erro ao encerrar a sessão não desfaz um commit confirmado.
            return resultado

    def referencia_em_uso(self, referencia, ids_midias=(), operacao_ignorada=None):
        campos = ("provedor", "public_id", "resource_type", "delivery_type")
        if not isinstance(referencia, dict) or any(
            not isinstance(referencia.get(campo), str) or not referencia[campo] for campo in campos
        ):
            return True  # Referência inválida exige revisão; não autoriza exclusão.
        identidade = tuple(referencia[campo] for campo in campos)
        ids = {str(identificador) for identificador in ids_midias}
        for nome in self.banco.list_collection_names():
            if nome == "tbl_limpezas_midias":
                continue
            for documento in self.banco[nome].find():
                if nome == "tbl_uploads_pendentes" and documento["_id"] == operacao_ignorada:
                    continue
                if nome == "tbl_uploads_pendentes" and documento.get("estado") in {"concluida", "limpa"}:
                    continue
                if self._contem(documento, ids=ids, referencia=identidade):
                    return True
        return False

    def concluir_limpeza(self, midia_id):
        self.banco["tbl_limpezas_midias"].delete_one({"_id": midia_id})
