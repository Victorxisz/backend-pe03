"""Correção de publicações: validação, histórico e compensação de uploads."""
from copy import deepcopy

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from app.dominio.comum import Relogio
from app.integracoes.armazenamento import ErroArmazenamento
from app.publicacoes.validacoes import validar_midias
from . import repository
from .acesso_midias import midia_para_dict
from .midias import ServicoMidias, ResultadoPersistenciaIndeterminado
from .operacoes import OperacaoUpload
from .revisoes import ConflitoRascunho
from .service import ErroAvanco
from .validacoes import validar_correcao
from .versoes import consultar_versoes


class ServicoCorrecoes:
    def __init__(self, repositorio=None, relogio=None):
        self.repositorio = repositorio if repositorio is not None else repository
        self.relogio = relogio if relogio is not None else Relogio()

    def _verificar_acesso(self, servico, midias):
        try:
            for midia in midias:
                servico.armazenamento.obter_conteudo(midia['referencia_externa'], midia['tamanho'])
        except ErroArmazenamento as erro:
            status = 422 if erro.status in (404, 422) else 503
            raise ErroAvanco('Uma mídia da correção não está disponível', status, ['midias_manter']) from None

    def corrigir_publicacao(self, avanco_id, dados, autor, arquivos=(), *, servico_midias=None):
        arquivos = list(arquivos)
        try:
            if not isinstance(avanco_id, (str, ObjectId)):
                raise TypeError
            identificador = ObjectId(avanco_id)
        except (InvalidId, TypeError):
            raise ErroAvanco('Identificador inválido', 400, ['avanco_id']) from None
        erro = validar_correcao(dados, possui_novas_midias=bool(arquivos))
        if erro:
            raise ErroAvanco(erro[0], 422, erro[1])
        documento = self.repositorio.buscar_avanco(identificador)
        if documento is None:
            raise ErroAvanco('Avanço não encontrado', 404, ['avanco_id'])
        if documento.get('estado') != 'publicado' or not documento.get('publicacao'):
            raise ErroAvanco('Somente publicações podem ser corrigidas', 409, ['estado'])
        # A versão lida e o filtro de concorrência usam o mesmo documento.
        cadeia = consultar_versoes(avanco_id, documento=documento)['versoes']
        antes = deepcopy(cadeia[-1]['conteudo'])
        depois = deepcopy(antes)
        for campo in ('descricao', 'data'):
            if campo in dados:
                depois[campo] = dados[campo].strip()
        atuais = {str(m.get('id')): m for m in antes['midias']}
        ids = dados.get('midias_manter', list(atuais))
        disponiveis = {str(m['_id']): m for m in self.repositorio.consultar_midias(identificador)}
        if any(item not in disponiveis for item in ids):
            raise ErroAvanco('Uma mídia não está vinculada ao avanço', 422, ['midias_manter'])
        # A ordem enviada não cria uma versão artificial do mesmo conjunto.
        ordem = [item for item in atuais if item in ids] + [item for item in ids if item not in atuais]
        selecionadas = [disponiveis[item] for item in ordem]
        if not selecionadas and not arquivos:
            raise ErroAvanco('Mantenha ao menos uma mídia válida', 422, ['midias_manter'])
        depois['midias'] = []
        for item in ordem:
            publica = deepcopy(atuais[item]) if item in atuais else midia_para_dict(disponiveis[item])
            if item not in atuais:
                publica['conteudo'] = f'/midias/{item}/conteudo'
            depois['midias'].append(publica)
        if depois == antes and not arquivos:
            raise ErroAvanco('A correção precisa modificar a publicação', 422, ['corpo'])
        if selecionadas and not validar_midias(selecionadas):
            raise ErroAvanco('Uma mídia selecionada é inválida', 422, ['midias_manter'])
        try:
            servico = servico_midias if servico_midias is not None else ServicoMidias()
        except (ErroArmazenamento, ValueError):
            raise ErroAvanco('Armazenamento indisponível', 503, ['midias']) from None
        self._verificar_acesso(servico, selecionadas)
        instante = self.relogio.agora()
        operacao = OperacaoUpload(self.repositorio, identificador, 'correcao') if arquivos else None

        def salvar(enviadas):
            novas = [{**item, '_id': ObjectId(), 'avanco_id': identificador,
                      'data_envio': instante} for item in enviadas]
            if not validar_midias(selecionadas + novas):
                raise ErroAvanco('Mantenha ao menos uma mídia válida', 422, ['midias'])
            self._verificar_acesso(servico, novas)
            for midia in novas:
                publica = midia_para_dict(midia)
                publica['conteudo'] = f"/midias/{publica['id']}/conteudo"
                depois['midias'].append(publica)
            campos = [campo for campo in ('data', 'descricao', 'midias') if antes[campo] != depois[campo]]
            if not campos:
                raise ErroAvanco('A correção precisa modificar a publicação', 422, ['corpo'])
            correcao = {'antes': antes, 'depois': depois, 'campos': campos,
                        'motivo': dados['motivo'].strip(), 'autor': autor, 'instante': instante}
            try:
                self.repositorio.salvar_correcao_publicada(
                    documento, correcao, depois, novas, operacao.id if operacao else None, selecionadas,
                )
            except PyMongoError as erro:
                if erro.has_error_label('UnknownTransactionCommitResult'):
                    raise ResultadoPersistenciaIndeterminado([m['referencia_externa'] for m in novas]) from None
                raise

        try:
            if operacao:
                operacao.executar(servico, arquivos, salvar)
            else:
                salvar([])
        except ConflitoRascunho:
            raise ErroAvanco('A publicação ou suas mídias foram alteradas; consulte novamente', 409, ['avanco_id']) from None
        return consultar_versoes(avanco_id)


_servico = ServicoCorrecoes()
corrigir_publicacao = _servico.corrigir_publicacao
