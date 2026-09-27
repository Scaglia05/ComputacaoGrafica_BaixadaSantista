"""
=============================================================================
 main.py  —  Visualizador interativo (terreno + LOD + água)
=============================================================================

A cena e o render moram em scene.py (classe `Cena`). Aqui ficam só a janela,
o input e o laço principal.

  dem.py / heightmap.py -> altura do terreno (DEM real da Baixada Santista ou ruído)
  lod.py                -> quadtree + seleção de blocos por distância (CDLOD)
  water.py + shaders    -> plano de água com ondas de Gerstner
  camera.py             -> câmera livre (matrizes view / projection)

Controles
---------
  W A S D          mover na horizontal
  Espaço / Ctrl    subir / descer
  Shift            mover mais rápido
  Mouse            olhar ao redor
  R                volta pro ponto de partida (se você se perder)
  , / .            baixar / subir o nível do mar (contínuo)
  1 2 3 4          cenários de nível do mar (0 / +0,5 / +1 / +2 m)
  5 6 7            cenários extremos p/ demonstração (+5 / +10 / +20 m)
  L                liga/desliga o LOD (CDLOD  x  malha ingênua)
  M                liga/desliga o morphing (com OFF, aparecem as cracks)
  K                debug: pinta cada bloco do quadtree por profundidade
  Z                alterna wireframe (ver a malha de triângulos)
  H                legenda de comandos: nenhuma -> básica -> completa -> nenhuma
  P                alterna o canto inferior-direito: minimapa <-> foto real
  I                mostra de novo a tela de boas-vindas
  ESC              sair

Uma tela de boas-vindas explica o objetivo ao abrir (some ao andar). O
nível do mar, o modo de LOD/morphing e o **tempo de render do quadro**
aparecem sempre na tela (canto superior-direito) — o tempo de render é o
número que muda de verdade ao apertar `L` (o FPS da tela fica travado em
~60 pelo V-Sync e esconde a diferença). Uma bússola (inferior-esquerda) e
um minimapa com a posição da câmera (inferior-direito) ajudam a não se
perder no terreno.

Como rodar
----------
  pip install -r requirements.txt
  python src/main.py
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import glfw
import glm
import moderngl
from PIL import Image

from camera import Camera
from hud import Hud
from scene import Cena


FONTE_TERRENO = "dem"        # "dem" = Baixada Santista (DEM real) | "procedural" = ruído
LARGURA, ALTURA = 1280, 720

# Cenários de subida do nível do mar, em METROS (tecla -> metros).
# 1-4: alinhados ao objetivo do projeto (faixas usuais de projeção científica).
# 5-7: cenários extremos, só para demonstração — deixam a inundação óbvia
#      mesmo de longe (o efeito real de +0,5/+1/+2 m é sutil contra ~1200 m
#      de relevo). Ajuste contínuo com ',' / '.' vai além disso, se precisar.
CENARIOS_MAR = {
    1: 0.0, 2: 0.5, 3: 1.0, 4: 2.0,      # cenários científicos
    5: 5.0, 6: 10.0, 7: 20.0,            # cenários extremos (demonstração)
}

FOTO_REFERENCIA = Path(__file__).parent / "data" / "referencia_santos.jpg"

# Nível 1 (básico): só o que um leigo precisa pra explorar a inundação.
COMANDOS_BASICOS = [
    ("W A S D", "mover na horizontal"),
    ("Espaco / Ctrl", "subir / descer"),
    ("Shift", "mais rapido"),
    ("Mouse", "olhar ao redor"),
    ("R", "voltar ao inicio (se se perder)"),
    (", / .", "nivel do mar (continuo)"),
    ("1 2 3 4", "mar: 0 / +0,5 / +1 / +2 m"),
    ("5 6 7", "mar extremo: +5 / +10 / +20 m"),
    ("H", "mais comandos / esconder"),
    ("P", "minimapa <-> foto de referencia"),
    ("I", "tela de boas-vindas"),
    ("ESC", "sair"),
]

# Nível 2 (completo): os comandos técnicos, com LOD/morphing explicados em
# 1 linha cada — pra quem quer entender a engine, não só ver a inundação.
COMANDOS_AVANCADOS = COMANDOS_BASICOS + [
    ("L", "LOD/CDLOD: desenha so o detalhe visivel dali"),
    ("M", "suavizacao (morphing): remove frestas entre blocos"),
    ("K", "debug: colore os blocos do LOD"),
    ("Z", "wireframe: ve a malha de triangulos"),
]


def gerar_minimapa(ctx: moderngl.Context, cena: Cena, tamanho_px: int = 220):
    """Renderiza a cena 1x, de cima, pra usar como fundo do minimapa.

    Faz um desenho normal da `Cena` (mesmo shader, mesmo terreno) numa
    câmera olhando reto pra baixo, com "up" apontando pro -Z do mundo (ou
    seja, Norte fica sempre pra cima na imagem — convenção de mapa).
    Roda 1x, antes do laço principal; não tem custo por frame.
    """
    fbo = ctx.simple_framebuffer((tamanho_px, tamanho_px))
    fbo.use()
    fbo.clear(0.62, 0.72, 0.84)

    altura_cam = cena.tamanho_mundo * 1.7
    meia_largura = cena.tamanho_mundo * 0.62   # extensão coberta (c/ margem de oceano)
    fov_graus = 2.0 * math.degrees(math.atan(meia_largura / altura_cam))

    pos = glm.vec3(0.0, altura_cam, 0.0)
    view = glm.lookAt(pos, glm.vec3(0.0, 0.0, 0.0), glm.vec3(0.0, 0.0, -1.0))
    proj = glm.perspective(glm.radians(fov_graus), 1.0, 0.1, altura_cam * 3.0)
    cena.desenhar(view, proj, pos, nivel_mar=0.0, tempo=0.0)

    dados = fbo.read(components=3)
    imagem = Image.frombytes("RGB", (tamanho_px, tamanho_px), dados).transpose(Image.FLIP_TOP_BOTTOM)
    fbo.release()

    tela = getattr(ctx, "screen", None)
    if tela is not None:
        tela.use()
    return imagem, meia_largura


def main() -> None:
    # --- 1. Janela + contexto -----------------------------------------
    if not glfw.init():
        raise RuntimeError("Não foi possível inicializar o GLFW")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)

    titulo = "Baixada Santista (DEM)" if FONTE_TERRENO == "dem" else "Terreno procedural"
    window = glfw.create_window(LARGURA, ALTURA, titulo, None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Não foi possível criar a janela GLFW")

    glfw.make_context_current(window)
    glfw.swap_interval(1)  # vsync

    ctx = moderngl.create_context()
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    # --- 2. A cena (todo o setup de GPU) ----------------------------
    cena = Cena(ctx, fonte=FONTE_TERRENO)
    print(f"terreno pronto | altura_ref={cena.altura_ref:.1f} u | "
          f"malha ingenua ~{cena.triangulos_ingenuo // 1000}k triangulos")

    print("Gerando minimapa (1 render de topo, fora do laço principal)...")
    fundo_minimapa, meia_largura_minimapa = gerar_minimapa(ctx, cena)

    hud = Hud(
        ctx, COMANDOS_BASICOS, COMANDOS_AVANCADOS,
        foto=FOTO_REFERENCIA,
        legenda_foto="Baia de Santos (ref.) - foto Emilio Pechini / CC BY 2.0",
        minimapa_fundo=fundo_minimapa,
        minimapa_meia_largura=meia_largura_minimapa,
    )
    hud.atualizar_viewport(LARGURA, ALTURA)

    # --- 3. Câmera + estado de input ------------------------------
    pos_inicial = (0.0, cena.altura_ref + 40.0, cena.tamanho_mundo * 0.45)
    cam = Camera(position=pos_inicial)

    glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)
    estado = {
        "primeiro_mouse": True,
        "ultimo_x": LARGURA / 2,
        "ultimo_y": ALTURA / 2,
        "aspect": LARGURA / ALTURA,
        "wireframe": False, "z_antes": False,
        "nivel_mar": 0.0,                 # em UNIDADES DE MUNDO
        "lod_ligado": True, "l_antes": False,
        "debug_lod": False, "k_antes": False,
        "morph": True, "m_antes": False,
        "nivel_ajuda": 1, "h_antes": False,      # 0=oculta 1=basica 2=completa
        "mostrar_foto": False, "p_antes": False,
        "mostrar_boasvindas": True, "i_antes": False,
        "r_antes": False,
    }

    def ajustar_nivel_mar(unidades: float) -> None:
        unidades = max(-cena.altura_ref, min(cena.altura_ref, unidades))
        if abs(unidades - estado["nivel_mar"]) > 1e-5:
            estado["nivel_mar"] = unidades
            print(f"nivel do mar: {unidades / cena.unidades_por_metro:+.2f} m")

    taxa_mar = 0.8 * cena.unidades_por_metro   # ajuste contínuo ~ 0,8 m/s

    def on_resize(_win, w, h):
        h = max(h, 1)
        ctx.viewport = (0, 0, w, h)
        estado["aspect"] = w / h
        hud.atualizar_viewport(w, h)

    def on_mouse(_win, xpos, ypos):
        if estado["primeiro_mouse"]:
            estado["ultimo_x"], estado["ultimo_y"] = xpos, ypos
            estado["primeiro_mouse"] = False
            return
        dx = xpos - estado["ultimo_x"]
        dy = estado["ultimo_y"] - ypos   # invertido: para cima = pitch positivo
        estado["ultimo_x"], estado["ultimo_y"] = xpos, ypos
        cam.process_mouse(dx, dy)

    glfw.set_framebuffer_size_callback(window, on_resize)
    glfw.set_cursor_pos_callback(window, on_mouse)

    def alterna(nome_flag: str, nome_borda: str, key: int, msg=None):
        """Vira uma flag booleana só na transição solto -> pressionado."""
        agora = glfw.get_key(window, key) == glfw.PRESS
        if agora and not estado[nome_borda]:
            estado[nome_flag] = not estado[nome_flag]
            if msg:
                print(msg, "ligado" if estado[nome_flag] else "desligado")
        estado[nome_borda] = agora

    # --- 4. Render loop ------------------------------------------
    t_inicio = time.perf_counter()
    t_anterior = t_inicio

    while not glfw.window_should_close(window):
        agora = time.perf_counter()
        dt = agora - t_anterior
        t_anterior = agora
        tempo = agora - t_inicio

        glfw.poll_events()

        if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
            glfw.set_window_should_close(window, True)

        turbo = glfw.get_key(window, glfw.KEY_LEFT_SHIFT) == glfw.PRESS
        cam.speed = 120.0 if turbo else 40.0
        moveu = False
        if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
            cam.process_keyboard("FORWARD", dt); moveu = True
        if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
            cam.process_keyboard("BACKWARD", dt); moveu = True
        if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
            cam.process_keyboard("LEFT", dt); moveu = True
        if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
            cam.process_keyboard("RIGHT", dt); moveu = True
        if glfw.get_key(window, glfw.KEY_SPACE) == glfw.PRESS:
            cam.process_keyboard("UP", dt); moveu = True
        if glfw.get_key(window, glfw.KEY_LEFT_CONTROL) == glfw.PRESS:
            cam.process_keyboard("DOWN", dt); moveu = True
        if moveu:
            estado["mostrar_boasvindas"] = False   # some ao começar a explorar

        # R: resgata quem se perdeu, voltando pro ponto de partida.
        r_agora = glfw.get_key(window, glfw.KEY_R) == glfw.PRESS
        if r_agora and not estado["r_antes"]:
            cam.resetar(pos_inicial)
        estado["r_antes"] = r_agora

        if glfw.get_key(window, glfw.KEY_COMMA) == glfw.PRESS:
            ajustar_nivel_mar(estado["nivel_mar"] - taxa_mar * dt)
        if glfw.get_key(window, glfw.KEY_PERIOD) == glfw.PRESS:
            ajustar_nivel_mar(estado["nivel_mar"] + taxa_mar * dt)
        for tecla, metros in CENARIOS_MAR.items():
            if glfw.get_key(window, getattr(glfw, f"KEY_{tecla}")) == glfw.PRESS:
                ajustar_nivel_mar(metros * cena.unidades_por_metro)

        alterna("wireframe", "z_antes", glfw.KEY_Z)
        alterna("lod_ligado", "l_antes", glfw.KEY_L, "LOD:")
        alterna("debug_lod", "k_antes", glfw.KEY_K)
        alterna("morph", "m_antes", glfw.KEY_M, "morphing:")
        alterna("mostrar_foto", "p_antes", glfw.KEY_P)
        alterna("mostrar_boasvindas", "i_antes", glfw.KEY_I)
        ctx.wireframe = estado["wireframe"]

        # H cicla a legenda: oculta -> básica -> completa -> oculta ...
        h_agora = glfw.get_key(window, glfw.KEY_H) == glfw.PRESS
        if h_agora and not estado["h_antes"]:
            estado["nivel_ajuda"] = (estado["nivel_ajuda"] + 1) % 3
        estado["h_antes"] = h_agora

        view = cam.get_view_matrix()
        proj = cam.get_projection_matrix(estado["aspect"])

        ctx.clear(0.62, 0.72, 0.84)
        # Mede o tempo de render de verdade (igual ao bench.py: sincroniza a
        # GPU com ctx.finish()) — é esse número, não o FPS da tela (travado
        # em ~60 pelo V-Sync), que muda quando se aperta L.
        t_render0 = time.perf_counter()
        cena.desenhar(
            view, proj, cam.position,
            nivel_mar=estado["nivel_mar"], tempo=tempo,
            lod_ligado=estado["lod_ligado"], morph=estado["morph"],
            debug_lod=estado["debug_lod"],
        )
        ctx.finish()
        tempo_render_ms = (time.perf_counter() - t_render0) * 1000.0

        bearing = cam.bearing_graus()
        hud.atualizar_status(
            estado["nivel_mar"] / cena.unidades_por_metro,
            estado["lod_ligado"], estado["morph"], tempo_render_ms,
        )
        hud.atualizar_bussola(bearing)
        hud.atualizar_minimapa(cam.position.x, cam.position.z, bearing)
        hud.desenhar(estado["nivel_ajuda"], estado["mostrar_foto"], estado["mostrar_boasvindas"])
        glfw.swap_buffers(window)

    glfw.terminate()


if __name__ == "__main__":
    main()
