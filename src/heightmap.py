"""
=============================================================================
 heightmap.py  —  Geração do campo de altura e construção da malha de terreno
=============================================================================

O que é um HEIGHTMAP?
---------------------
É uma grade 2D de valores de altura: heights[linha][coluna] = y.
Pense numa imagem em tons de cinza onde branco = ponto alto, preto = ponto
baixo. Aqui a grade é gerada proceduralmente com RUÍDO SIMPLEX
(opensimplex), somando várias "oitavas" (Fractal Brownian Motion) para
obter relevo com formas grandes + detalhes pequenos.

Mais adiante no projeto, esta mesma grade poderá vir de um dado real
(SRTM / DEM de uma região costeira) sem alterar o resto do pipeline.

Da grade à MALHA (mesh)
-----------------------
A GPU só desenha triângulos. Convertemos a grade N x N em:
  - array de VÉRTICES: para cada ponto (i, j) guardamos
    [x, y, z, nx, ny, nz]  (posição no mundo + normal para iluminação);
  - array de ÍNDICES: cada célula do grid vira 2 triângulos que
    referenciam os vértices pelo número (Element Buffer). Índices evitam
    repetir vértices compartilhados entre triângulos vizinhos.

As NORMAIS são estimadas pelo gradiente do campo de altura (quão inclinado
está o terreno em x e em z naquele ponto).
"""

from __future__ import annotations

import numpy as np
import opensimplex


def generate_heightmap(
    resolution: int = 256,
    height_scale: float = 18.0,
    seed: int = 42,
    octaves: int = 5,
    base_frequency: float = 2.0,
    persistence: float = 0.5,
) -> np.ndarray:
    """Gera uma grade (resolution x resolution) de alturas em float32.

    Parâmetros
    ----------
    resolution     : nº de pontos por lado da grade (mais = mais detalhe e mais custo).
    height_scale   : amplitude vertical máxima aproximada (em unidades de mundo).
    seed           : semente do ruído — mesma seed => mesmo terreno.
    octaves        : quantas camadas de ruído somar (formas grandes -> detalhes finos).
    base_frequency : frequência da 1ª oitava (quanto o terreno "ondula").
    persistence    : quanto cada oitava seguinte perde de amplitude (0.5 = metade).
    """
    opensimplex.seed(seed)   # fixa o gerador global do módulo

    # Coordenadas normalizadas [-0.5, 0.5] em cada eixo do ruído.
    lin = np.linspace(-0.5, 0.5, resolution, dtype=np.float64)

    heights = np.zeros((resolution, resolution), dtype=np.float64)
    frequency = base_frequency
    amplitude = 1.0
    amplitude_total = 0.0

    for _ in range(octaves):
        # noise2array(x, y) -> matriz de forma (len(y), len(x)) com valores em [-1, 1].
        layer = opensimplex.noise2array(lin * frequency, lin * frequency)
        heights += amplitude * layer
        amplitude_total += amplitude
        frequency *= 2.0            # cada oitava dobra a frequência...
        amplitude *= persistence    # ...e reduz a amplitude.

    # Normaliza para ~[-1, 1] e aplica a escala vertical desejada.
    heights /= amplitude_total
    heights *= height_scale

    return heights.astype(np.float32)


def build_mesh(heights: np.ndarray, world_size: float = 200.0):
    """Converte a grade de alturas em (vertices, indices) prontos para a GPU.

    Retorna
    -------
    vertices : np.ndarray float32, forma (N*N, 6) -> [x, y, z, nx, ny, nz]
    indices  : np.ndarray uint32,  forma (n_triangulos * 3,)

    O terreno fica centrado na origem: x e z variam de -world_size/2 a +world_size/2.
    Convenção de eixos: X = leste/oeste, Y = altura (para cima), Z = norte/sul.
    """
    res = heights.shape[0]

    # --- posições (x, z) da grade, centradas na origem --------------------
    lin = np.linspace(-world_size / 2.0, world_size / 2.0, res, dtype=np.float32)
    # xs[i, j] = lin[j] (varia na coluna);  zs[i, j] = lin[i] (varia na linha).
    xs, zs = np.meshgrid(lin, lin)
    ys = heights  # y[i, j] é a altura naquele ponto

    # --- normais via gradiente do campo de altura -----------------------
    spacing = world_size / (res - 1)          # distância entre pontos vizinhos
    # np.gradient devolve [derivada ao longo das linhas (z), ao longo das colunas (x)].
    dz_dz, dz_dx = np.gradient(ys, spacing)
    nx = -dz_dx
    ny = np.ones_like(ys)
    nz = -dz_dz
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len

    # --- empacota tudo em (N*N, 6) --------------------------------------
    vertices = np.stack([xs, ys, zs, nx, ny, nz], axis=-1).astype(np.float32)
    vertices = vertices.reshape(-1, 6)

    indices = grid_indices(res)
    return vertices, indices


def build_unit_grid(subdivisions: int):
    """Grade quadrada em [0, 1] x [0, 1] com (subdivisions+1)^2 vértices.

    É a malha reaproveitável do CDLOD: o vertex shader recebe o canto e o
    tamanho de cada bloco do quadtree e "estica" esta grade unitária para a
    posição certa no mundo, amostrando a altura da textura de heightmap.

    Retorna
    -------
    vertices : float32, forma ((n)^2, 2) -> [x, z] em [0, 1]
    indices  : uint32, triângulos da grade
    """
    n = subdivisions + 1
    lin = np.linspace(0.0, 1.0, n, dtype=np.float32)
    xs, zs = np.meshgrid(lin, lin)
    vertices = np.stack([xs, zs], axis=-1).astype(np.float32).reshape(-1, 2)
    return vertices, grid_indices(n)


def grid_indices(resolution: int) -> np.ndarray:
    """Índices (uint32) que ligam os vértices de uma grade N x N em triângulos.

    Cada célula do grid vira 2 triângulos. Serve tanto para o terreno quanto
    para o plano de água (ver water.py), que compartilham o mesmo formato de grade.
    O índice do vértice na posição (i, j) da grade é  i * resolution + j.
    """
    i = np.arange(resolution - 1)
    j = np.arange(resolution - 1)
    jj, ii = np.meshgrid(j, i)                 # ii = linha, jj = coluna

    top_left     = (ii * resolution + jj).ravel()
    top_right    = top_left + 1
    bottom_left  = top_left + resolution
    bottom_right = bottom_left + 1

    # triângulo 1 (TL, BL, TR) + triângulo 2 (TR, BL, BR)
    tri1 = np.stack([top_left, bottom_left, top_right], axis=-1)
    tri2 = np.stack([top_right, bottom_left, bottom_right], axis=-1)
    return np.concatenate([tri1, tri2], axis=1).ravel().astype(np.uint32)


# --- teste rápido sem OpenGL:  python -m src.heightmap  --------------------
if __name__ == "__main__":
    h = generate_heightmap(resolution=64)
    v, idx = build_mesh(h)
    print(f"heightmap : {h.shape}, min={h.min():.2f}, max={h.max():.2f}")
    print(f"vertices  : {v.shape}  (esperado: {64 * 64} x 6)")
    print(f"indices   : {idx.shape}  (triângulos: {idx.size // 3})")
