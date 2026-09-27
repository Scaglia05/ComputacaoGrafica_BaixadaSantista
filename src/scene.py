"""
=============================================================================
 scene.py  —  A cena (terreno + água) e como desenhá-la
=============================================================================

Isola toda a parte de GPU — textura de altura, buffers, shaders, seleção de
LOD e os draw calls — numa classe reutilizável, a `Cena`.

Assim:
  - main.py  cuida só de janela + input + laço;
  - bench.py consegue medir EXATAMENTE o mesmo caminho de render, sem janela.

`Cena.desenhar(...)` devolve `EstatisticasFrame` (blocos, draw calls, triângulos),
que o benchmark usa para relacionar custo x carga.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import glm
import moderngl

import dem
import heightmap
import lod
import water

SHADER_DIR = Path(__file__).parent / "shaders"
DIRECAO_LUZ = tuple(glm.normalize(glm.vec3(-0.5, -1.0, -0.3)))


def _programa(ctx: moderngl.Context, nome: str) -> moderngl.Program:
    return ctx.program(
        vertex_shader=(SHADER_DIR / f"{nome}.vert").read_text(encoding="utf-8"),
        fragment_shader=(SHADER_DIR / f"{nome}.frag").read_text(encoding="utf-8"),
    )


@dataclass
class EstatisticasFrame:
    blocos: int          # quantos blocos do quadtree foram desenhados
    draw_calls: int      # blocos + 1 (a água)
    triangulos: int      # total de triângulos enviados neste frame


class Cena:
    def __init__(
        self,
        ctx: moderngl.Context,
        *,
        fonte: str = "dem",
        resolucao_heightmap: int = 1024,
        resolucao_agua: int = 256,
        tamanho_mundo: float = 300.0,
        escala_altura: float = 28.0,
        seed: int = 42,
        lod_profundidade: int = 5,
        lod_subdivisoes: int = 32,
        lod_fator_split: float = 2.2,
        construir_ingenuo: bool = True,
        verboso: bool = True,
    ):
        self.ctx = ctx
        self.tamanho_mundo = tamanho_mundo
        self.resolucao_heightmap = resolucao_heightmap
        self.lod_subdivisoes = lod_subdivisoes
        self.lod_fator_split = lod_fator_split

        # --- heightmap -> textura R32F --------------------------------
        if fonte == "dem":
            if verboso:
                print("Carregando DEM da Baixada Santista (baixa tiles na 1a vez)...")
            alturas, self.unidades_por_metro = dem.carregar_heightmap(
                resolution=resolucao_heightmap, world_size=tamanho_mundo
            )
        else:
            if verboso:
                print("Gerando terreno procedural...")
            alturas = heightmap.generate_heightmap(
                resolution=resolucao_heightmap, height_scale=escala_altura, seed=seed
            )
            # Sem escala geográfica real: amplitude ~ 600 m só para os
            # cenários de nível do mar (em metros) fazerem sentido.
            self.unidades_por_metro = escala_altura / 600.0

        self.altura_ref = max(abs(float(alturas.min())), abs(float(alturas.max()))) or 1.0

        self._tex = ctx.texture(
            (resolucao_heightmap, resolucao_heightmap), 1, alturas.tobytes(), dtype="f4"
        )
        self._tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._tex.repeat_x = False
        self._tex.repeat_y = False
        self._tex.use(location=0)

        # --- programa do terreno + grades ---------------------------
        self.prog = _programa(ctx, "terrain")
        self.prog["u_heightmap"].value = 0
        self.prog["u_world_size"].value = (tamanho_mundo, tamanho_mundo)
        self.prog["u_height_scale"].value = self.altura_ref
        self.prog["u_light_dir"].value = DIRECAO_LUZ

        self._vao_bloco = self._grade(lod_subdivisoes)
        self._vao_ingenuo = self._grade(resolucao_heightmap) if construir_ingenuo else None

        self._quadtree = lod.build_quadtree(tamanho_mundo, lod_profundidade)
        self._bloco_raiz = lod.QuadNode(0.0, 0.0, tamanho_mundo, 0)

        self.triangulos_por_bloco = lod_subdivisoes * lod_subdivisoes * 2
        self.triangulos_ingenuo = resolucao_heightmap * resolucao_heightmap * 2

        # --- água ---------------------------------------------------
        av, ai = water.build_water_plane(
            resolution=resolucao_agua, world_size=tamanho_mundo * 1.6
        )
        self.prog_agua = _programa(ctx, "water")
        self.prog_agua["u_light_dir"].value = DIRECAO_LUZ
        self._vao_agua = ctx.vertex_array(
            self.prog_agua,
            [(ctx.buffer(av.tobytes()), "3f", "in_position")],
            index_buffer=ctx.buffer(ai.tobytes()),
            index_element_size=4,
        )
        self.triangulos_agua = int(ai.size // 3)

    # ------------------------------------------------------------------
    def _grade(self, subdivisoes: int) -> moderngl.VertexArray:
        v, i = heightmap.build_unit_grid(subdivisoes)
        return self.ctx.vertex_array(
            self.prog,
            [(self.ctx.buffer(v.tobytes()), "2f", "in_xz")],
            index_buffer=self.ctx.buffer(i.tobytes()),
            index_element_size=4,
        )

    def selecionar_blocos(self, cam_x: float, cam_z: float) -> list[lod.QuadNode]:
        blocos: list[lod.QuadNode] = []
        lod.select(self._quadtree, cam_x, cam_z, self.lod_fator_split, blocos)
        return blocos

    # ------------------------------------------------------------------
    def desenhar(
        self,
        view: glm.mat4,
        proj: glm.mat4,
        cam_pos,
        *,
        nivel_mar: float = 0.0,
        tempo: float = 0.0,
        lod_ligado: bool = True,
        morph: bool = True,
        debug_lod: bool = False,
    ) -> EstatisticasFrame:
        """Desenha terreno (opaco) + água (translúcida). NÃO limpa a tela."""
        ctx = self.ctx
        cam_pos = tuple(cam_pos)
        view_b = view.to_bytes()
        proj_b = proj.to_bytes()

        # Reafirma a textura de altura na unidade 0 a cada frame — outras
        # partes (HUD) podem ter usado essa unidade no frame anterior.
        self._tex.use(location=0)

        self.prog["u_view"].write(view_b)
        self.prog["u_proj"].write(proj_b)
        self.prog["u_camera_pos"].value = cam_pos
        self.prog["u_sea_level"].value = nivel_mar
        self.prog["u_debug_lod"].value = bool(debug_lod)
        self.prog["u_morph_ligado"].value = bool(morph and lod_ligado)

        if lod_ligado:
            blocos = self.selecionar_blocos(cam_pos[0], cam_pos[2])
            vao = self._vao_bloco
            self.prog["u_grid_dim"].value = float(self.lod_subdivisoes)
            tri_bloco = self.triangulos_por_bloco
        else:
            if self._vao_ingenuo is None:
                raise RuntimeError("Cena criada sem a malha ingênua (construir_ingenuo=False).")
            blocos = [self._bloco_raiz]
            vao = self._vao_ingenuo
            self.prog["u_grid_dim"].value = float(self.resolucao_heightmap)
            tri_bloco = self.triangulos_ingenuo

        k = self.lod_fator_split
        for bloco in blocos:
            r_bloco = bloco.size * k                 # ~ borda interna do alcance
            r_pai = 2.0 * r_bloco                    # o bloco-pai assume aqui
            self.prog["u_node_offset"].value = bloco.offset
            self.prog["u_node_scale"].value = bloco.size
            self.prog["u_node_level"].value = float(bloco.depth)
            self.prog["u_morph_start"].value = r_bloco + 0.55 * (r_pai - r_bloco)
            self.prog["u_morph_end"].value = r_pai
            vao.render(moderngl.TRIANGLES)

        ctx.enable(moderngl.BLEND)
        self.prog_agua["u_view"].write(view_b)
        self.prog_agua["u_proj"].write(proj_b)
        self.prog_agua["u_camera_pos"].value = cam_pos
        self.prog_agua["u_sea_level"].value = nivel_mar
        self.prog_agua["u_time"].value = tempo
        self._vao_agua.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)

        return EstatisticasFrame(
            blocos=len(blocos),
            draw_calls=len(blocos) + 1,
            triangulos=len(blocos) * tri_bloco + self.triangulos_agua,
        )
