"""
=============================================================================
 verificar_fendas.py  —  O geomorphing realmente fecha as fendas (cracks)?
=============================================================================

Renderiza o terreno (a água fica abaixo dele, em -100) em câmeras aleatórias
e conta as FENDAS FINAS: faixas verticais de 1 a 3 pixels de céu entre
terreno acima e abaixo, que a malha completa (sem LOD) não tem.

Por que "finas": o LOD simplifica a forma do terreno, então a silhueta difere
da malha completa em manchas maiores. Contar todo pixel diferente misturaria
essa diferença legítima com as fendas de verdade (que são estreitas).

Limite: só detecta fendas verticais; não mede o popping.

Uso:
    python src/verificar_fendas.py            # 40 câmeras
    python src/verificar_fendas.py 100        # 100 câmeras
"""

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))
sys.path.insert(0, str(RAIZ / "src"))

from _base import ALTURA, CEU, LARGURA, camera_aleatoria, criar_contexto_gl, matriz_view, projecao  # noqa: E402
from scene import Cena  # noqa: E402

CEU_RGB = np.array([round(c * 255) for c in CEU], dtype=np.int16)


def _eh_ceu(img):
    return np.abs(img - CEU_RGB).max(axis=2) <= 2


def contar_fendas_finas(img, ref):
    """Conta faixas de 1 a 3 px de céu (ausentes em `ref`) entre terreno acima e abaixo."""
    ceu_img, ceu_ref = _eh_ceu(img), _eh_ceu(ref)
    terreno = ~ceu_img
    total = 0
    for k in (1, 2, 3):                       # largura da fresta em pixels
        n = terreno.shape[0] - (k + 1)
        padrao = terreno[:n] & terreno[k + 1:k + 1 + n]   # terreno acima e abaixo
        for j in range(1, k + 1):                         # k pixels de céu no meio
            padrao &= ceu_img[j:j + n] & ~ceu_ref[j:j + n]
        total += int(padrao.sum())
    return total


def main(n_cameras=40):
    ctx = criar_contexto_gl()
    cena = Cena(ctx, verboso=False)
    fbo = ctx.simple_framebuffer((LARGURA, ALTURA))
    proj = projecao()

    def quadro(pos, alvo, **opcoes):
        fbo.use()
        fbo.clear(*CEU)
        cena.desenhar(matriz_view(pos, alvo), proj, tuple(pos), nivel_mar=-100.0, tempo=0.0, **opcoes)
        bruto = np.frombuffer(fbo.read(), dtype=np.uint8)
        return bruto.reshape(ALTURA, LARGURA, 3).astype(np.int16)

    rng = np.random.default_rng(7)
    com, sem = 0, 0
    for _ in range(n_cameras):
        pos, alvo = camera_aleatoria(rng)
        ref = quadro(pos, alvo, lod_ligado=False)
        com += contar_fendas_finas(quadro(pos, alvo, lod_ligado=True, morph=True), ref)
        sem += contar_fendas_finas(quadro(pos, alvo, lod_ligado=True, morph=False), ref)

    print(f"{n_cameras} câmeras aleatórias, {LARGURA}x{ALTURA}")
    print("Fendas finas (1 a 3 px de céu entre terreno, ausentes na malha completa):")
    print(f"  CDLOD com morphing : {com}")
    print(f"  CDLOD sem morphing : {sem}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
