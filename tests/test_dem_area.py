"""
Testes do DEM (`dem.py`) e da área alagada (`area_alagada.py`).

Rodam offline e sem GPU: usam matrizes minúsculas feitas à mão, nunca baixam tiles.
"""

import unittest

import numpy as np

import _base  # noqa: F401  (coloca src/ no sys.path)
import area_alagada
import dem


class TestDecodificacaoTerrarium(unittest.TestCase):
    def test_zero_metros(self):
        # R=128, G=0, B=0  ->  128*256 - 32768 = 0 m
        rgb = np.array([[[128.0, 0.0, 0.0]]])
        self.assertEqual(dem._rgb_para_metros(rgb)[0, 0], 0.0)

    def test_valor_conhecido_com_fracao(self):
        # R=128, G=10, B=128  ->  10 + 128/256 = 10,5 m
        rgb = np.array([[[128.0, 10.0, 128.0]]])
        self.assertAlmostEqual(dem._rgb_para_metros(rgb)[0, 0], 10.5)

    def test_batimetria_negativa(self):
        rgb = np.array([[[127.0, 156.0, 0.0]]])   # 127*256 + 156 - 32768 = -100 m
        self.assertEqual(dem._rgb_para_metros(rgb)[0, 0], -100.0)


class TestRemoverSpikes(unittest.TestCase):
    def test_remove_pico_isolado(self):
        elev = np.full((7, 7), 10.0)
        elev[3, 3] = 5000.0                       # agulha absurda
        limpo = dem._remover_spikes(elev, limiar_m=80.0)
        self.assertEqual(limpo[3, 3], 10.0)

    def test_preserva_relevo_suave(self):
        # Rampa suave: nenhum texel foge da mediana por mais que o limiar.
        elev = np.tile(np.linspace(0.0, 30.0, 8), (8, 1))
        limpo = dem._remover_spikes(elev, limiar_m=80.0)
        np.testing.assert_allclose(limpo, elev.astype(np.float32))

    def test_preserva_degrau_grande_e_largo(self):
        # Uma escarpa (metade 0 m, metade 500 m) NÃO é spike: tem vizinhos iguais.
        elev = np.zeros((8, 8))
        elev[:, 4:] = 500.0
        limpo = dem._remover_spikes(elev, limiar_m=80.0)
        np.testing.assert_allclose(limpo, elev.astype(np.float32))


class TestTiles(unittest.TestCase):
    def test_origem_do_mapa(self):
        x, y = dem._lonlat_para_tile(-180.0, 0.0, 1)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 1.0)            # equador = meio do mapa (n/2)

    def test_norte_tem_y_menor(self):
        _, y_norte = dem._lonlat_para_tile(-46.3, -23.7, 11)
        _, y_sul = dem._lonlat_para_tile(-46.3, -24.1, 11)
        self.assertLess(y_norte, y_sul)


class TestAreaAlagada(unittest.TestCase):
    def setUp(self):
        # 0 m (plateau), 0,3 m, 1,5 m, 5 m e dois pontos no mar (-10 m).
        self.elev = np.array([0.0, 0.3, 1.5, 5.0, -10.0, -10.0])
        self.r = area_alagada.calcular_areas(self.elev, 2.0, niveis=(0.5, 2.0, 10.0))

    def test_emersa_ignora_o_mar(self):
        self.assertEqual(self.r["emersa"], 4 * 2.0)

    def test_area_cresce_com_o_nivel(self):
        areas = [self.r[n][0] for n in (0.5, 2.0, 10.0)]
        self.assertEqual(areas, [2 * 2.0, 3 * 2.0, 4 * 2.0])
        self.assertEqual(areas, sorted(areas))

    def test_porcentagem_chega_a_100_com_nivel_alto(self):
        self.assertAlmostEqual(self.r[10.0][1], 100.0)

    def test_sem_celulas_a_zero_desconta_o_plateau(self):
        self.assertEqual(self.r["zeros"], 1 * 2.0)
        self.assertEqual(self.r[0.5][2], 1 * 2.0)   # só a célula de 0,3 m

    def test_dem_so_com_mar_nao_divide_por_zero(self):
        r = area_alagada.calcular_areas(np.array([-5.0, -1.0]), 1.0, niveis=(1.0,))
        self.assertEqual(r[1.0], (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
