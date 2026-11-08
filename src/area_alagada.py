"""
=============================================================================
 area_alagada.py  —  Quanto da área emersa fica abaixo de cada nível do mar
=============================================================================

Calcula, direto sobre o DEM (mesmo heightmap usado na cena), a área de terra
emersa (elevação >= 0 m) que fica abaixo de cada cenário de nível do mar.
Gera os números da Tabela "Área emersa alagada" do artigo.

Cuidado ao interpretar: o DEM tem muitas células com elevação praticamente 0 m (< 1 mm)
(provavelmente corpos d'água e áreas costeiras planas do produto de origem).
Elas são alagadas assim que o nível passa de zero; por isso o script também
mostra a área descontando essas células.

Uso:  python src/area_alagada.py
"""

import numpy as np

import dem

RESOLUCAO = 1024
TAMANHO_MUNDO = 300.0
EXAGERO = 6.0  # o mesmo de dem.carregar_heightmap
NIVEIS_M = (0.5, 1.0, 2.0, 10.0)


def calcular_areas(elev_m: np.ndarray, area_celula_km2: float, niveis=NIVEIS_M) -> dict:
    """Área alagada por nível, a partir de um DEM em metros (função pura, testável).

    Devolve {"emersa": km², "zeros": km², nivel: (km², % da emersa, km² sem células a 0 m)}.
    Separar o cálculo do print permite testá-lo com matrizes pequenas, sem baixar tiles.
    """
    emersa = elev_m >= 0.0
    zeros = emersa & (elev_m < 1e-3)    # plateau em ~0 m (< 1 mm, absorve erro de arredondamento)
    total = emersa.sum()
    resultado = {"emersa": total * area_celula_km2, "zeros": zeros.sum() * area_celula_km2}
    for nivel in niveis:
        alagada = emersa & (elev_m < nivel)
        pct = 100.0 * alagada.sum() / total if total else 0.0
        resultado[nivel] = (
            alagada.sum() * area_celula_km2,
            pct,
            (alagada & ~zeros).sum() * area_celula_km2,
        )
    return resultado


def main() -> None:
    alturas, unidades_por_metro = dem.carregar_heightmap(
        resolution=RESOLUCAO, world_size=TAMANHO_MUNDO, exagero_vertical=EXAGERO
    )
    elev_m = alturas / unidades_por_metro            # volta de unidades de mundo p/ metros
    extensao_m = TAMANHO_MUNDO * EXAGERO / unidades_por_metro
    area_celula_km2 = (extensao_m / RESOLUCAO) ** 2 / 1e6

    r = calcular_areas(elev_m, area_celula_km2)
    print(f"célula: {extensao_m / RESOLUCAO:.1f} m | {area_celula_km2:.5f} km²")
    print(f"área emersa (elev >= 0 m): {r['emersa']:.0f} km²")
    print(f"células com elev ~ 0 m (< 1 mm): {r['zeros']:.1f} km²\n")
    print("nível   alagada(km²)  % da emersa  sem células a 0 m(km²)")
    for nivel in NIVEIS_M:
        km2, pct, sem_zeros = r[nivel]
        print(f"+{nivel:>4.1f} m  {km2:11.1f}  {pct:10.1f}%  {sem_zeros:20.1f}")


if __name__ == "__main__":
    main()
