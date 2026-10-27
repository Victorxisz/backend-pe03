def cria_ciclo (vinculos, marco_id, depende_de_id):
    if marco_id == depende_de_id:
        return True

    grafo = {}

    for vinculo in vinculos:
        origem = vinculo["marco_id"]
        destino = vinculo["depende_de_id"]
        grafo.setdefault(origem, set()).add(destino)

    pendentes = [depende_de_id]
    visitados = set()

    while pendentes:
        atual = pendentes.pop()

        if atual == marco_id:
            return True

        if atual in visitados:
            continue

        visitados.add(atual)
        pendentes.extend(grafo.get(atual, ()))

    return False