"""Compatibilidade com a validação de dependências anterior à camada de domínio."""

from app.dominio.marcos import Dependencia, GrafoDependencias


def cria_ciclo(vinculos, marco_id, depende_de_id):
    return GrafoDependencias(vinculos).cria_ciclo(Dependencia(marco_id, depende_de_id))
