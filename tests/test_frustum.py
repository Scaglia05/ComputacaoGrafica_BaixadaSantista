"""
=============================================================================
 test_frustum.py  —  Frustum culling sobre a quadtree do CDLOD
=============================================================================

Escritos ANTES da implementação (TDD).

Ideia: descartar os blocos da quadtree que estão TOTALMENTE fora do campo de
visão da câmera. Cada bloco vira uma caixa (AABB): o lado em XZ vem da própria
quadtree e a faixa vertical [y_min, y_max] vem do heightmap. Um bloco só é
descartado se a caixa inteira estiver do lado de fora de ALGUM dos 6 planos
do frustum — um teste conservador: na dúvida, o bloco é desenhado.

O critério de aceite mais forte (e mais simples de entender) é este:

    desenhar com culling e sem culling deve gerar a MESMA IMAGEM, pixel a pixel.

Se o culling descartar um bloco que aparecia na tela, a imagem muda e o teste
reprova. O teste geométrico (CPU) cobre a mesma ideia sem precisar de GPU.

Orçamento de desempenho: testar os 1365 nós num laço Python custa ~9 ms por
quadro (o quadro inteiro hoje leva ~1,1 ms). Por isso o teste exige a versão
vetorizada (numpy), que mede ~0,09 ms.
"""

from __future__ import annotations

import time
import unittest

import glm
import numpy as np

from _base import (
    TAMANHO_MUNDO, LARGURA, ALTURA, CEU,
    criar_contexto_gl, camera_aleatoria, matriz_view, projecao,
)

import bench
import dem
import lod
import scene

N_NOS_PROFUNDIDADE_5 = sum(4 ** k for k in range(6))      # 1 + 4 + 16 + 64 + 256 + 1024


def altura_bilinear(alturas, x, z, tamanho):
    """O que a GPU faz ao amostrar a textura R32F com filtro LINEAR, em numpy."""
    n = alturas.shape[0]
    u = np.clip((x / tamanho + 0.5) * n - 0.5, 0, n - 1)
    v = np.clip((z / tamanho + 0.5) * n - 0.5, 0, n - 1)
    i0, j0 = np.floor(u).astype(int), np.floor(v).astype(int)
    i1, j1 = np.minimum(i0 + 1, n - 1), np.minimum(j0 + 1, n - 1)
    fu, fv = u - i0, v - j0
    a, b, c, d = alturas[j0, i0], alturas[j0, i1], alturas[j1, i0], alturas[j1, i1]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def vertices_do_bloco(no, alturas, n=33):
    """Os 33x33 vértices que o bloco desenha, em coordenadas homogêneas (N,4)."""
    lin = np.linspace(0.0, 1.0, n)
    xs, zs = np.meshgrid(no.cx - no.size / 2 + lin * no.size, no.cz - no.size / 2 + lin * no.size)
    ys = altura_bilinear(alturas, xs, zs, TAMANHO_MUNDO)
    return np.stack([xs.ravel(), ys.ravel(), zs.ravel(), np.ones(xs.size)], axis=1)


def algum_vertice_visivel(vertices, view, proj) -> bool:
    # np.array(mat4) do PyGLM vem como [linha][coluna]; para vértices em linhas: clip = V @ M^T.
    clip = vertices @ np.array(proj * view, dtype=np.float64).T
    w = clip[:, 3]
    dentro = (w > 0) & (np.abs(clip[:, 0]) <= w) & (np.abs(clip[:, 1]) <= w) & (np.abs(clip[:, 2]) <= w)
    return bool(dentro.any())


class ArvoreBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alturas, _ = dem.carregar_heightmap(resolution=512, world_size=TAMANHO_MUNDO)
        cls.raiz = lod.build_quadtree(TAMANHO_MUNDO, 5)
        lod.atribuir_faixas_altura(cls.raiz, cls.alturas, TAMANHO_MUNDO)
        cls.nos = lod.listar_nos(cls.raiz)
        cls.caixas = lod.caixas_dos_nos(cls.raiz)
        cls.proj = projecao()

    def selecionar(self, pos, alvo, culling):
        view = matriz_view(pos, alvo)
        visiveis = lod.nos_visiveis(self.caixas, lod.planos_do_frustum(view, self.proj)) if culling else None
        saida = []
        lod.select(self.raiz, pos.x, pos.z, 2.2, saida, visiveis=visiveis)
        return saida


class TestFaixasDeAltura(ArvoreBase):
    def test_indices_dos_nos_sao_sequenciais_e_unicos(self):
        self.assertEqual(len(self.nos), N_NOS_PROFUNDIDADE_5)
        self.assertEqual([n.indice for n in self.nos], list(range(N_NOS_PROFUNDIDADE_5)))

    def test_raiz_cobre_o_minimo_e_o_maximo_do_terreno(self):
        self.assertAlmostEqual(self.raiz.y_min, float(self.alturas.min()), places=5)
        self.assertAlmostEqual(self.raiz.y_max, float(self.alturas.max()), places=5)

    def test_pai_contem_a_faixa_dos_filhos(self):
        for no in self.nos:
            for filho in no.children:
                self.assertLessEqual(no.y_min, filho.y_min)
                self.assertGreaterEqual(no.y_max, filho.y_max)

    def test_faixa_cobre_toda_altura_que_a_gpu_amostraria_no_bloco(self):
        # A GPU interpola entre texels vizinhos; na borda do bloco isso puxa
        # valores de texels de FORA do bloco. A faixa precisa de uma margem.
        rng = np.random.default_rng(1)
        folhas = [n for n in self.nos if not n.children]
        for no in rng.choice(folhas, size=150, replace=False):
            x = no.cx + rng.uniform(-0.5, 0.5, 80) * no.size
            z = no.cz + rng.uniform(-0.5, 0.5, 80) * no.size
            h = altura_bilinear(self.alturas, x, z, TAMANHO_MUNDO)
            self.assertGreaterEqual(float(h.min()), no.y_min - 1e-4)
            self.assertLessEqual(float(h.max()), no.y_max + 1e-4)


class TestPlanosDoFrustum(unittest.TestCase):
    def setUp(self):
        view = matriz_view(glm.vec3(0, 40, 90), glm.vec3(0, 0, 0))
        self.planos = lod.planos_do_frustum(view, projecao())

    def dentro(self, ponto):
        p = np.array(ponto, dtype=np.float64)
        return bool((self.planos[:, :3] @ p + self.planos[:, 3] >= 0).all())

    def test_formato_seis_planos_de_quatro_coeficientes(self):
        self.assertEqual(self.planos.shape, (6, 4))

    def test_ponto_na_frente_da_camera_esta_dentro(self):
        self.assertTrue(self.dentro((0, 10, 0)))

    def test_ponto_atras_da_camera_esta_fora(self):
        self.assertFalse(self.dentro((0, 40, 300)))

    def test_ponto_alem_do_plano_far_esta_fora(self):
        self.assertFalse(self.dentro((0, 0, -4000)))

    def test_ponto_muito_a_esquerda_e_muito_a_direita_estao_fora(self):
        self.assertFalse(self.dentro((-2000, 10, 0)))
        self.assertFalse(self.dentro((2000, 10, 0)))


class TestSelecaoComCulling(ArvoreBase):
    def test_mascara_tem_um_valor_por_no(self):
        view = matriz_view(glm.vec3(0, 40, 90), glm.vec3(0, 0, 0))
        mascara = lod.nos_visiveis(self.caixas, lod.planos_do_frustum(view, self.proj))
        self.assertEqual(mascara.dtype, bool)
        self.assertEqual(mascara.shape, (N_NOS_PROFUNDIDADE_5,))

    def test_select_sem_mascara_e_igual_a_mascara_toda_verdadeira(self):
        pos = glm.vec3(10, 40, 90)
        sem = []
        lod.select(self.raiz, pos.x, pos.z, 2.2, sem)
        com = []
        lod.select(self.raiz, pos.x, pos.z, 2.2, com, visiveis=np.ones(N_NOS_PROFUNDIDADE_5, dtype=bool))
        self.assertEqual([n.indice for n in sem], [n.indice for n in com])

    def test_camera_de_costas_para_o_terreno_nao_seleciona_nada(self):
        pos = glm.vec3(0, 40, 400)
        self.assertEqual(self.selecionar(pos, pos + glm.vec3(0, 0, 10), culling=True), [])

    def test_camera_que_olha_para_o_terreno_seleciona_algo(self):
        pos = glm.vec3(0, 40, 90)
        self.assertGreater(len(self.selecionar(pos, glm.vec3(0, 0, 0), culling=True)), 0)

    def test_culling_so_remove_blocos_nunca_acrescenta(self):
        rng = np.random.default_rng(3)
        for _ in range(100):
            pos, alvo = camera_aleatoria(rng)
            sem = {n.indice for n in self.selecionar(pos, alvo, culling=False)}
            com = {n.indice for n in self.selecionar(pos, alvo, culling=True)}
            self.assertTrue(com <= sem)

    def test_bloco_descartado_nao_tem_nenhum_vertice_visivel(self):
        # Verdade-fundamento geométrica, sem GPU: projeta os vértices REAIS do
        # bloco (com a altura que a GPU amostraria) e confere que nenhum cai
        # dentro do volume de visão. Só detecta culling errado (nunca falso
        # alarme); o teste de imagem idêntica cobre triângulos que cruzam o frustum.
        rng = np.random.default_rng(5)
        descartados_total = 0
        for _ in range(150):
            pos, alvo = camera_aleatoria(rng)
            view = matriz_view(pos, alvo)
            sem = self.selecionar(pos, alvo, culling=False)
            com_ids = {n.indice for n in self.selecionar(pos, alvo, culling=True)}
            for no in sem:
                if no.indice not in com_ids:
                    descartados_total += 1
                    self.assertFalse(
                        algum_vertice_visivel(vertices_do_bloco(no, self.alturas), view, self.proj),
                        f"bloco {no.indice} (nível {no.depth}) foi descartado mas aparece na tela",
                    )
        self.assertGreater(descartados_total, 500, "o teste não exercitou o descarte o bastante")

    def test_custo_da_mascara_vetorizada_cabe_no_orcamento(self):
        view = matriz_view(glm.vec3(-90, 15, 135), glm.vec3(90, 13, -135))
        n = 300
        t0 = time.perf_counter()
        for _ in range(n):
            lod.nos_visiveis(self.caixas, lod.planos_do_frustum(view, self.proj))
        ms = (time.perf_counter() - t0) / n * 1000.0
        # medido ~0,1 ms; um laço Python custaria ~9 ms. 1 ms dá folga sem deixar a regressão passar.
        self.assertLess(ms, 1.0, f"mascara + planos levaram {ms:.3f} ms por quadro")


class TestCullingNaGPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = criar_contexto_gl()
        cls.fbo = cls.ctx.simple_framebuffer((LARGURA, ALTURA))
        cls.cena = scene.Cena(cls.ctx, fonte="dem", resolucao_heightmap=512,
                              tamanho_mundo=TAMANHO_MUNDO, verboso=False)
        cls.proj = projecao()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.release()

    def quadro(self, pos, alvo, culling):
        self.fbo.use()
        self.fbo.clear(*CEU)
        stats = self.cena.desenhar(matriz_view(pos, alvo), self.proj, tuple(pos),
                                   lod_ligado=True, morph=True, frustum_culling=culling)
        self.ctx.finish()
        return stats, self.fbo.read()

    def test_imagem_identica_nas_4_cameras_do_benchmark(self):
        cameras = bench.cameras(self.cena.altura_ref, TAMANHO_MUNDO)
        for nome, (pos, alvo) in cameras.items():
            sem, img_sem = self.quadro(pos, alvo, culling=False)
            com, img_com = self.quadro(pos, alvo, culling=True)
            self.assertEqual(img_sem, img_com, f"câmera '{nome}': o culling mudou a imagem")
            self.assertLessEqual(com.blocos, sem.blocos)
            if nome in ("rasante", "encosta"):
                self.assertLess(com.blocos, sem.blocos, f"câmera '{nome}' deveria descartar blocos")

    def test_imagem_identica_com_cameras_aleatorias_em_varios_quadros(self):
        rng = np.random.default_rng(7)
        com_poda = 0
        for _ in range(40):
            pos, alvo = camera_aleatoria(rng)
            for _quadro in range(2):         # 2 quadros: bugs de estado só aparecem a partir do 2º
                sem, img_sem = self.quadro(pos, alvo, culling=False)
                com, img_com = self.quadro(pos, alvo, culling=True)
                self.assertEqual(img_sem, img_com, f"câmera {tuple(pos)} → {tuple(alvo)}: imagem diferente")
                com_poda += com.blocos < sem.blocos
        self.assertGreater(com_poda, 20, "o teste quase não exercitou o descarte")

    def test_culling_vem_desligado_por_padrao(self):
        pos, alvo = glm.vec3(0, 40, 90), glm.vec3(0, 0, 0)
        stats = self.cena.desenhar(matriz_view(pos, alvo), self.proj, tuple(pos))
        self.assertEqual(stats.nos_podados, 0)
        esperado = len(self.cena.selecionar_blocos(pos.x, pos.z))
        self.assertEqual(stats.blocos, esperado)

    def test_estatisticas_informam_o_que_foi_podado(self):
        cameras = bench.cameras(self.cena.altura_ref, TAMANHO_MUNDO)
        pos, alvo = cameras["rasante"]
        sem, _ = self.quadro(pos, alvo, culling=False)
        com, _ = self.quadro(pos, alvo, culling=True)
        self.assertGreater(com.nos_podados, 0)
        self.assertLess(com.triangulos, sem.triangulos)
        self.assertLess(com.draw_calls, sem.draw_calls)


class TestBenchComFrustum(unittest.TestCase):
    def test_condicoes_antigas_continuam_iguais_e_a_nova_foi_acrescentada(self):
        por_nome = {c[0]: c for c in bench.CONDICOES}
        # (nome, lod_ligado, morph, culling) — as 3 originais não podem mudar.
        self.assertEqual(por_nome["sem_lod"][1:], (False, False, False))
        self.assertEqual(por_nome["cdlod"][1:], (True, True, False))
        self.assertEqual(por_nome["cdlod_sem_morph"][1:], (True, False, False))
        self.assertEqual(por_nome["cdlod_frustum"][1:], (True, True, True))

    def test_medir_aceita_culling_e_desenha_menos_blocos(self):
        ctx = criar_contexto_gl()
        try:
            fbo = ctx.simple_framebuffer((LARGURA, ALTURA))
            cena = scene.Cena(ctx, fonte="dem", resolucao_heightmap=256,
                              tamanho_mundo=TAMANHO_MUNDO, verboso=False)
            pos, alvo = bench.cameras(cena.altura_ref, TAMANHO_MUNDO)["rasante"]
            view, proj = matriz_view(pos, alvo), projecao()
            sem = bench.medir(ctx, cena, fbo, view, proj, pos, lod_ligado=True, morph=True, culling=False)
            com = bench.medir(ctx, cena, fbo, view, proj, pos, lod_ligado=True, morph=True, culling=True)
            self.assertLess(com[0].blocos, sem[0].blocos)
        finally:
            ctx.release()


if __name__ == "__main__":
    unittest.main()
