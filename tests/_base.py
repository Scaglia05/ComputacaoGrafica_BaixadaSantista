"""
=============================================================================
 _base.py  —  Utilidades compartilhadas pelos testes
=============================================================================

Os testes usam só a biblioteca padrão (`unittest`): o projeto não tem pytest e
não vale instalar uma dependência só para isso. Para rodar tudo:

    python -m unittest discover -s tests -v

Testes que precisam de GPU criam um contexto OpenGL SEM janela (o mesmo que o
bench.py usa). Se a máquina não tiver GPU/driver, esses testes são PULADOS, e
não reprovados — o resto da suíte continua valendo.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import glm
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

TAMANHO_MUNDO = 300.0
LARGURA, ALTURA = 1280, 720
CEU = (0.62, 0.72, 0.84)


def criar_contexto_gl():
    """Contexto OpenGL headless, configurado como no bench.py."""
    try:
        import moderngl
        ctx = moderngl.create_standalone_context()
    except Exception as erro:  # sem driver / sem GPU
        raise unittest.SkipTest(f"sem contexto OpenGL headless: {erro}")
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    return ctx


def projecao() -> glm.mat4:
    """Mesma projeção do app e do bench.py (constantes de camera.py: FOV 60°, near 0,1, far 2000)."""
    from camera import FOV_GRAUS, PLANO_LONGE, PLANO_PERTO
    return glm.perspective(glm.radians(FOV_GRAUS), LARGURA / ALTURA, PLANO_PERTO, PLANO_LONGE)


def matriz_view(pos, alvo) -> glm.mat4:
    return glm.lookAt(pos, alvo, glm.vec3(0.0, 1.0, 0.0))


def camera_aleatoria(rng: np.random.Generator):
    """(posição, alvo) sorteados dentro e ao redor do terreno.

    O pitch é limitado (-60° a +25°) para o olhar nunca ficar paralelo ao
    vetor "para cima" — nesse caso o lookAt degenera.
    """
    meio = TAMANHO_MUNDO / 2.0
    pos = glm.vec3(
        rng.uniform(-1.3 * meio, 1.3 * meio),
        rng.uniform(2.0, 90.0),
        rng.uniform(-1.3 * meio, 1.3 * meio),
    )
    yaw = rng.uniform(0.0, 2.0 * math.pi)
    pitch = math.radians(rng.uniform(-60.0, 25.0))
    direcao = glm.vec3(
        math.cos(yaw) * math.cos(pitch),
        math.sin(pitch),
        math.sin(yaw) * math.cos(pitch),
    )
    return pos, pos + direcao * 10.0
