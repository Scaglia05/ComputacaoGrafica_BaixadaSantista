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
    nos_podados: int = 0  # subárvores descartadas pelo frustum culling (0 = culling desligado)


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
        construir_lod: bool = True,
        construir_ingenuo: bool = True,
        verboso: bool = True,
    ):
        # `construir_lod` / `construir_ingenuo` existem para a medição de
        # memória: cada modo de render só precisa da SUA malha. Construir as
        # duas sempre (o padrão) é o que fazia RAM/VRAM não diferirem entre modos.
        self.ctx = ctx
        self.tamanho_mundo = tamanho_mundo
        self.resolucao_heightmap = resolucao_heightmap
        self.lod_subdivisoes = lod_subdivisoes
        self.lod_fator_split = lod_fator_split

        alturas = self._carregar_alturas(fonte, escala_altura, seed, verboso)
        self.altura_ref = max(abs(float(alturas.min())), abs(float(alturas.max()))) or 1.0
        self._criar_textura_altura(alturas)
        self._criar_terreno(construir_lod, construir_ingenuo)
        self._criar_quadtree(alturas, lod_profundidade)
        self._criar_agua(resolucao_agua)

    # --- montagem (chamada uma vez, no construtor) --------------------
    def _carregar_alturas(self, fonte: str, escala_altura: float, seed: int, verboso: bool):
        """Devolve a matriz de alturas (N x N, unidades de mundo) e define
        `self.unidades_por_metro` (quantas unidades de mundo valem 1 metro)."""
        if fonte == "dem":
            if verboso:
                print("Carregando DEM da Baixada Santista (baixa tiles na 1a vez)...")
            alturas, self.unidades_por_metro = dem.carregar_heightmap(
                resolution=self.resolucao_heightmap, world_size=self.tamanho_mundo
            )
        else:
            if verboso:
                print("Gerando terreno procedural...")
            alturas = heightmap.generate_heightmap(
                resolution=self.resolucao_heightmap, height_scale=escala_altura, seed=seed
            )
            # Sem escala geográfica real: amplitude ~ 600 m só para os
            # cenários de nível do mar (em metros) fazerem sentido.
            self.unidades_por_metro = escala_altura / 600.0
        return alturas

    def _criar_textura_altura(self, alturas) -> None:
        """Sobe as alturas para a GPU como textura R32F (1 float por texel)."""
        n = self.resolucao_heightmap
        self._tex = self.ctx.texture((n, n), 1, alturas.tobytes(), dtype="f4")
        self._tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._tex.repeat_x = False
        self._tex.repeat_y = False
        self._tex.use(location=0)
        self._bytes_textura = n * n * 4          # R32F = 4 bytes por texel

    def _criar_terreno(self, construir_lod: bool, construir_ingenuo: bool) -> None:
        """Programa (shaders) do terreno + as duas grades: a do CDLOD (pequena,
        desenhada várias vezes) e a ingênua (uma malha só, na resolução total)."""
        self.prog = _programa(self.ctx, "terrain")
        self.prog["u_heightmap"].value = 0
        self.prog["u_world_size"].value = (self.tamanho_mundo, self.tamanho_mundo)
        self.prog["u_height_scale"].value = self.altura_ref
        self.prog["u_light_dir"].value = DIRECAO_LUZ

        self._vao_bloco, self._bytes_malha_lod = (
            self._grade(self.lod_subdivisoes) if construir_lod else (None, 0)
        )
        self._vao_ingenuo, self._bytes_malha_ingenua = (
            self._grade(self.resolucao_heightmap) if construir_ingenuo else (None, 0)
        )
        self.triangulos_por_bloco = self.lod_subdivisoes ** 2 * 2
        self.triangulos_ingenuo = self.resolucao_heightmap ** 2 * 2

    def _criar_quadtree(self, alturas, profundidade: int) -> None:
        self._quadtree = lod.build_quadtree(self.tamanho_mundo, profundidade)
        # Caixas dos nós para o frustum culling: a faixa de altura de cada bloco
        # sai do heightmap, uma vez só (aqui), e o frame só consulta os vetores.
        lod.atribuir_faixas_altura(self._quadtree, alturas, self.tamanho_mundo)
        self._caixas = lod.caixas_dos_nos(self._quadtree)
        self._bloco_raiz = lod.QuadNode(0.0, 0.0, self.tamanho_mundo, 0)   # a malha ingênua = 1 bloco só

    def _criar_agua(self, resolucao_agua: int) -> None:
        vertices, indices = water.build_water_plane(
            resolution=resolucao_agua, world_size=self.tamanho_mundo * 1.6
        )
        self.prog_agua = _programa(self.ctx, "water")
        self.prog_agua["u_light_dir"].value = DIRECAO_LUZ
        vbo = self.ctx.buffer(vertices.tobytes())
        ibo = self.ctx.buffer(indices.tobytes())
        self._vao_agua = self.ctx.vertex_array(
            self.prog_agua, [(vbo, "3f", "in_position")],
            index_buffer=ibo, index_element_size=4,
        )
        self.triangulos_agua = int(indices.size // 3)
        self._bytes_agua = vbo.size + ibo.size

    def _grade(self, subdivisoes: int) -> tuple[moderngl.VertexArray, int]:
        """Cria a grade unitária e devolve (VAO, bytes ocupados na GPU pelos buffers)."""
        v, i = heightmap.build_unit_grid(subdivisoes)
        vbo, ibo = self.ctx.buffer(v.tobytes()), self.ctx.buffer(i.tobytes())
        vao = self.ctx.vertex_array(
            self.prog, [(vbo, "2f", "in_xz")], index_buffer=ibo, index_element_size=4
        )
        return vao, vbo.size + ibo.size

    def bytes_alocados(self) -> dict[str, int]:
        """Bytes que ESTA aplicação aloca na GPU (texturas + buffers), por parte.

        Diferente do nvidia-smi (que mostra a GPU inteira, com outros programas
        e só em placas NVIDIA), esta conta é exata, isolada e vale para qualquer
        GPU. Não inclui o framebuffer (é igual em todos os modos).
        """
        partes = {
            "textura_altura": self._bytes_textura,
            "malha_lod": self._bytes_malha_lod,
            "malha_ingenua": self._bytes_malha_ingenua,
            "agua": self._bytes_agua,
        }
        partes["total"] = sum(partes.values())
        return partes

    # --- seleção de blocos ---------------------------------------------
    def _selecionar(self, cam_x: float, cam_z: float, visiveis=None):
        """Seleção de blocos; devolve (blocos, nós_podados)."""
        blocos: list[lod.QuadNode] = []
        podados = lod.select(
            self._quadtree, cam_x, cam_z, self.lod_fator_split, blocos, visiveis
        )
        return blocos, podados

    def selecionar_blocos(self, cam_x: float, cam_z: float) -> list[lod.QuadNode]:
        return self._selecionar(cam_x, cam_z)[0]

    # --- desenho (todo frame) ------------------------------------------
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
        frustum_culling: bool = False,
    ) -> EstatisticasFrame:
        """Desenha terreno (opaco) + água (translúcida). NÃO limpa a tela.

        `frustum_culling` (só vale com LOD ligado): poda os blocos que estão
        fora do campo de visão. Vem DESLIGADO por padrão para que as medições
        antigas continuem reproduzíveis; a imagem gerada é idêntica nos dois casos.
        """
        cam_pos = tuple(cam_pos)

        # Reafirma a textura de altura na unidade 0 a cada frame — outras
        # partes (HUD) podem ter usado essa unidade no frame anterior.
        self._tex.use(location=0)

        blocos, podados, triangulos_por_bloco = self._desenhar_terreno(
            view, proj, cam_pos, nivel_mar, lod_ligado, morph, debug_lod, frustum_culling,
        )
        self._desenhar_agua(view, proj, cam_pos, nivel_mar, tempo)

        return EstatisticasFrame(
            blocos=len(blocos),
            draw_calls=len(blocos) + 1,
            triangulos=len(blocos) * triangulos_por_bloco + self.triangulos_agua,
            nos_podados=podados,
        )

    def _desenhar_terreno(self, view, proj, cam_pos, nivel_mar,
                          lod_ligado, morph, debug_lod, frustum_culling):
        """Escolhe os blocos e desenha cada um. Devolve (blocos, podados, triângulos por bloco)."""
        self.prog["u_view"].write(view.to_bytes())
        self.prog["u_proj"].write(proj.to_bytes())
        self.prog["u_camera_pos"].value = cam_pos
        self.prog["u_sea_level"].value = nivel_mar
        self.prog["u_debug_lod"].value = bool(debug_lod)
        self.prog["u_morph_ligado"].value = bool(morph and lod_ligado)

        podados = 0
        if lod_ligado:
            if self._vao_bloco is None:
                raise RuntimeError("Cena criada sem a malha do CDLOD (construir_lod=False).")
            visiveis = None
            if frustum_culling:
                visiveis = lod.nos_visiveis(self._caixas, lod.planos_do_frustum(view, proj))
            blocos, podados = self._selecionar(cam_pos[0], cam_pos[2], visiveis)
            vao = self._vao_bloco
            grade = self.lod_subdivisoes
            triangulos_por_bloco = self.triangulos_por_bloco
        else:
            if self._vao_ingenuo is None:
                raise RuntimeError("Cena criada sem a malha ingênua (construir_ingenuo=False).")
            blocos = [self._bloco_raiz]
            vao = self._vao_ingenuo
            grade = self.resolucao_heightmap
            triangulos_por_bloco = self.triangulos_ingenuo
        self.prog["u_grid_dim"].value = float(grade)

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
        return blocos, podados, triangulos_por_bloco

    def _desenhar_agua(self, view, proj, cam_pos, nivel_mar, tempo) -> None:
        self.ctx.enable(moderngl.BLEND)
        self.prog_agua["u_view"].write(view.to_bytes())
        self.prog_agua["u_proj"].write(proj.to_bytes())
        self.prog_agua["u_camera_pos"].value = cam_pos
        self.prog_agua["u_sea_level"].value = nivel_mar
        self.prog_agua["u_time"].value = tempo
        self._vao_agua.render(moderngl.TRIANGLES)
        self.ctx.disable(moderngl.BLEND)
