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
  TAB              solta / prende o mouse (solto: dá para usar o outro monitor)
  F11              tela cheia <-> janela (no monitor onde a janela está)
  , / .            baixar / subir o nível do mar (contínuo)
  1 2 3 4          cenários de nível do mar (0 / +0,5 / +1 / +2 m)
  5 6 7            cenários extremos p/ demonstração (+5 / +10 / +20 m)
  L                liga/desliga o LOD (CDLOD  x  malha ingênua)
  M                liga/desliga o morphing (com OFF, aparecem as cracks)
  C                liga/desliga o frustum culling (não desenha o que está fora da tela)
  K               debug: pinta cada bloco do quadtree por profundidade
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
    ("C", "culling: nao desenha blocos fora da tela"),
    ("K", "debug: colore os blocos do LOD"),
    ("Z", "wireframe: ve a malha de triangulos"),
    ("Tab", "solta / prende o mouse (outro monitor)"),
    ("F11", "tela cheia <-> janela"),
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


class Tecla:
    """Detecta o INSTANTE em que uma tecla é apertada (e não o tempo todo em que ela está segura)."""

    def __init__(self, codigo: int):
        self.codigo = codigo
        self._estava_apertada = False

    def apertou(self, janela) -> bool:
        apertada = glfw.get_key(janela, self.codigo) == glfw.PRESS
        acabou_de_apertar = apertada and not self._estava_apertada
        self._estava_apertada = apertada
        return acabou_de_apertar


class Interruptor(Tecla):
    """Uma tecla que liga/desliga uma opção a cada aperto (ex.: L liga/desliga o LOD)."""

    def __init__(self, codigo: int, ligado: bool, mensagem: str | None = None):
        super().__init__(codigo)
        self.ligado = ligado
        self.mensagem = mensagem      # se houver, é impressa no terminal a cada troca

    def atualizar(self, janela) -> None:
        if self.apertou(janela):
            self.ligado = not self.ligado
            if self.mensagem:
                print(self.mensagem, "ligado" if self.ligado else "desligado")


def apertada(janela, codigo: int) -> bool:
    """A tecla está sendo segurada neste momento?"""
    return glfw.get_key(janela, codigo) == glfw.PRESS


# Tecla -> direção da câmera (nomes que a `Camera.process_keyboard` entende).
MOVIMENTOS = (
    (glfw.KEY_W, "FORWARD"), (glfw.KEY_S, "BACKWARD"),
    (glfw.KEY_A, "LEFT"), (glfw.KEY_D, "RIGHT"),
    (glfw.KEY_SPACE, "UP"), (glfw.KEY_LEFT_CONTROL, "DOWN"),
)


def criar_janela_e_contexto():
    """Abre a janela GLFW (OpenGL 3.3 core) e devolve (janela, contexto moderngl)."""
    if not glfw.init():
        raise RuntimeError("Não foi possível inicializar o GLFW")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)

    titulo = "Baixada Santista (DEM)" if FONTE_TERRENO == "dem" else "Terreno procedural"
    janela = glfw.create_window(LARGURA, ALTURA, titulo, None, None)
    if not janela:
        glfw.terminate()
        raise RuntimeError("Não foi possível criar a janela GLFW")

    glfw.make_context_current(janela)
    glfw.swap_interval(1)  # vsync

    ctx = moderngl.create_context()
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    return janela, ctx


def monitor_da_janela(janela):
    """Devolve o monitor onde está a maior parte da janela (serve p/ vários monitores)."""
    x, y = glfw.get_window_pos(janela)
    largura, altura = glfw.get_window_size(janela)
    melhor, melhor_area = glfw.get_primary_monitor(), -1
    for monitor in glfw.get_monitors():
        mx, my = glfw.get_monitor_pos(monitor)
        modo = glfw.get_video_mode(monitor)
        # área da janela que cai dentro deste monitor
        dx = min(x + largura, mx + modo.size.width) - max(x, mx)
        dy = min(y + altura, my + modo.size.height) - max(y, my)
        area = max(dx, 0) * max(dy, 0)
        if area > melhor_area:
            melhor, melhor_area = monitor, area
    return melhor


def alternar_tela_cheia(janela, estado) -> None:
    """F11: vai para tela cheia no monitor atual, ou volta para janela comum."""
    if glfw.get_window_monitor(janela):                      # já está em tela cheia
        x, y, largura, altura = estado.geometria_janela
        glfw.set_window_monitor(janela, None, x, y, largura, altura, 0)
        return
    # guarda posição e tamanho para poder voltar depois
    x, y = glfw.get_window_pos(janela)
    largura, altura = glfw.get_window_size(janela)
    estado.geometria_janela = (x, y, largura, altura)
    monitor = monitor_da_janela(janela)
    modo = glfw.get_video_mode(monitor)
    glfw.set_window_monitor(janela, monitor, 0, 0,
                            modo.size.width, modo.size.height, modo.refresh_rate)


def definir_mouse_preso(janela, estado, preso: bool) -> None:
    """Preso = o mouse controla a câmera (cursor escondido). Solto = cursor normal."""
    estado.mouse_preso = preso
    modo = glfw.CURSOR_DISABLED if preso else glfw.CURSOR_NORMAL
    glfw.set_input_mode(janela, glfw.CURSOR, modo)
    estado.primeiro_mouse = True    # evita um "pulo" da câmera ao prender de novo


class Estado:
    """Tudo que muda enquanto o programa roda e não é uma tecla de liga/desliga."""

    def __init__(self):
        self.aspect = LARGURA / ALTURA
        self.nivel_mar = 0.0                 # em UNIDADES DE MUNDO
        self.nivel_ajuda = 1                 # 0 = oculta, 1 = básica, 2 = completa
        self.primeiro_mouse = True
        self.mouse_preso = True              # TAB solta/prende o mouse
        self.geometria_janela = (100, 100, LARGURA, ALTURA)   # usada ao sair da tela cheia
        self.ultimo_x = LARGURA / 2
        self.ultimo_y = ALTURA / 2


def main() -> None:
    # --- 1. Janela + contexto -----------------------------------------
    janela, ctx = criar_janela_e_contexto()

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
    glfw.set_input_mode(janela, glfw.CURSOR, glfw.CURSOR_DISABLED)

    estado = Estado()
    wireframe = Interruptor(glfw.KEY_Z, False)
    lod_ligado = Interruptor(glfw.KEY_L, True, "LOD:")
    debug_lod = Interruptor(glfw.KEY_K, False)
    morph = Interruptor(glfw.KEY_M, True, "morphing:")
    # Culling vem DESLIGADO: a imagem é idêntica nos dois casos, mas assim o
    # comportamento descrito no artigo (tecla L) não muda. Ligue com C.
    culling = Interruptor(glfw.KEY_C, False, "frustum culling:")
    mostrar_foto = Interruptor(glfw.KEY_P, False)
    boasvindas = Interruptor(glfw.KEY_I, True)
    interruptores = (wireframe, lod_ligado, debug_lod, morph, culling, mostrar_foto, boasvindas)
    tecla_resetar = Tecla(glfw.KEY_R)
    tecla_ajuda = Tecla(glfw.KEY_H)
    tecla_mouse = Tecla(glfw.KEY_TAB)
    tecla_tela_cheia = Tecla(glfw.KEY_F11)

    def ajustar_nivel_mar(unidades: float) -> None:
        unidades = max(-cena.altura_ref, min(cena.altura_ref, unidades))
        if abs(unidades - estado.nivel_mar) > 1e-5:
            estado.nivel_mar = unidades
            print(f"nivel do mar: {unidades / cena.unidades_por_metro:+.2f} m")

    taxa_mar = 0.8 * cena.unidades_por_metro   # ajuste contínuo ~ 0,8 m/s

    def ao_redimensionar(_janela, largura, altura):
        altura = max(altura, 1)
        ctx.viewport = (0, 0, largura, altura)
        estado.aspect = largura / altura
        hud.atualizar_viewport(largura, altura)

    def ao_mover_mouse(_janela, x, y):
        if not estado.mouse_preso:
            return                 # mouse solto: a câmera não gira
        if estado.primeiro_mouse:
            estado.ultimo_x, estado.ultimo_y = x, y
            estado.primeiro_mouse = False
            return
        dx = x - estado.ultimo_x
        dy = estado.ultimo_y - y   # invertido: para cima = pitch positivo
        estado.ultimo_x, estado.ultimo_y = x, y
        cam.process_mouse(dx, dy)

    glfw.set_framebuffer_size_callback(janela, ao_redimensionar)
    glfw.set_cursor_pos_callback(janela, ao_mover_mouse)

    def ao_clicar(_janela, botao, acao, _mods):
        # clicar na janela com o mouse solto prende o mouse de novo
        if acao == glfw.PRESS and not estado.mouse_preso:
            definir_mouse_preso(janela, estado, True)

    glfw.set_mouse_button_callback(janela, ao_clicar)

    # --- 4. Render loop ------------------------------------------
    t_inicio = time.perf_counter()
    t_anterior = t_inicio

    while not glfw.window_should_close(janela):
        agora = time.perf_counter()
        dt = agora - t_anterior
        t_anterior = agora
        tempo = agora - t_inicio

        glfw.poll_events()

        # Teclado: sair, andar, nível do mar e liga/desliga de opções.
        if apertada(janela, glfw.KEY_ESCAPE):
            glfw.set_window_should_close(janela, True)

        if tecla_mouse.apertou(janela):
            definir_mouse_preso(janela, estado, not estado.mouse_preso)
        if tecla_tela_cheia.apertou(janela):
            alternar_tela_cheia(janela, estado)

        cam.speed = 120.0 if apertada(janela, glfw.KEY_LEFT_SHIFT) else 40.0
        moveu = False
        for codigo, direcao in MOVIMENTOS:
            if apertada(janela, codigo):
                cam.process_keyboard(direcao, dt)
                moveu = True
        if moveu:
            boasvindas.ligado = False              # some ao começar a explorar

        # R: resgata quem se perdeu, voltando pro ponto de partida.
        if tecla_resetar.apertou(janela):
            cam.resetar(pos_inicial)

        if apertada(janela, glfw.KEY_COMMA):
            ajustar_nivel_mar(estado.nivel_mar - taxa_mar * dt)
        if apertada(janela, glfw.KEY_PERIOD):
            ajustar_nivel_mar(estado.nivel_mar + taxa_mar * dt)
        for numero, metros in CENARIOS_MAR.items():
            if apertada(janela, getattr(glfw, f"KEY_{numero}")):
                ajustar_nivel_mar(metros * cena.unidades_por_metro)

        for interruptor in interruptores:
            interruptor.atualizar(janela)
        ctx.wireframe = wireframe.ligado

        # H cicla a legenda: oculta -> básica -> completa -> oculta ...
        if tecla_ajuda.apertou(janela):
            estado.nivel_ajuda = (estado.nivel_ajuda + 1) % 3

        view = cam.get_view_matrix()
        proj = cam.get_projection_matrix(estado.aspect)

        ctx.clear(0.62, 0.72, 0.84)
        # Mede o tempo de render de verdade (igual ao bench.py: sincroniza a
        # GPU com ctx.finish()) — é esse número, não o FPS da tela (travado
        # em ~60 pelo V-Sync), que muda quando se aperta L.
        t_render0 = time.perf_counter()
        cena.desenhar(
            view, proj, cam.position,
            nivel_mar=estado.nivel_mar, tempo=tempo,
            lod_ligado=lod_ligado.ligado, morph=morph.ligado,
            debug_lod=debug_lod.ligado, frustum_culling=culling.ligado,
        )
        ctx.finish()
        tempo_render_ms = (time.perf_counter() - t_render0) * 1000.0

        bearing = cam.bearing_graus()
        hud.atualizar_status(
            estado.nivel_mar / cena.unidades_por_metro,
            lod_ligado.ligado, morph.ligado, tempo_render_ms,
            culling_ligado=culling.ligado,
        )
        hud.atualizar_bussola(bearing)
        hud.atualizar_minimapa(cam.position.x, cam.position.z, bearing)
        hud.desenhar(estado.nivel_ajuda, mostrar_foto.ligado, boasvindas.ligado)
        glfw.swap_buffers(janela)

    glfw.terminate()


if __name__ == "__main__":
    main()
