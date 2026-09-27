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

Observação: sem V-Sync, os números são a VAZÃO da GPU (pode passar de
1000 fps nos casos leves). O que importa para o artigo é a RAZÃO entre
"com LOD" e "sem LOD", e como ela cresce com a resolução.
"""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from pathlib import Path

import glm
import moderngl
import psutil

from scene import Cena

SAIDA = Path(__file__).resolve().parent.parent / "bench"
LARGURA, ALTURA = 1280, 720
TAMANHO_MUNDO = 300.0

FRAMES_AQUECIMENTO = 30
FRAMES_MEDIDA = 150

# Vai bem além da resolução usável para achar o "ponto de virada": onde a
# malha ingênua fica cara o bastante para o CDLOD compensar.
RESOLUCOES = [256, 512, 1024, 1536, 2048]
RESOLUCOES_RAPIDO = [256, 1024]

CEU = (0.62, 0.72, 0.84)


def cameras(altura_ref: float, s: float):
    """(nome -> (posição, alvo)) em coordenadas de mundo."""
    a = altura_ref
    return {
        "rasante":   (glm.vec3(-s * 0.15, a * 0.5, s * 0.30), glm.vec3(-s * 0.45, 0.0, -s * 0.20)),
        "encosta":   (glm.vec3(s * 0.25, a * 1.6, s * 0.35), glm.vec3(-s * 0.10, a * 0.4, -s * 0.10)),
        "aerea":     (glm.vec3(0.0, a * 4.0, s * 0.55), glm.vec3(0.0, 0.0, 0.0)),
        "horizonte": (glm.vec3(-s * 0.30, a * 0.35, s * 0.45), glm.vec3(s * 0.30, a * 0.3, -s * 0.45)),
    }


def _recursos():
    """Amostra pontual de consumo de recursos, no estado estável pós-medição.

    RAM: memória residente (RSS) do processo Python (psutil — multiplataforma).
    VRAM / uso de GPU: via `nvidia-smi` (só existe em GPUs NVIDIA). Se não
    houver `nvidia-smi` no PATH (outra marca de GPU, ou não instalado),
    devolve None nesses dois campos em vez de quebrar o benchmark.
    """
    ram_mb = psutil.Process().memory_info().rss / 1e6
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
    return ram_mb, vram_mb, gpu_util_pct


def medir(ctx, cena, fbo, view, proj, cam_pos, *, lod_ligado, morph):
    stats = None
    for _ in range(FRAMES_AQUECIMENTO):
        fbo.use()
        fbo.clear(*CEU)
        stats = cena.desenhar(view, proj, cam_pos, lod_ligado=lod_ligado, morph=morph)
    ctx.finish()

    tempos = []
    for _ in range(FRAMES_MEDIDA):
        t0 = time.perf_counter()
        fbo.use()
        fbo.clear(*CEU)
        cena.desenhar(view, proj, cam_pos, lod_ligado=lod_ligado, morph=morph)
        ctx.finish()
        tempos.append((time.perf_counter() - t0) * 1000.0)

    tempos.sort()
    ram_mb, vram_mb, gpu_util_pct = _recursos()
    return stats, tempos, ram_mb, vram_mb, gpu_util_pct


def main() -> None:
    rapido = "--rapido" in sys.argv
    resolucoes = RESOLUCOES_RAPIDO if rapido else RESOLUCOES
    condicoes = [("sem_lod", False, False), ("cdlod", True, True)]
    if not rapido:
        condicoes.append(("cdlod_sem_morph", True, False))

    SAIDA.mkdir(exist_ok=True)

    ctx = moderngl.create_standalone_context()
    ctx.gc_mode = "auto"
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    fbo = ctx.simple_framebuffer((LARGURA, ALTURA))
    fbo.use()
    print("GPU:", ctx.info["GL_RENDERER"])
    proj = glm.perspective(glm.radians(60.0), LARGURA / ALTURA, 0.05, 3000.0)

    linhas: list[dict] = []
    for res in resolucoes:
        print(f"\n=== heightmap {res} x {res} ===")
        cena = Cena(ctx, fonte="dem", resolucao_heightmap=res,
                    tamanho_mundo=TAMANHO_MUNDO, verboso=False)
        cams = cameras(cena.altura_ref, TAMANHO_MUNDO)

        for nome_cam, (pos, alvo) in cams.items():
            view = glm.lookAt(pos, alvo, glm.vec3(0.0, 1.0, 0.0))
            for nome_cond, lod_on, morph_on in condicoes:
                stats, tempos, ram_mb, vram_mb, gpu_util = medir(
                    ctx, cena, fbo, view, proj, pos, lod_ligado=lod_on, morph=morph_on
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
                }
                linhas.append(linha)
                extra = f" | {vram_mb:.0f} MB VRAM" if vram_mb is not None else ""
                print(f"  {nome_cam:9s} {nome_cond:16s} "
                      f"{stats.triangulos / 1e6:6.2f} M tri | "
                      f"{media:8.3f} ms | {linha['fps']:8.1f} fps | "
                      f"{ram_mb:6.0f} MB RAM{extra}")
        del cena

    csv_path = SAIDA / "resultados.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        writer.writeheader()
        writer.writerows(linhas)
    print(f"\nCSV salvo em {csv_path}")

    _gerar_graficos(linhas, rapido)
    print(f"Graficos salvos em {SAIDA}")


# ---------------------------------------------------------------------------
def _media_por(linhas, chave_cond, campo, filtro=lambda r: True):
    """Média de 'campo' agrupada por resolução, para uma condição."""
    porres: dict[int, list[float]] = {}
    for r in linhas:
        if r["condicao"] == chave_cond and filtro(r):
            porres.setdefault(r["resolucao"], []).append(r[campo])
    return {res: statistics.fmean(v) for res, v in sorted(porres.items())}


def _gerar_graficos(linhas, rapido: bool) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    condicoes = sorted({r["condicao"] for r in linhas})
    cores = {"sem_lod": "#c1443c", "cdlod": "#2f7d4f", "cdlod_sem_morph": "#4a6fb0"}
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
    fig.savefig(SAIDA / "fps_vs_resolucao.png", dpi=130)
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
    fig.savefig(SAIDA / "tempo_por_camera.png", dpi=130)
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
    fig.savefig(SAIDA / "triangulos_vs_tempo.png", dpi=130)
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
        fig.savefig(SAIDA / "recursos_vs_resolucao.png", dpi=130)
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
        fig.savefig(SAIDA / "custo_do_morph.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
