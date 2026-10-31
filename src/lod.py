"""
=============================================================================
 lod.py  —  Quadtree do terreno + seleção de nível de detalhe (CDLOD, parte 2a)
=============================================================================

Ideia do CDLOD (Strugar, 2010)
------------------------------
O terreno é dividido recursivamente em 4 quadrantes, formando um QUADTREE:

        +---------+          +----+----+
        |         |          |    |    |
        |  raiz   |   ->     +----+----+   ->  ... até a profundidade máxima
        |         |          |    |    |
        +---------+          +----+----+

- A RAIZ cobre o terreno inteiro (bloco grande, pouco detalhe).
- Cada nível abaixo divide o bloco em 4, dobrando o detalhe.

A cada frame, percorremos a árvore de cima para baixo:
  - se a câmera está PERTO do bloco  -> desce para os 4 filhos (mais detalhe);
  - se está LONGE                     -> para aqui e desenha este bloco.

Resultado: muitos blocos pequenos perto da câmera, poucos blocos grandes
ao longe. Todos desenhados com a MESMA malha unitária (heightmap.build_unit_grid),
só mudando o canto e o tamanho — ver terrain.vert.

Parte 2a x 2b
-------------
Aqui (2a) os blocos de tamanhos diferentes se encostam sem tratamento, o que
deixa FRESTAS ("cracks") nas bordas: o bloco grande tem menos vértices naquela
aresta e não acompanha a curva do terreno que o bloco pequeno segue.
A parte 2b resolve isso com "morphing" de vértices.

Frustum culling (parte 2c)
--------------------------
Até aqui a seleção só olhava a DISTÂNCIA: blocos atrás da câmera eram
desenhados à toa. O frustum culling descarta os blocos que estão fora do campo
de visão. Cada bloco vira uma CAIXA (AABB): o lado em XZ vem da própria
quadtree e a faixa vertical [y_min, y_max] vem do heightmap. Se a caixa inteira
está do lado de fora de algum dos 6 planos do frustum, nenhum pixel do bloco
pode aparecer — então ele (e todos os filhos, que cabem dentro dele) é podado.

Por que NUMPY e não um laço Python? Testar os 1365 nós um a um em Python custa
~9 ms por quadro, e o quadro inteiro hoje leva ~1,1 ms. Em numpy o teste de
TODOS os nós de uma vez custa ~0,1 ms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

import numpy as np


@dataclass
class QuadNode:
    cx: float                       # centro do bloco no mundo (eixo X)
    cz: float                       # centro do bloco no mundo (eixo Z)
    size: float                     # comprimento do lado do bloco
    depth: int                      # 0 = raiz; aumenta a cada subdivisão
    children: list["QuadNode"] = field(default_factory=list)
    indice: int = -1                # posição do nó no vetor "plano" (índice da máscara de visibilidade)
    y_min: float = 0.0              # menor altura do terreno dentro do bloco (base da caixa do culling)
    y_max: float = 0.0              # maior altura do terreno dentro do bloco

    @property
    def offset(self) -> tuple[float, float]:
        """Canto (x, z) do bloco — é o que vai para u_node_offset no shader."""
        return (self.cx - self.size / 2.0, self.cz - self.size / 2.0)


def build_quadtree(world_size: float, max_depth: int) -> QuadNode:
    """Monta o quadtree completo uma única vez (na inicialização)."""
    root = QuadNode(0.0, 0.0, float(world_size), 0)
    _subdivide(root, max_depth)
    _numerar(root, [0])
    return root


def _numerar(node: QuadNode, contador: list[int]) -> None:
    """Dá a cada nó um índice único, em pré-ordem (pai antes dos filhos).

    É esse índice que liga o nó à sua posição nos vetores numpy do culling.
    """
    node.indice = contador[0]
    contador[0] += 1
    for child in node.children:
        _numerar(child, contador)


def listar_nos(raiz: QuadNode) -> list[QuadNode]:
    """Todos os nós, na ordem do índice (nos[i].indice == i)."""
    nos: list[QuadNode] = []

    def visitar(no: QuadNode) -> None:
        nos.append(no)
        for filho in no.children:
            visitar(filho)

    visitar(raiz)
    return nos


def _subdivide(node: QuadNode, max_depth: int) -> None:
    if node.depth >= max_depth:
        return
    q = node.size / 4.0            # deslocamento do centro de cada filho
    half = node.size / 2.0         # tamanho de cada filho
    for dx, dz in ((-q, -q), (q, -q), (-q, q), (q, q)):
        child = QuadNode(node.cx + dx, node.cz + dz, half, node.depth + 1)
        node.children.append(child)
        _subdivide(child, max_depth)


def _dist_para_bloco(node: QuadNode, cam_x: float, cam_z: float) -> float:
    """Menor distância (no plano XZ) da câmera até o quadrado do bloco.

    0 se a câmera está sobre o bloco. Usar a borda (e não o centro) evita
    que blocos grandes próximos deixem de subdividir só porque o centro
    deles está longe.
    """
    half = node.size / 2.0
    dx = max(abs(cam_x - node.cx) - half, 0.0)
    dz = max(abs(cam_z - node.cz) - half, 0.0)
    return hypot(dx, dz)


def select(
    node: QuadNode,
    cam_x: float,
    cam_z: float,
    split_factor: float,
    out: list[QuadNode],
    visiveis: np.ndarray | None = None,
) -> int:
    """Preenche 'out' com os blocos a desenhar neste frame.

    Regra: se o bloco tem filhos E a câmera está a menos de
    (size * split_factor) da borda dele, desce; senão, desenha este.
    split_factor menor  -> desce menos  -> menos triângulos, LOD mais agressivo.

    `visiveis` (opcional) é a máscara do frustum culling (ver `nos_visiveis`):
    um nó marcado como invisível é PODADO — não desenha nem desce. Isso vale
    para a subárvore inteira, porque a caixa dos filhos cabe dentro da do pai.

    Devolve quantos nós foram podados (0 sem culling).
    """
    if visiveis is not None and not visiveis[node.indice]:
        return 1
    tem_filhos = bool(node.children)
    perto = _dist_para_bloco(node, cam_x, cam_z) < node.size * split_factor
    if tem_filhos and perto:
        podados = 0
        for child in node.children:
            podados += select(child, cam_x, cam_z, split_factor, out, visiveis)
        return podados
    out.append(node)
    return 0


# --- frustum culling ------------------------------------------------------
def atribuir_faixas_altura(
    raiz: QuadNode, alturas: np.ndarray, world_size: float, margem_texels: int = 2
) -> None:
    """Preenche y_min/y_max de cada nó a partir do heightmap (matriz N x N).

    Folhas: mínimo e máximo da região do heightmap sob o bloco. Nós internos:
    mínimo/máximo dos filhos (por isso o pai sempre contém a faixa dos filhos).

    MARGEM: a GPU amostra a textura com filtro linear, ou seja, interpola
    entre texels vizinhos. Um vértice na borda do bloco "puxa" a altura de
    texels que estão FORA dele. Sem uma margem de alguns texels a caixa ficaria
    um pouco baixa/alta demais e o culling poderia descartar um bloco visível.
    """
    n = alturas.shape[0]

    def texel(coordenada_mundo: float) -> float:
        # mundo [-S/2, S/2] -> uv [0, 1] -> índice de texel (centro do texel = inteiro)
        return (coordenada_mundo / world_size + 0.5) * n - 0.5

    def preencher(no: QuadNode) -> None:
        if no.children:
            for filho in no.children:
                preencher(filho)
            no.y_min = min(f.y_min for f in no.children)
            no.y_max = max(f.y_max for f in no.children)
            return
        meio = no.size / 2.0
        i0 = max(int(np.floor(texel(no.cx - meio))) - margem_texels, 0)
        i1 = min(int(np.floor(texel(no.cx + meio))) + 1 + margem_texels + 1, n)
        j0 = max(int(np.floor(texel(no.cz - meio))) - margem_texels, 0)
        j1 = min(int(np.floor(texel(no.cz + meio))) + 1 + margem_texels + 1, n)
        regiao = alturas[j0:j1, i0:i1]
        no.y_min = float(regiao.min())
        no.y_max = float(regiao.max())

    preencher(raiz)


@dataclass
class CaixasNos:
    """As caixas (AABB) de todos os nós, em vetores numpy indexados por `indice`."""
    cx: np.ndarray
    cz: np.ndarray
    meio: np.ndarray        # metade do lado do bloco
    y_min: np.ndarray
    y_max: np.ndarray


def caixas_dos_nos(raiz: QuadNode) -> CaixasNos:
    """Monta os vetores numpy UMA vez (na inicialização); o frame só os consulta."""
    nos = listar_nos(raiz)
    return CaixasNos(
        cx=np.array([n.cx for n in nos], dtype=np.float64),
        cz=np.array([n.cz for n in nos], dtype=np.float64),
        meio=np.array([n.size / 2.0 for n in nos], dtype=np.float64),
        y_min=np.array([n.y_min for n in nos], dtype=np.float64),
        y_max=np.array([n.y_max for n in nos], dtype=np.float64),
    )


def planos_do_frustum(view, proj) -> np.ndarray:
    """Os 6 planos do frustum (esq, dir, baixo, cima, near, far), forma (6, 4).

    Método de Gribb-Hartmann: cada plano é uma soma/diferença de linhas da
    matriz projeção*view. Um ponto p está do lado de DENTRO de um plano quando
    n·p + d >= 0. Os planos não são normalizados — para o teste de caixa só o
    sinal importa.
    """
    # np.array(mat4) do PyGLM já vem como [linha][coluna]: m[i] é a linha i.
    m = np.array(proj * view, dtype=np.float64)
    r0, r1, r2, r3 = m[0], m[1], m[2], m[3]
    return np.stack([r3 + r0, r3 - r0, r3 + r1, r3 - r1, r3 + r2, r3 - r2])


def nos_visiveis(caixas: CaixasNos, planos: np.ndarray) -> np.ndarray:
    """Máscara (um bool por nó): False = a caixa está TODA fora de algum plano.

    Para cada plano olhamos o canto da caixa mais "para dentro" dele (o vértice
    positivo): se até esse canto está do lado de fora, a caixa toda está.
    O teste é CONSERVADOR — uma caixa que só encosta no frustum fica como
    visível; o pior que acontece é desenhar um bloco a mais, nunca um a menos.
    """
    a, b, c, d = planos[:, 0:1], planos[:, 1:2], planos[:, 2:3], planos[:, 3:4]
    px = np.where(a > 0, caixas.cx + caixas.meio, caixas.cx - caixas.meio)
    py = np.where(b > 0, caixas.y_max, caixas.y_min)
    pz = np.where(c > 0, caixas.cz + caixas.meio, caixas.cz - caixas.meio)
    fora = (a * px + b * py + c * pz + d) < 0.0
    return ~fora.any(axis=0)


# --- teste rápido:  python src/lod.py ----------------------------------
if __name__ == "__main__":
    tree = build_quadtree(world_size=300.0, max_depth=5)
    for (cx, cz) in ((0.0, 0.0), (150.0, 150.0), (600.0, 0.0)):
        sel: list[QuadNode] = []
        select(tree, cx, cz, split_factor=2.2, out=sel)
        profundidades = sorted({n.depth for n in sel})
        print(f"camera em ({cx:6.1f},{cz:6.1f}): {len(sel):3d} blocos, "
              f"profundidades {profundidades}")
