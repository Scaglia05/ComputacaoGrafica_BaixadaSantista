"""
=============================================================================
 test_memoria.py  —  Medição de memória ISOLADA por modo de renderização
=============================================================================

Escritos ANTES da implementação (TDD). O problema que estes testes cobrem:

  No benchmark original os 3 modos compartilhavam a MESMA `Cena`, com a malha
  ingênua sempre residente na GPU. Por isso RAM/VRAM não mudavam entre
  "sem LOD" e "CDLOD". Para isolar o ganho de memória do LOD é preciso:

    1. uma `Cena` que construa só o que o modo precisa;
    2. um jeito exato de contar os bytes que a aplicação aloca (não depende
       de nvidia-smi, então funciona em GPU de qualquer marca);
    3. cada modo medido num PROCESSO NOVO, para que um não contamine o outro.

Fórmulas esperadas (escritas aqui de forma independente do código, de
propósito — se o código errar a conta, o teste pega):

  malha em grade com `n` subdivisões:
      vértices : (n+1)^2 * 2 floats * 4 B   = (n+1)^2 * 8
      índices  : n^2 * 2 triângulos * 3 * 4 = n^2 * 24     (uint32)
  textura de altura (R32F) : lado^2 * 4
  água (resolução r)       : r^2 * 12  +  (r-1)^2 * 24
"""

from __future__ import annotations

import os
import unittest

from _base import TAMANHO_MUNDO, LARGURA, ALTURA, CEU, criar_contexto_gl, matriz_view, projecao

import bench
import scene


def bytes_malha(n: int) -> int:
    return (n + 1) ** 2 * 8 + n ** 2 * 24


def bytes_textura(lado: int) -> int:
    return lado * lado * 4


def bytes_agua(r: int) -> int:
    return r * r * 12 + (r - 1) ** 2 * 24


class TestContabilidadeDaCena(unittest.TestCase):
    """`Cena.bytes_alocados()` e as flags de construção seletiva."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = criar_contexto_gl()
        cls.fbo = cls.ctx.simple_framebuffer((LARGURA, ALTURA))
        cls.proj = projecao()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.release()

    def _cena(self, res=256, **kw):
        return scene.Cena(self.ctx, fonte="dem", resolucao_heightmap=res,
                          tamanho_mundo=TAMANHO_MUNDO, verboso=False, **kw)

    def test_cena_completa_bate_com_as_formulas(self):
        b = self._cena(256).bytes_alocados()
        self.assertEqual(b["textura_altura"], bytes_textura(256))
        self.assertEqual(b["malha_ingenua"], bytes_malha(256))
        self.assertEqual(b["malha_lod"], bytes_malha(32))
        self.assertEqual(b["agua"], bytes_agua(256))

    def test_total_e_a_soma_das_partes(self):
        b = self._cena(256).bytes_alocados()
        partes = b["textura_altura"] + b["malha_lod"] + b["malha_ingenua"] + b["agua"]
        self.assertEqual(b["total"], partes)

    def test_so_cdlod_nao_aloca_a_malha_ingenua(self):
        b = self._cena(256, construir_ingenuo=False).bytes_alocados()
        self.assertEqual(b["malha_ingenua"], 0)
        self.assertEqual(b["malha_lod"], bytes_malha(32))

    def test_so_ingenuo_nao_aloca_a_malha_lod(self):
        b = self._cena(256, construir_lod=False).bytes_alocados()
        self.assertEqual(b["malha_lod"], 0)
        self.assertEqual(b["malha_ingenua"], bytes_malha(256))

    def test_pedir_lod_sem_ter_construido_da_erro_claro(self):
        cena = self._cena(256, construir_lod=False)
        with self.assertRaises(RuntimeError):
            cena.desenhar(matriz_view((0, 40, 90), (0, 0, 0)), self.proj, (0, 40, 90), lod_ligado=True)

    def test_pedir_ingenuo_sem_ter_construido_da_erro_claro(self):
        cena = self._cena(256, construir_ingenuo=False)
        with self.assertRaises(RuntimeError):
            cena.desenhar(matriz_view((0, 40, 90), (0, 0, 0)), self.proj, (0, 40, 90), lod_ligado=False)

    def _quadro(self, cena, lod_ligado):
        pos = (0.0, 40.0, 90.0)
        self.fbo.use()
        self.fbo.clear(*CEU)
        cena.desenhar(matriz_view(pos, (0.0, 0.0, 0.0)), self.proj, pos, lod_ligado=lod_ligado)
        self.ctx.finish()
        return self.fbo.read()

    def test_cena_isolada_so_cdlod_desenha_o_mesmo_quadro_da_completa(self):
        completa = self._cena(256)
        isolada = self._cena(256, construir_ingenuo=False)
        # 2 quadros: um bug real deste projeto só aparecia a partir do 2º frame.
        for _ in range(2):
            self.assertEqual(self._quadro(completa, True), self._quadro(isolada, True))

    def test_cena_isolada_so_ingenuo_desenha_o_mesmo_quadro_da_completa(self):
        completa = self._cena(256)
        isolada = self._cena(256, construir_lod=False)
        for _ in range(2):
            self.assertEqual(self._quadro(completa, False), self._quadro(isolada, False))


class TestMedicaoIsolada(unittest.TestCase):
    """`bench.memoria_isolada`: cada (modo, resolução) num processo novo."""

    CAMPOS = {
        "modo", "resolucao", "pid", "gpu", "triangulos",
        "bytes_app_mb", "bytes_textura_mb", "bytes_malha_mb",
        "rss_antes_mb", "rss_depois_mb", "rss_pico_mb",
        "vram_antes_mb", "vram_depois_mb",
    }

    @classmethod
    def setUpClass(cls):
        criar_contexto_gl().release()   # pula a classe inteira se não houver GPU
        cls.r256 = bench.memoria_isolada(["sem_lod", "cdlod", "cdlod_sem_morph", "cdlod_frustum"], [256])
        cls.r1024 = bench.memoria_isolada(["sem_lod", "cdlod"], [1024])

    def _achar(self, resultados, modo):
        return next(r for r in resultados if r["modo"] == modo)

    def test_cada_modo_roda_em_processo_proprio(self):
        pids = [r["pid"] for r in self.r256]
        self.assertEqual(len(set(pids)), len(pids), "dois modos compartilharam o mesmo processo")
        self.assertNotIn(os.getpid(), pids, "a medição rodou dentro do processo do teste")

    def test_resultado_tem_todos_os_campos(self):
        for r in self.r256 + self.r1024:
            self.assertTrue(self.CAMPOS <= set(r), f"faltam campos: {self.CAMPOS - set(r)}")

    def test_rss_e_numero_e_vram_e_numero_ou_none(self):
        for r in self.r256:
            for campo in ("rss_antes_mb", "rss_depois_mb", "rss_pico_mb", "bytes_app_mb"):
                self.assertIsInstance(r[campo], float)
                self.assertGreater(r[campo], 0.0)
            for campo in ("vram_antes_mb", "vram_depois_mb"):
                self.assertTrue(r[campo] is None or isinstance(r[campo], float))

    def test_pico_de_memoria_nunca_e_menor_que_o_valor_final(self):
        for r in self.r256:
            self.assertGreaterEqual(r["rss_pico_mb"] + 0.5, r["rss_depois_mb"])

    def test_diferenca_de_bytes_entre_sem_lod_e_cdlod_e_a_malha_ingenua(self):
        sem = self._achar(self.r1024, "sem_lod")
        cd = self._achar(self.r1024, "cdlod")
        esperado_mb = (bytes_malha(1024) - bytes_malha(32)) / 1e6      # ~33,5 MB
        self.assertAlmostEqual(sem["bytes_app_mb"] - cd["bytes_app_mb"], esperado_mb, delta=0.5)

    def test_malha_do_cdlod_nao_cresce_com_a_resolucao_e_a_ingenua_cresce(self):
        cd256, cd1024 = self._achar(self.r256, "cdlod"), self._achar(self.r1024, "cdlod")
        sem256, sem1024 = self._achar(self.r256, "sem_lod"), self._achar(self.r1024, "sem_lod")
        self.assertAlmostEqual(cd256["bytes_malha_mb"], cd1024["bytes_malha_mb"], places=6)
        self.assertGreater(sem1024["bytes_malha_mb"], 10 * sem256["bytes_malha_mb"])

    def test_modos_de_cdlod_tem_o_mesmo_consumo_de_malha(self):
        # morphing e culling são só uniforms/máscaras: não mudam a malha na GPU.
        base = self._achar(self.r256, "cdlod")["bytes_malha_mb"]
        for modo in ("cdlod_sem_morph", "cdlod_frustum"):
            self.assertAlmostEqual(self._achar(self.r256, modo)["bytes_malha_mb"], base, places=6)

    def test_modo_invalido_levanta_erro(self):
        with self.assertRaises(ValueError):
            bench.memoria_isolada(["modo_que_nao_existe"], [256])


if __name__ == "__main__":
    unittest.main()
