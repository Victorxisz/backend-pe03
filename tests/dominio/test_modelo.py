"""Invariantes exercitadas sem Flask, banco ou provedor de arquivos."""

from datetime import date, datetime, timezone
import pytest

from app.dominio.comum import ErroDominio
from app.dominio.obras import Obra, PrazoEntrega
from app.dominio.marcos import Dependencia, DependenciasPendentes, GrafoDependencias, Marco
from app.dominio.avancos import Avanco
from app.dominio.pessoas import Trabalhador


@pytest.mark.parametrize("modalidade", ["data_exata", "intervalo_estimado"])
@pytest.mark.parametrize("dia,esperado", [(19, []), (20, []), (21, ["atrasada"])])
def test_alerta_unico_respeita_limite_inclusivo(modalidade, dia, esperado):
    dados = {"modalidade": modalidade}
    dados.update({"data": "2030-10-20"} if modalidade == "data_exata"
                 else {"inicio": "2030-10-01", "fim": "2030-10-20"})
    obra = Obra("obra", PrazoEntrega.de_dados(dados))
    assert obra.alertas(date(2030, 10, dia)) == esperado


@pytest.mark.parametrize("dados", [
    None, {}, {"modalidade": "data_exata", "data": "2030-02-30"},
    {"modalidade": "data_exata", "data": "2030-10-20", "fim": "2030-10-22"},
    {"modalidade": "intervalo_estimado", "inicio": "2030-10-20", "fim": "2030-10-19"},
])
def test_prazo_invalido_nao_constroi_objeto(dados):
    with pytest.raises(ErroDominio):
        PrazoEntrega.de_dados(dados)


def test_conclusao_automatica_reabertura_e_eventos_independentes():
    obra = Obra("obra", PrazoEntrega.de_dados({"modalidade": "data_exata", "data": "2030-10-20"}))
    instante = datetime(2030, 10, 18, 12, tzinfo=timezone.utc)
    conclusao = obra.alterar_estado("concluída", "Finalizada", "conta", instante)
    assert obra.data_conclusao == date(2030, 10, 18)
    assert obra.alertas(date(2030, 10, 30)) == []
    assert obra.alterar_estado("concluída", "Repetição", "conta", instante) is None
    reabertura = obra.alterar_estado("em andamento", "Retrabalho", "conta", instante)
    assert obra.data_conclusao is None
    assert obra.alertas(date(2030, 10, 30)) == ["atrasada"]
    assert conclusao.para_documento()["valor_novo"]["data_conclusao"] == "2030-10-18"
    assert reabertura.para_documento()["valor_anterior"]["data_conclusao"] == "2030-10-18"


def test_marco_avisa_dependencias_e_permite_confirmacao():
    marco = Marco("marco", "obra")
    instante = datetime(2030, 10, 20, tzinfo=timezone.utc)
    with pytest.raises(DependenciasPendentes):
        marco.alterar_estado("concluído", "Decisão", "conta", instante, pendentes=["estrutura"])
    assert marco.estado == "a iniciar"
    mudanca = marco.alterar_estado("concluído", "Decisão", "conta", instante,
                                  pendentes=["estrutura"], confirmar=True)
    assert mudanca.anterior == "a iniciar" and marco.estado == "concluído"


def test_grafo_detecta_ciclos_indiretos_e_autorreferencia():
    grafo = GrafoDependencias([{"marco_id": "A", "depende_de_id": "B"},
                              {"marco_id": "B", "depende_de_id": "C"}])
    assert grafo.cria_ciclo(Dependencia("C", "A"))
    assert grafo.cria_ciclo(Dependencia("A", "A"))
    assert not grafo.cria_ciclo(Dependencia("A", "D"))


def test_avanco_publicado_nao_pode_voltar_a_edicao_simples():
    avanco = Avanco("avanco", "rascunho")
    with pytest.raises(ErroDominio):
        avanco.validar_midias_finais(0)
    avanco.validar_midias_finais(1)
    avanco.publicar()
    with pytest.raises(ErroDominio):
        avanco.exigir_rascunho()


def test_trabalhador_mantem_construtora_sem_vinculos_e_nao_duplica_obra():
    trabalhador = Trabalhador("Nome", "a@example.com", "11999999999", "pedreiro", "conta",
                              datetime(2030, 10, 20, tzinfo=timezone.utc))
    assert trabalhador.para_documento()["construtora_id"] == "conta"
    trabalhador.vincular_obra("obra")
    trabalhador.vincular_obra("obra")
    assert trabalhador.obras == ["obra"]
