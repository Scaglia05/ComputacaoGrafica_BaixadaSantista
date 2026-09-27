"""
=============================================================================
 exemplos/janela.py  —  Uma janela vazia com GLFW + ModernGL
=============================================================================

Primeiro exemplo isolado da fase de estudo. Antes de desenhar qualquer
coisa é preciso ter:

  1) uma JANELA do sistema operacional para onde a GPU vai desenhar;
  2) um CONTEXTO OpenGL associado a ela — o "estado" da GPU (shaders,
     buffers e configurações ativos);
  3) um RENDER LOOP — laço que, a cada frame, limpa a tela, (futuramente)
     desenha a cena e troca os buffers para exibir o resultado.

Aqui a entrega é só isso: janela azul-acinzentada que fecha com ESC.

Divisão de papéis
-----------------
  GLFW     -> fala com o SO: cria a janela, lê teclado/mouse, faz o
              "double buffering".
  ModernGL -> embrulha o OpenGL numa API de objetos Python. NÃO cria
              janela — usa o contexto que o GLFW preparou.

Como rodar
----------
  python exemplos/janela.py
"""

import glfw
import moderngl

LARGURA, ALTURA = 960, 540


def main() -> None:
    # 1. Inicializa o GLFW ------------------------------------------------
    if not glfw.init():
        raise RuntimeError("Não foi possível inicializar o GLFW")

    # 2. Descreve o contexto desejado ANTES de criar a janela ----------
    #    OpenGL 3.3 perfil "core" (sem funções legadas) — mínimo para
    #    shaders modernos e o que o ModernGL espera.
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)  # exigido no macOS

    # 3. Cria a janela (que já traz um contexto OpenGL embutido) -------
    window = glfw.create_window(LARGURA, ALTURA, "Exemplo - janela vazia", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Não foi possível criar a janela GLFW")

    glfw.make_context_current(window)  # chamadas GL da thread afetam ESTA janela
    glfw.swap_interval(1)              # V-Sync ligado (~60 FPS)

    # 4. Cria o contexto ModernGL sobre o contexto do GLFW -------------
    ctx = moderngl.create_context()
    print("Placa     :", ctx.info["GL_RENDERER"])
    print("Versão GL :", ctx.info["GL_VERSION"])

    # 5. Render loop ----------------------------------------------------
    while not glfw.window_should_close(window):
        glfw.poll_events()  # processa eventos do SO (teclado, mouse, X, resize)

        if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
            glfw.set_window_should_close(window, True)

        ctx.clear(0.10, 0.14, 0.20)   # limpa a tela com uma cor de fundo (R, G, B)
        glfw.swap_buffers(window)     # troca back buffer <-> front buffer

    # 6. Encerramento limpo ------------------------------------------
    glfw.terminate()


if __name__ == "__main__":
    main()
