"""
=============================================================================
 resumo_bench.py  —  Tabela média ± desvio e ponto de virada, direto dos CSVs
=============================================================================

Os números do artigo devem vir dos CSVs, e não de cópia manual. Este script lê
várias execuções do benchmark (uma pasta com resultados.csv cada) e imprime:

  1. tempo de quadro (média e p95) por resolução e técnica: média ± desvio
     ENTRE execuções (cada execução já é a média das 4 câmeras);
  2. o ponto de virada de cada execução: número de triângulos da malha completa
     em que o CDLOD passa a ser mais rápido, por interpolação linear entre as
     duas resoluções vizinhas ao cruzamento.

Só usa a biblioteca padrão. Não escreve nada em disco (não toca nos dados).

Uso:  python src/resumo_bench.py bench/v2/run1 bench/v2/run2 bench/v2/run3
"""

import csv
import statistics as est
import sys
from collections import defaultdict
from pathlib import Path


def media_por_execucao(pasta: Path, coluna: str) -> dict:
    """{(resolucao, condicao): média da coluna sobre as câmeras} de UMA execução."""
    acumulado = defaultdict(list)
    with open(pasta / "resultados.csv", newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            acumulado[(int(linha["resolucao"]), linha["condicao"])].append(float(linha[coluna]))
    return {k: est.mean(v) for k, v in acumulado.items()}


def triangulos_sem_lod(pasta: Path) -> dict:
    """{resolucao: triângulos da malha completa}."""
    return {k[0]: v for k, v in media_por_execucao(pasta, "triangulos").items() if k[1] == "sem_lod"}


def ponto_de_virada(tempos: dict, tris: dict, tecnica: str):
    """Triângulos (da malha completa) onde `tecnica` cruza a malha completa; None se não cruza."""
    res = sorted(tris)
    # diferença > 0 quando a malha completa é MAIS LENTA que a técnica
    d = [tempos[(r, "sem_lod")] - tempos[(r, tecnica)] for r in res]
    for i in range(len(res) - 1):
        if d[i] < 0 <= d[i + 1]:
            t0, t1 = tris[res[i]], tris[res[i + 1]]
            return t0 + (t1 - t0) * (-d[i]) / (d[i + 1] - d[i])
    return None


def mais_menos(valores: list) -> str:
    desvio = est.stdev(valores) if len(valores) > 1 else 0.0
    return f"{est.mean(valores):.2f} ± {desvio:.2f}"


def main(pastas: list) -> None:
    for coluna in ("ms_media", "ms_p95"):
        por_exec = [media_por_execucao(p, coluna) for p in pastas]
        chaves = sorted(set().union(*por_exec))
        print(f"\n{coluna} (ms), média ± desvio entre {len(pastas)} execuções")
        print(f"{'res':>5}  {'condicao':<17} tempo")
        for chave in chaves:
            valores = [e[chave] for e in por_exec if chave in e]
            print(f"{chave[0]:>5}  {chave[1]:<17} {mais_menos(valores)}")

        for tecnica in ("cdlod", "cdlod_frustum"):
            viradas = [
                ponto_de_virada(e, triangulos_sem_lod(p), tecnica)
                for e, p in zip(por_exec, pastas)
                if (256, tecnica) in e
            ]
            texto = ", ".join("sem cruzamento" if v is None else f"{v / 1e6:.2f} M" for v in viradas)
            print(f"ponto de virada ({tecnica}), por execução: {texto}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main([Path(a) for a in sys.argv[1:]])
