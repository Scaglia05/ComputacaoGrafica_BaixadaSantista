"""
=============================================================================
 bench.py  —  Mede tempo de frame / FPS do render, com e sem LOD
=============================================================================

Roda SEM janela (contexto standalone + framebuffer 1280x720), varrendo:

  - condição : sem_lod  |  cdlod  |  cdlod_sem_morph
  - resolução do heightmap : 256, 512, 768, 1024
      (afeta MUITO a malha ingênua; no CDLOD é só o tamanho da textura)
  - câmera : 4 posições representativas (rasante, encosta, aérea, horizonte)

Para cada combinação: aquece alguns frames, mede N frames sincronizando a
GPU a cada um (ctx.finish), guarda média / mediana / p95 do tempo de frame,
e tira uma amostra de **consumo de recursos** (RAM do processo via `psutil`;
VRAM e uso de GPU via `nvidia-smi`, quando disponível — placas não-NVIDIA
ficam com essas colunas vazias no CSV, sem quebrar o benchmark).

Saídas em  bench/:
  resultados.csv
  fps_vs_resolucao.png
  tempo_por_camera.png
  triangulos_vs_tempo.png
  custo_do_morph.png
  recursos_vs_resolucao.png

Uso
---
  python src/bench.py            # varredura completa (~1-2 min)
  python src/bench.py --rapido    # subconjunto rápido (~20 s)
  python src/bench.py --saida bench/v2      # grava em outra pasta (não sobrescreve
                                            # o bench/resultados.csv usado no artigo)

  Memória ISOLADA por modo (cada modo × resolução num processo novo):
  python src/bench.py --memoria --saida bench/v2 [--resolucoes 256,1024] [--repeticoes 3]

Observação: sem V-Sync, os números são a VAZÃO da GPU (pode passar de
1000 fps nos casos leves). O que importa para o artigo é a RAZÃO entre
"com LOD" e "sem LOD", e como ela cresce com a resolução.

CUIDADO: sem --saida, o benchmark grava em bench/ e SOBRESCREVE o
resultados.csv que sustenta os números do artigo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import glm
import moderngl
import psutil

from scene import Cena

SAIDA_PADRAO = Path(__file__).resolve().parent.parent / "bench"
LARGURA, ALTURA = 1280, 720
TAMANHO_MUNDO = 300.0

FRAMES_AQUECIMENTO = 30
FRAMES_MEDIDA = 150

# Vai bem além da resolução usável para achar o "ponto de virada": onde a
# malha ingênua fica cara o bastante para o CDLOD compensar.
RESOLUCOES = [256, 512, 1024, 1536, 2048]
RESOLUCOES_RAPIDO = [256, 1024]

CEU = (0.62, 0.72, 0.84)

# (nome, lod_ligado, morph, frustum_culling). As 3 primeiras são as do artigo e
# NÃO podem mudar (os números publicados dependem delas); a 4ª é a nova.
CONDICOES = [
    ("sem_lod", False, False, False),
    ("cdlod", True, True, False),
    ("cdlod_sem_morph", True, False, False),
    ("cdlod_frustum", True, True, True),
]
CONDICOES_RAPIDO = ("sem_lod", "cdlod", "cdlod_frustum")


def cameras(altura_ref: float, s: float):
    """(nome -> (posição, alvo)) em coordenadas de mundo."""
    a = altura_ref
    return {
        "rasante":   (glm.vec3(-s * 0.15, a * 0.5, s * 0.30), glm.vec3(-s * 0.45, 0.0, -s * 0.20)),
        "encosta":   (glm.vec3(s * 0.25, a * 1.6, s * 0.35), glm.vec3(-s * 0.10, a * 0.4, -s * 0.10)),
        "aerea":     (glm.vec3(0.0, a * 4.0, s * 0.55), glm.vec3(0.0, 0.0, 0.0)),
        "horizonte": (glm.vec3(-s * 0.30, a * 0.35, s * 0.45), glm.vec3(s * 0.30, a * 0.3, -s * 0.45)),
    }


def _rss_mb() -> float:
    """Memória residente (RSS) do processo, em MB."""
    return psutil.Process().memory_info().rss / 1e6


def _rss_pico_mb() -> float:
    """Maior RSS que o processo já teve, em MB.

    O pico importa porque a malha ingênua passa por cópias temporárias grandes
    na CPU (numpy -> bytes -> GPU) que o RSS final já não mostra mais.
    """
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):                  # Windows
        return info.peak_wset / 1e6
    try:
        import resource                              # Linux / macOS
        pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return pico / (1e6 if sys.platform == "darwin" else 1e3)   # mac: bytes; Linux: KB
    except ImportError:
        return info.rss / 1e6


def _recursos():
    """Amostra pontual de consumo de recursos, no estado estável pós-medição.

    RAM: memória residente (RSS) do processo Python (psutil — multiplataforma).
    VRAM / uso de GPU: via `nvidia-smi` (só existe em GPUs NVIDIA). Se não
    houver `nvidia-smi` no PATH (outra marca de GPU, ou não instalado),
    devolve None nesses dois campos em vez de quebrar o benchmark.
    """
    vram_mb, gpu_util_pct = _vram_e_util()
    return _rss_mb(), vram_mb, gpu_util_pct


def _vram_e_util():
    """(VRAM usada na GPU INTEIRA em MB, uso de GPU em %) ou (None, None)."""
    vram_mb = None
    gpu_util_pct = None
    try:
        saida = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if saida.returncode == 0 and saida.stdout.strip():
            vram_str, util_str = saida.stdout.strip().splitlines()[0].split(",")
            vram_mb = float(vram_str.strip())
            gpu_util_pct = float(util_str.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass  # sem GPU NVIDIA / nvidia-smi indisponível: segue sem esses dados
    return vram_mb, gpu_util_pct


def medir(ctx, cena, fbo, view, proj, cam_pos, *, lod_ligado, morph, culling=False):
    stats = None
    for _ in range(FRAMES_AQUECIMENTO):
        fbo.use()
        fbo.clear(*CEU)
        stats = cena.desenhar(view, proj, cam_pos, lod_ligado=lod_ligado, morph=morph,
                              frustum_culling=culling)
    ctx.finish()

    tempos = []
    for _ in range(FRAMES_MEDIDA):
        t0 = time.perf_counter()
        fbo.use()
        fbo.clear(*CEU)
        cena.desenhar(view, proj, cam_pos, lod_ligado=lod_ligado, morph=morph,
                      frustum_culling=culling)
        ctx.finish()
        tempos.append((time.perf_counter() - t0) * 1000.0)

    tempos.sort()
    ram_mb, vram_mb, gpu_util_pct = _recursos()
    return stats, tempos, ram_mb, vram_mb, gpu_util_pct


# ---------------------------------------------------------------------------
# Memória ISOLADA por modo
# ---------------------------------------------------------------------------
# No benchmark original os 3 modos compartilhavam a mesma `Cena`, com a malha
# ingênua SEMPRE residente na GPU — por isso RAM/VRAM não diferiam entre modos.
# Aqui cada (modo, resolução) roda num PROCESSO NOVO e a `Cena` constrói só a
# malha que o modo usa. Processo novo também evita que um modo herde a memória
# que o anterior deixou para trás (o alocador do Python quase não devolve RAM
# ao sistema).
def medir_memoria(modo: str, resolucao: int) -> dict:
    """Mede UM modo, neste processo. Chamado pelo subprocesso `--memoria-um`."""
    cond = {c[0]: c for c in CONDICOES}.get(modo)
    if cond is None:
        raise ValueError(f"modo desconhecido: {modo!r} (use um de {[c[0] for c in CONDICOES]})")
    _, lod_on, morph_on, culling_on = cond

    rss_antes = _rss_mb()
    vram_antes, _ = _vram_e_util()

    ctx = moderngl.create_standalone_context()
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    fbo = ctx.simple_framebuffer((LARGURA, ALTURA))
    fbo.use()

    cena = Cena(ctx, fonte="dem", resolucao_heightmap=resolucao, tamanho_mundo=TAMANHO_MUNDO,
                verboso=False, construir_lod=lod_on, construir_ingenuo=not lod_on)
    pos, alvo = cameras(cena.altura_ref, TAMANHO_MUNDO)["rasante"]
    view = glm.lookAt(pos, alvo, glm.vec3(0.0, 1.0, 0.0))
    proj = glm.perspective(glm.radians(60.0), LARGURA / ALTURA, 0.05, 3000.0)

    # Desenha alguns quadros para que tudo (buffers, texturas, shaders) esteja
    # de fato residente antes de medir.
    stats = None
    for _ in range(FRAMES_AQUECIMENTO):
        fbo.use()
        fbo.clear(*CEU)
        stats = cena.desenhar(view, proj, pos, lod_ligado=lod_on, morph=morph_on,
                              frustum_culling=culling_on)
    ctx.finish()

    rss_depois = _rss_mb()
    rss_pico = max(_rss_pico_mb(), rss_depois)
    vram_depois, _ = _vram_e_util()
    b = cena.bytes_alocados()

    def mb(x):
        return round(x / 1e6, 6)

    def mb_ou_none(x):
        return None if x is None else round(float(x), 3)

    return {
        "modo": modo,
        "resolucao": resolucao,
        "pid": os.getpid(),
        "gpu": ctx.info["GL_RENDERER"],
        "triangulos": stats.triangulos,
        "bytes_app_mb": mb(b["total"]),
        "bytes_textura_mb": mb(b["textura_altura"]),
        "bytes_malha_mb": mb(b["malha_lod"] + b["malha_ingenua"]),
        "rss_antes_mb": round(rss_antes, 3),
        "rss_depois_mb": round(rss_depois, 3),
        "rss_pico_mb": round(rss_pico, 3),
        "vram_antes_mb": mb_ou_none(vram_antes),
        "vram_depois_mb": mb_ou_none(vram_depois),
    }


def memoria_isolada(modos, resolucoes, repeticoes: int = 1) -> list[dict]:
    """Roda `medir_memoria` para cada (resolução, repetição, modo), cada um num processo novo."""
    validos = [c[0] for c in CONDICOES]
    for modo in modos:
        if modo not in validos:
            raise ValueError(f"modo desconhecido: {modo!r} (use um de {validos})")

    resultados: list[dict] = []
    for res in resolucoes:
        for rep in range(repeticoes):
            for modo in modos:
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--memoria-um", modo, str(res)],
                    capture_output=True, text=True, timeout=600,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"medição de memória falhou ({modo}, {res}):\n{proc.stderr}")
                linha = json.loads(proc.stdout.strip().splitlines()[-1])
                linha["repeticao"] = rep
                resultados.append(linha)
                print(f"  {modo:16s} {res:5d}² rep {rep}: {linha['bytes_app_mb']:8.2f} MB alocados | "
                      f"RSS {linha['rss_depois_mb']:6.0f} MB (pico {linha['rss_pico_mb']:6.0f})")
    return resultados


def _executar_memoria(args) -> None:
    resolucoes = [int(r) for r in args.resolucoes.split(",")] if args.resolucoes else RESOLUCOES
    modos = [c[0] for c in CONDICOES]
    saida = args.saida
    saida.mkdir(parents=True, exist_ok=True)

    print(f"Memória isolada: {len(modos)} modos x {len(resolucoes)} resoluções x "
          f"{args.repeticoes} repetições, cada um num processo novo")
    linhas = memoria_isolada(modos, resolucoes, args.repeticoes)

    caminho = saida / "memoria.csv"
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"\nCSV salvo em {caminho}")
    _grafico_memoria(linhas, saida)
    print(f"Gráfico salvo em {saida / 'memoria_isolada.png'}")


def _grafico_memoria(linhas, saida: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cores = {"sem_lod": "#c1443c", "cdlod": "#2f7d4f", "cdlod_sem_morph": "#4a6fb0",
             "cdlod_frustum": "#8a4fb0"}
    fig, eixos = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, campo, titulo in (
        (eixos[0], "bytes_app_mb", "Memória alocada pela aplicação na GPU (MB)"),
        (eixos[1], "rss_pico_mb", "Pico de RAM do processo (MB)"),
    ):
        for modo in dict.fromkeys(r["modo"] for r in linhas):
            porres: dict[int, list[float]] = {}
            for r in linhas:
                if r["modo"] == modo:
                    porres.setdefault(r["resolucao"], []).append(r[campo])
            serie = {res: statistics.fmean(v) for res, v in sorted(porres.items())}
            ax.plot(list(serie), list(serie.values()), "o-", color=cores.get(modo), label=modo)
        ax.set_xlabel("resolução do heightmap (lado)")
        ax.set_title(titulo)
        ax.grid(alpha=0.3)
        ax.legend()
    fig.suptitle("Cada modo medido em processo separado, só com a malha que usa")
    fig.tight_layout()
    fig.savefig(saida / "memoria_isolada.png", dpi=130)
    plt.close(fig)


def _argumentos():
    p = argparse.ArgumentParser(description="Benchmark do CDLOD (tempo de frame e memória).")
    p.add_argument("--rapido", action="store_true", help="subconjunto rápido")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO,
                   help="pasta de saída (padrão: bench/, que contém os dados do artigo)")
    p.add_argument("--memoria", action="store_true",
                   help="mede RAM/VRAM de cada modo em processos separados")
    p.add_argument("--memoria-um", nargs=2, metavar=("MODO", "RES"), help=argparse.SUPPRESS)
    p.add_argument("--resolucoes", default=None, help="lista separada por vírgula, ex.: 256,1024")
    p.add_argument("--repeticoes", type=int, default=3, help="repetições da medição de memória")
    return p.parse_args()


def main() -> None:
    args = _argumentos()
    if args.memoria_um:                      # modo interno: UM modo, saída em JSON
        print(json.dumps(medir_memoria(args.memoria_um[0], int(args.memoria_um[1]))))
        return
    if args.memoria:
        _executar_memoria(args)
        return

    rapido = args.rapido
    saida = args.saida
    resolucoes = [int(r) for r in args.resolucoes.split(",")] if args.resolucoes else (
        RESOLUCOES_RAPIDO if rapido else RESOLUCOES)
    condicoes = [c for c in CONDICOES if not rapido or c[0] in CONDICOES_RAPIDO]

    saida.mkdir(parents=True, exist_ok=True)

    ctx = moderngl.create_standalone_context()
    ctx.gc_mode = "auto"
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    fbo = ctx.simple_framebuffer((LARGURA, ALTURA))
    fbo.use()
    gpu = ctx.info["GL_RENDERER"]
    print("GPU:", gpu)
    proj = glm.perspective(glm.radians(60.0), LARGURA / ALTURA, 0.05, 3000.0)

    linhas: list[dict] = []
    for res in resolucoes:
        print(f"\n=== heightmap {res} x {res} ===")
        cena = Cena(ctx, fonte="dem", resolucao_heightmap=res,
                    tamanho_mundo=TAMANHO_MUNDO, verboso=False)
        cams = cameras(cena.altura_ref, TAMANHO_MUNDO)

        for nome_cam, (pos, alvo) in cams.items():
            view = glm.lookAt(pos, alvo, glm.vec3(0.0, 1.0, 0.0))
            for nome_cond, lod_on, morph_on, culling_on in condicoes:
                stats, tempos, ram_mb, vram_mb, gpu_util = medir(
                    ctx, cena, fbo, view, proj, pos,
                    lod_ligado=lod_on, morph=morph_on, culling=culling_on,
                )
                media = statistics.fmean(tempos)
                linha = {
                    "resolucao": res,
                    "condicao": nome_cond,
                    "camera": nome_cam,
                    "blocos": stats.blocos,
                    "draw_calls": stats.draw_calls,
                    "triangulos": stats.triangulos,
                    "ms_media": round(media, 3),
                    "ms_p50": round(tempos[len(tempos) // 2], 3),
                    "ms_p95": round(tempos[min(len(tempos) - 1, int(len(tempos) * 0.95))], 3),
                    "fps": round(1000.0 / media, 1),
                    "ram_mb": round(ram_mb, 1),
                    "vram_mb": round(vram_mb, 1) if vram_mb is not None else "",
                    "gpu_util_pct": gpu_util if gpu_util is not None else "",
                    "nos_podados": stats.nos_podados,
                    "gpu": gpu,
                }
                linhas.append(linha)
                extra = f" | {vram_mb:.0f} MB VRAM" if vram_mb is not None else ""
                print(f"  {nome_cam:9s} {nome_cond:16s} "
                      f"{stats.triangulos / 1e6:6.2f} M tri | "
                      f"{media:8.3f} ms | {linha['fps']:8.1f} fps | "
                      f"{ram_mb:6.0f} MB RAM{extra}")
        del cena

    csv_path = saida / "resultados.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        writer.writeheader()
        writer.writerows(linhas)
    print(f"\nCSV salvo em {csv_path}")

    _gerar_graficos(linhas, rapido, saida)
    print(f"Graficos salvos em {saida}")


# ---------------------------------------------------------------------------
def _media_por(linhas, chave_cond, campo, filtro=lambda r: True):
    """Média de 'campo' agrupada por resolução, para uma condição."""
    porres: dict[int, list[float]] = {}
    for r in linhas:
        if r["condicao"] == chave_cond and filtro(r):
            porres.setdefault(r["resolucao"], []).append(r[campo])
    return {res: statistics.fmean(v) for res, v in sorted(porres.items())}


def _gerar_graficos(linhas, rapido: bool, saida: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    condicoes = sorted({r["condicao"] for r in linhas})
    cores = {"sem_lod": "#c1443c", "cdlod": "#2f7d4f", "cdlod_sem_morph": "#4a6fb0",
             "cdlod_frustum": "#8a4fb0"}
    res_max = max(r["resolucao"] for r in linhas)

    # --- 1. FPS medio x resolucao -------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for cond in condicoes:
        serie = _media_por(linhas, cond, "fps")
        ax.plot(list(serie), list(serie.values()), "o-", color=cores.get(cond), label=cond)
    ax.set_xlabel("resolução do heightmap (lado)")
    ax.set_ylabel("FPS médio (4 câmeras)")
    ax.set_title("FPS x resolução — CDLOD mantém o custo baixo")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(saida / "fps_vs_resolucao.png", dpi=130)
    plt.close(fig)

    # --- 2. tempo de frame por camera (resolucao maxima) -----------
    cams = sorted({r["camera"] for r in linhas})
    fig, ax = plt.subplots(figsize=(8, 4.2))
    largura = 0.8 / len(condicoes)
    for i, cond in enumerate(condicoes):
        vals = []
        for cam in cams:
            m = [r["ms_media"] for r in linhas
                 if r["condicao"] == cond and r["camera"] == cam and r["resolucao"] == res_max]
            vals.append(m[0] if m else 0.0)
        xs = [j + i * largura for j in range(len(cams))]
        ax.bar(xs, vals, largura, color=cores.get(cond), label=cond)
    ax.set_xticks([j + largura * (len(condicoes) - 1) / 2 for j in range(len(cams))])
    ax.set_xticklabels(cams)
    ax.set_ylabel("tempo de frame (ms)")
    ax.set_title(f"Tempo de frame por câmera — heightmap {res_max}")
    ax.grid(alpha=0.3, axis="y")
    ax.legend()
    fig.tight_layout()
    fig.savefig(saida / "tempo_por_camera.png", dpi=130)
    plt.close(fig)

    # --- 3. triangulos x tempo de frame (dispersao) ---------------
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for cond in condicoes:
        pts = [(r["triangulos"] / 1e6, r["ms_media"]) for r in linhas if r["condicao"] == cond]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, color=cores.get(cond), label=cond, alpha=0.8)
    ax.set_xlabel("triângulos por frame (milhões)")
    ax.set_ylabel("tempo de frame (ms)")
    ax.set_title("Custo x carga geométrica")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(saida / "triangulos_vs_tempo.png", dpi=130)
    plt.close(fig)

    # --- 4b. VRAM/RAM x resolucao (perfilamento de recursos) -------
    # Nota: as 3 condições compartilham a MESMA `Cena` (mesma textura de
    # heightmap + os DOIS VAOs, o pequeno do CDLOD e a malha ingênua, sempre
    # residentes juntos) — por isso as 3 curvas praticamente coincidem. Este
    # gráfico mostra o crescimento de VRAM com a RESOLUÇÃO DO DEM, não uma
    # comparação de memória entre "com LOD" x "sem LOD" (para isolar isso
    # seria preciso montar cenas separadas, sem a malha ingênua residente).
    tem_vram = any(isinstance(r["vram_mb"], (int, float)) for r in linhas)
    if tem_vram:
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for cond in condicoes:
            porres: dict[int, list[float]] = {}
            for r in linhas:
                if r["condicao"] == cond and isinstance(r["vram_mb"], (int, float)):
                    porres.setdefault(r["resolucao"], []).append(r["vram_mb"])
            serie = {res: statistics.fmean(v) for res, v in sorted(porres.items())}
            if serie:
                ax.plot(list(serie), list(serie.values()), "o-", color=cores.get(cond), label=cond)
        ax.set_xlabel("resolução do heightmap (lado)")
        ax.set_ylabel("VRAM usada (MB, GPU inteira)")
        ax.set_title("VRAM x resolução do DEM (mesma cena p/ todas as condições)")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(saida / "recursos_vs_resolucao.png", dpi=130)
        plt.close(fig)

    # --- 5. custo do morphing (so no modo completo) --------------
    if not rapido and "cdlod_sem_morph" in condicoes:
        fig, ax = plt.subplots(figsize=(8, 4.2))
        for i, cond in enumerate(("cdlod_sem_morph", "cdlod")):
            vals = []
            for cam in cams:
                m = [r["ms_media"] for r in linhas
                     if r["condicao"] == cond and r["camera"] == cam and r["resolucao"] == res_max]
                vals.append(m[0] if m else 0.0)
            xs = [j + i * 0.4 for j in range(len(cams))]
            ax.bar(xs, vals, 0.4, color=cores.get(cond), label=cond)
        ax.set_xticks([j + 0.2 for j in range(len(cams))])
        ax.set_xticklabels(cams)
        ax.set_ylabel("tempo de frame (ms)")
        ax.set_title(f"Custo do morphing — heightmap {res_max}")
        ax.grid(alpha=0.3, axis="y")
        ax.legend()
        fig.tight_layout()
        fig.savefig(saida / "custo_do_morph.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
