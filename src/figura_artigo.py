"""
=============================================================================
 figura_artigo.py  —  Figura "custo x carga" do artigo, com 3 execuções
=============================================================================

Desenha o tempo de quadro (média e p95) em função dos triângulos da malha
completa, usando a MÉDIA das execuções de bench/v3 e barras de ± 1 desvio
entre execuções. Inclui a curva do CDLOD com culling e marca os pontos de
virada. Só LÊ os CSVs; escreve apenas a imagem de saída.

Uso:  python src/figura_artigo.py docs/artigo_final/custo_vs_carga_v5.png
"""

import statistics as est
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 8})

from resumo_bench import media_por_execucao, ponto_de_virada, triangulos_sem_lod

PASTAS = [Path("bench/v3") / f"run{i}" for i in (1, 2, 3)]
CURVAS = [  # (condicao, rótulo, cor, marcador)
    ("sem_lod", "Malha completa", "#b5413b", "o"),
    ("cdlod", "CDLOD", "#2b6a9e", "s"),
    ("cdlod_frustum", "CDLOD + culling", "#3a8a5c", "^"),
]


def main(saida: Path) -> None:
    tris = triangulos_sem_lod(PASTAS[0])
    resolucoes = sorted(tris)
    x = [tris[r] / 1e6 for r in resolucoes]

    fig, eixos = plt.subplots(1, 2, figsize=(6.4, 2.0), sharey=True)
    for ax, coluna, titulo in zip(eixos, ("ms_media", "ms_p95"), ("Média", "Percentil 95")):
        por_exec = [media_por_execucao(p, coluna) for p in PASTAS]
        for cond, rotulo, cor, marca in CURVAS:
            y = [est.mean(e[(r, cond)] for e in por_exec) for r in resolucoes]
            dp = [est.stdev(e[(r, cond)] for e in por_exec) for r in resolucoes]
            ax.errorbar(x, y, yerr=dp, label=rotulo, color=cor, marker=marca, ms=4, lw=1.4, capsize=2)
        medias = {k: est.mean(e[k] for e in por_exec) for k in por_exec[0]}
        for cond, _, cor, _ in CURVAS[1:]:
            v = ponto_de_virada(medias, tris, cond)
            if v:
                ax.axvline(v / 1e6, color=cor, ls=":", lw=1)
                ax.text(v / 1e6 + 0.1, 0.05, f"{v / 1e6:.1f} M", color=cor, fontsize=6)
        ax.set_title(titulo, fontsize=8)
        ax.set_xlabel("Triângulos da malha completa (milhões)", fontsize=8)
        ax.grid(alpha=0.25)
    eixos[0].set_ylabel("Tempo de quadro (ms)")
    eixos[0].legend(fontsize=6.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(saida, dpi=200)
    print("figura salva em", saida)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
