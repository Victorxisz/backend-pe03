"""Persistência atômica da ocorrência com evidências e aceitações."""

import db
from pymongo import ReturnDocument


class OcorrenciaNaoEncontrada(Exception):
    pass


class EstadoOcorrenciaIncompativel(Exception):
    pass


class ChaveReenvioIncompativel(Exception):
    pass


class RepositorioOcorrencias:
    def __init__(self, banco=None):
        self.banco = banco if banco is not None else db.banco_dados

    def buscar(self, ocorrencia_id):
        return self.banco["tbl_ocorrencias"].find_one({"_id": ocorrencia_id})

    def upload_em_andamento(self, ocorrencia_id, *, session=None):
        return self.banco["tbl_uploads_pendentes"].find_one(
            {"ocorrencia_id": ocorrencia_id, "estado": "pendente"}, session=session,
        ) is not None

    def buscar_obra(self, obra_id):
        return self.banco["tbl_obras"].find_one({"_id": obra_id})

    def buscar_marco(self, marco_id):
        return self.banco["tbl_marcos"].find_one({"_id": marco_id})

    def buscar_trabalhador(self, trabalhador_id):
        return self.banco["tbl_trabalhadores"].find_one({"_id": trabalhador_id})

    def listar(self, obra_id):
        return self.banco["tbl_ocorrencias"].find({"obra_id": obra_id}).sort(
            [("data_registro", -1), ("_id", 1)])

    def listar_do_conjunto(self, filtro, *, session=None):
        """Ocorrências removidas junto com a obra ou com o marco vinculado."""
        return list(self.banco["tbl_ocorrencias"].find(filtro, session=session).sort("_id", 1))

    def desvincular_marco(self, marco_id, *, session=None):
        """Alternativa de P-08: a ocorrência fica na obra, sem o marco excluído."""
        return self.banco["tbl_ocorrencias"].update_many(
            {"marco_id": marco_id}, {"$set": {"marco_id": None}}, session=session,
        ).modified_count

    def remover(self, ocorrencias, *, session=None):
        """Leva evidências e aceitações embutidas e os diários de upload."""
        ids = list(ocorrencias)
        if not ids:
            return
        self.banco["tbl_uploads_pendentes"].delete_many(
            {"ocorrencia_id": {"$in": ids}}, session=session)
        self.banco["tbl_ocorrencias"].delete_many({"_id": {"$in": ids}}, session=session)

    def inserir(self, documento):
        # Evidências e vínculos são embutidos: uma única escrita atômica,
        # inclusive em MongoDB standalone, sem ocorrência parcial.
        self.banco["tbl_ocorrencias"].insert_one(documento)

    def criar_operacao(self, documento):
        self.banco["tbl_uploads_pendentes"].insert_one(documento)

    def registrar_referencia(self, operacao_id, referencia):
        resultado = self.banco["tbl_uploads_pendentes"].update_one(
            {"_id": operacao_id, "estado": "pendente"}, {"$push": {"referencias": referencia}})
        if resultado.matched_count != 1:
            raise RuntimeError("Diário de upload indisponível")

    def remover_operacao_pendente(self, operacao_id):
        self.banco["tbl_uploads_pendentes"].delete_one({"_id": operacao_id, "estado": "pendente"})

    def concluir_operacao(self, operacao_id):
        self.banco["tbl_uploads_pendentes"].update_one(
            {"_id": operacao_id}, {"$set": {"estado": "concluida"}})

    def atualizar(self, anterior, campos, evento=None):
        filtro = {"_id": anterior["_id"], "estado": anterior["estado"],
                  "versao": anterior.get("versao", {"$exists": False})}
        atualizacao = {"$set": campos, "$inc": {"versao": 1}}
        if evento is not None:
            atualizacao["$push"] = {"historico_estados": evento}
            atualizacao["$inc"]["episodio"] = 1
        # Uma única escrita: estado, edição e append do evento são indivisíveis.
        return self.banco["tbl_ocorrencias"].find_one_and_update(
            filtro, atualizacao, return_document=ReturnDocument.AFTER)

    def _reenvio(self, documento, aceitacao, chave):
        if documento is None or chave is None:
            return None
        anterior = next((item for item in documento.get("aceitacoes", [])
                         if item.get("chave_reenvio") == chave), None)
        if anterior is not None and any(anterior.get(campo) != aceitacao.get(campo)
                                        for campo in ("justificativa", "medida_compensatoria", "autor")):
            raise ChaveReenvioIncompativel()
        return anterior

    def aceitar(self, ocorrencia_id, aceitacao, chave_reenvio=None, *, esperado=None):
        anterior = esperado if esperado is not None else self.buscar(ocorrencia_id)
        if anterior is None:
            raise OcorrenciaNaoEncontrada()
        repetida = self._reenvio(anterior, aceitacao, chave_reenvio)
        if repetida is not None:
            return {"aceitacoes": [repetida]}, True
        if anterior.get("estado") != "sem solução":
            raise EstadoOcorrenciaIncompativel()
        # A decisão pertence ao episódio lido, inclusive se o estado sair e
        # voltar a 'sem solução' durante uma requisição concorrente.
        aceitacao["episodio"] = anterior.get("episodio", 0)
        # Estado no filtro torna a validação e o append uma única operação atômica.
        filtro = {"_id": ocorrencia_id, "estado": "sem solução",
                  "episodio": anterior.get("episodio", {"$exists": False})}
        if chave_reenvio:
            filtro["aceitacoes.chave_reenvio"] = {"$ne": chave_reenvio}
            aceitacao["chave_reenvio"] = chave_reenvio
        salvo = self.banco["tbl_ocorrencias"].find_one_and_update(
            filtro,
            {"$push": {"aceitacoes": aceitacao}},
            return_document=ReturnDocument.AFTER,
        )
        if salvo is not None:
            return salvo, False
        existente = self.buscar(ocorrencia_id)
        repetida = self._reenvio(existente, aceitacao, chave_reenvio)
        if repetida is not None:
            return {"aceitacoes": [repetida]}, True
        if existente is None:
            raise OcorrenciaNaoEncontrada()
        raise EstadoOcorrenciaIncompativel()


_repositorio = RepositorioOcorrencias()
