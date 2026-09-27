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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot


@dataclass
class QuadNode:
    cx: float                       # centro do bloco no mundo (eixo X)
    cz: float                       # centro do bloco no mundo (eixo Z)
    size: float                     # comprimento do lado do bloco
    depth: int                      # 0 = raiz; aumenta a cada subdivisão
    children: list["QuadNode"] = field(default_factory=list)

    @property
    def offset(self) -> tuple[float, float]:
        """Canto (x, z) do bloco — é o que vai para u_node_offset no shader."""
        return (self.cx - self.size / 2.0, self.cz - self.size / 2.0)


def build_quadtree(world_size: float, max_depth: int) -> QuadNode:
    """Monta o quadtree completo uma única vez (na inicialização)."""
    root = QuadNode(0.0, 0.0, float(world_size), 0)
    _subdivide(root, max_depth)
    return root


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
) -> None:
    """Preenche 'out' com os blocos a desenhar neste frame.

    Regra: se o bloco tem filhos E a câmera está a menos de
    (size * split_factor) da borda dele, desce; senão, desenha este.
    split_factor menor  -> desce menos  -> menos triângulos, LOD mais agressivo.
    """
    tem_filhos = bool(node.children)
    perto = _dist_para_bloco(node, cam_x, cam_z) < node.size * split_factor
    if tem_filhos and perto:
        for child in node.children:
            select(child, cam_x, cam_z, split_factor, out)
    else:
        out.append(node)


# --- teste rápido:  python src/lod.py ----------------------------------
if __name__ == "__main__":
    tree = build_quadtree(world_size=300.0, max_depth=5)
    for (cx, cz) in ((0.0, 0.0), (150.0, 150.0), (600.0, 0.0)):
        sel: list[QuadNode] = []
        select(tree, cx, cz, split_factor=2.2, out=sel)
        profundidades = sorted({n.depth for n in sel})
        print(f"camera em ({cx:6.1f},{cz:6.1f}): {len(sel):3d} blocos, "
              f"profundidades {profundidades}")
