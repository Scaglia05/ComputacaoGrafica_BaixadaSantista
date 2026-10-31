"""
=============================================================================
 dem.py  —  Carrega um DEM real (Baixada Santista) como heightmap
=============================================================================

DEM = Digital Elevation Model (Modelo Digital de Elevação): uma grade de
alturas reais do terreno, medidas por satélite/radar.

Fonte usada aqui
----------------
AWS Terrain Tiles (bucket público `elevation-tiles-prod`), no formato
"terrarium": PNG em que a elevação em metros é decodificada como

        elev = (R * 256 + G + B / 256) - 32768

Não precisa de chave de API. Os dados vêm de SRTM / ASTER / etc. em terra e
de batimetria GEBCO no mar (por isso há valores NEGATIVOS na água — útil:
ao subir o nível do mar, ele preenche o relevo submarino real).

Recorte padrão: **Baixada Santista (Santos/SP)** — costa baixa com a Serra
do Mar logo atrás. O relevo forte exercita bem o LOD, e a planície costeira
plana mostra a área inundada quando o mar sobe.

O resultado sai no MESMO formato de `heightmap.generate_heightmap`:
uma matriz (N, N) float32 em unidades de mundo, com 0 = nível do mar atual.
"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CACHE_DIR = Path(__file__).parent / "data" / "tiles"

# Caixa (norte, sul, oeste, leste) em graus decimais.
BAIXADA_SANTISTA = (-23.70, -24.10, -46.60, -46.05)

PIXELS_POR_TILE = 256


def _lonlat_para_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    """Coordenada (fracionária) de tile no esquema Web Mercator / slippy map."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _baixar_tile(z: int, x: int, y: int) -> Path:
    """Baixa 1 tile (com cache em disco) e devolve o caminho do PNG."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destino = CACHE_DIR / f"{z}_{x}_{y}.png"
    if not destino.exists():
        url = TILE_URL.format(z=z, x=x, y=y)
        with urllib.request.urlopen(url, timeout=30) as resp:
            destino.write_bytes(resp.read())
    return destino


def _juntar_tiles(x0: int, x1: int, y0: int, y1: int, z: int) -> np.ndarray:
    """Baixa os tiles do retângulo [x0..x1] x [y0..y1] e os cola numa imagem RGB só."""
    linhas = []
    for ty in range(y0, y1 + 1):
        colunas = []
        for tx in range(x0, x1 + 1):
            imagem = Image.open(_baixar_tile(z, tx, ty)).convert("RGB")
            colunas.append(np.asarray(imagem, dtype=np.float64))
        linhas.append(np.hstack(colunas))   # lado a lado
    return np.vstack(linhas)                # uma linha de tiles embaixo da outra


def _rgb_para_metros(rgb: np.ndarray) -> np.ndarray:
    """Decodifica o formato terrarium: elev = R*256 + G + B/256 - 32768."""
    return rgb[:, :, 0] * 256.0 + rgb[:, :, 1] + rgb[:, :, 2] / 256.0 - 32768.0


def _mosaico_metros(bbox, z: int) -> np.ndarray:
    """Junta os tiles que cobrem a bbox e recorta na área exata. Retorna metros."""
    norte, sul, oeste, leste = bbox
    fx0, fy0 = _lonlat_para_tile(oeste, norte, z)   # canto superior-esquerdo
    fx1, fy1 = _lonlat_para_tile(leste, sul, z)     # canto inferior-direito
    x0, x1 = math.floor(fx0), math.floor(fx1)
    y0, y1 = math.floor(fy0), math.floor(fy1)

    elev = _rgb_para_metros(_juntar_tiles(x0, x1, y0, y1, z))

    # Os tiles inteiros cobrem um pouco mais que a bbox: recorta o que sobra.
    topo = round((fy0 - y0) * PIXELS_POR_TILE)
    base = round((fy1 - y0) * PIXELS_POR_TILE)
    esq = round((fx0 - x0) * PIXELS_POR_TILE)
    dir_ = round((fx1 - x0) * PIXELS_POR_TILE)
    return elev[topo:base, esq:dir_]


def _remover_spikes(elev: np.ndarray, limiar_m: float = 80.0) -> np.ndarray:
    """Troca texels isolados muito diferentes da vizinhança pela mediana 3x3.

    Dados de radar (SRTM e derivados) têm "spikes": pixels absurdos, comuns
    perto de água ou nas bordas de tile. Sem isso, aparecem agulhas no relevo.
    """
    p = np.pad(elev, 1, mode="edge")
    janela = sliding_window_view(p, (3, 3)).reshape(*elev.shape, 9)
    mediana = np.median(janela, axis=-1)
    spike = np.abs(elev - mediana) > limiar_m
    return np.where(spike, mediana, elev).astype(np.float32)


def carregar_heightmap(
    resolution: int = 1024,
    bbox=BAIXADA_SANTISTA,
    zoom: int = 11,
    world_size: float = 300.0,
    exagero_vertical: float = 6.0,
    piso_metros: float = -40.0,
):
    """Baixa/prepara o DEM e devolve (alturas, unidades_por_metro).

    alturas            : (resolution, resolution) float32, em unidades de mundo,
                         0 = nível do mar atual.
    unidades_por_metro : fator para converter "mar +X m" em unidades de mundo
                         (já inclui o exagero vertical).

    exagero_vertical : a Baixada Santista tem ~50 km de largura para ~1,2 km de
        relevo (razão ~40:1). Sem exagero, a Serra do Mar vira uma lombada.
        6x deixa a escarpa visível como uma parede de montanhas — é prática
        padrão em geovisualização; DECLARAR esse valor no artigo.
    """
    elev_m = _mosaico_metros(bbox, zoom)
    for _ in range(2):   # 2ª passada pega clusters pequenos que a 1ª deixou
        elev_m = _remover_spikes(elev_m, limiar_m=60.0)

    # Abaixo de 'piso_metros' está tudo submerso de qualquer jeito: achata para
    # o oceano profundo não estourar a normalização de cor do terreno.
    elev_m = np.clip(elev_m, piso_metros, None)

    # Reamostra para resolution x resolution (PIL suporta float32 no modo 'F').
    elev_m = np.asarray(
        Image.fromarray(elev_m.astype(np.float32)).resize(
            (resolution, resolution), Image.BILINEAR
        ),
        dtype=np.float32,
    )

    # Escala horizontal real da bbox (metros), aproximada no paralelo central.
    norte, sul, oeste, leste = bbox
    lat_meio = math.radians((norte + sul) / 2.0)
    largura_m = abs(leste - oeste) * 111_320.0 * math.cos(lat_meio)
    altura_m = abs(norte - sul) * 110_540.0
    extensao_m = (largura_m + altura_m) / 2.0

    unidades_por_metro = (world_size / extensao_m) * exagero_vertical
    alturas = (elev_m * unidades_por_metro).astype(np.float32)
    return alturas, unidades_por_metro


# --- teste rápido:  python src/dem.py ----------------------------------
if __name__ == "__main__":
    alt, upm = carregar_heightmap(resolution=512)
    print(f"alturas {alt.shape}  min={alt.min():.2f}  max={alt.max():.2f} (unidades)")
    print(f"unidades por metro: {upm:.5f}  ->  mar +2 m = {2 * upm:.3f} unidades")
