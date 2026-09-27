"""
=============================================================================
 water.py  —  Plano de água (a geometria; as ondas ficam no shader)
=============================================================================

Ideia
-----
A água é só uma GRADE PLANA de triângulos, gerada uma vez. O movimento das
ondas NÃO é feito aqui na CPU: quem desloca cada vértice, a cada frame, é o
vertex shader (shaders/water.vert), usando as **ondas de Gerstner**.

Por que Gerstner (e não um seno simples)?
-----------------------------------------
Num seno vertical puro a água só "sobe e desce". Nas ondas de Gerstner cada
partícula descreve um círculo: além de subir, ela também é empurrada na
horizontal, na direção de propagação. Isso deixa a crista mais afiada e o
vale mais largo — o visual clássico de mar. É a formulação de
Fournier & Reeves (1986), "A Simple Model of Ocean Waves", que já tratava
justamente da zona costeira.

Quanto mais fina a grade (resolution), mais suave o deslocamento — mas mais
triângulos. ~200 x 200 costuma ser um bom equilíbrio.
"""

from __future__ import annotations

import numpy as np

from heightmap import grid_indices   # reaproveita a triangulação da grade


def build_water_plane(resolution: int = 200, world_size: float = 450.0):
    """Gera (vertices, indices) de um plano horizontal em y = 0, centrado na origem.

    vertices : float32, forma (resolution*resolution, 3) -> [x, 0, z]
    indices  : uint32,  triângulos da grade

    O plano costuma ser MAIOR que o terreno (world_size maior) para que a
    água alcance o horizonte e não "acabe" dentro do campo de visão.
    """
    lin = np.linspace(-world_size / 2.0, world_size / 2.0, resolution, dtype=np.float32)
    xs, zs = np.meshgrid(lin, lin)
    ys = np.zeros_like(xs)

    vertices = np.stack([xs, ys, zs], axis=-1).astype(np.float32).reshape(-1, 3)
    indices = grid_indices(resolution)
    return vertices, indices


# --- teste rápido:  python src/water.py ----------------------------------
if __name__ == "__main__":
    v, idx = build_water_plane(resolution=64)
    print(f"vertices : {v.shape}  (esperado: {64 * 64} x 3)")
    print(f"indices  : {idx.shape}  (triângulos: {idx.size // 3})")
