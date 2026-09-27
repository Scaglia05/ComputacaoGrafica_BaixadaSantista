"""
=============================================================================
 exemplos/triangulo.py  —  Um triângulo colorido
=============================================================================

Com janela + contexto + render loop prontos (exemplos/janela.py), este
exemplo desenha a primeira geometria e introduz 4 conceitos centrais do
pipeline gráfico programável:

  VÉRTICE   Ponto com atributos. Aqui: POSIÇÃO (x, y) + COR (r, g, b).

  VBO       Vertex Buffer Object — bloco de memória NA GPU com o array de
            vértices. Enviar CPU->GPU é caro, então fazemos uma vez só.

  SHADERS   Programas que rodam NA GPU, em paralelo:
              vertex shader   : 1x por vértice; define gl_Position.
              fragment shader : 1x por pixel do triângulo; define a cor.
            Entre eles a GPU RASTERIZA e INTERPOLA os out/in — por isso a
            cor faz degradê suave entre os vértices.

  VAO       Vertex Array Object — a "planta baixa" que diz à GPU como ler
            o VBO (quantos floats por atributo, em que ordem, para qual
            variável "in").

Coordenadas: ainda SEM câmera/matrizes. As posições são escritas direto em
NDC — centro da tela (0, 0), cantos (-1,-1) e (+1,+1).

Como rodar
----------
  python exemplos/triangulo.py
"""

import glfw
import moderngl
import numpy as np

LARGURA, ALTURA = 960, 540


VERTEX_SHADER = """
#version 330 core
in vec2 in_pos;      // posição em NDC (vem do VBO)
in vec3 in_color;    // cor RGB       (vem do VBO)
out vec3 v_color;    // saída interpolada para o fragment shader
void main() {
    v_color = in_color;
    gl_Position = vec4(in_pos, 0.0, 1.0);  // já em NDC: z = 0, w = 1
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec3 v_color;     // cor interpolada por pixel
out vec4 f_color;    // cor final (R, G, B, A)
void main() {
    f_color = vec4(v_color, 1.0);
}
"""


def main() -> None:
    # --- Janela + contexto (igual ao exemplo da janela) --------------
    if not glfw.init():
        raise RuntimeError("Não foi possível inicializar o GLFW")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)

    window = glfw.create_window(LARGURA, ALTURA, "Exemplo - triangulo", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Não foi possível criar a janela GLFW")

    glfw.make_context_current(window)
    glfw.swap_interval(1)
    ctx = moderngl.create_context()

    # 1. Vértices na CPU: layout intercalado [x, y, r, g, b] por vértice.
    #    dtype 'f4' = float de 32 bits (o que a GPU espera).
    vertices = np.array([
        # x      y       r    g    b
        -0.6,  -0.4,    1.0, 0.0, 0.0,   # inferior-esquerdo (vermelho)
         0.6,  -0.4,    0.0, 1.0, 0.0,   # inferior-direito  (verde)
         0.0,   0.6,    0.0, 0.4, 1.0,   # superior          (azul)
    ], dtype="f4")

    # 2. VBO: copia os vértices para a memória da GPU.
    vbo = ctx.buffer(vertices.tobytes())

    # 3. Program: compila e linka os dois shaders.
    prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)

    # 4. VAO: "2f 3f" = primeiro atributo tem 2 floats, segundo tem 3;
    #    os nomes casam com as variáveis "in" na mesma ordem.
    vao = ctx.vertex_array(prog, [(vbo, "2f 3f", "in_pos", "in_color")])

    # 5. Render loop.
    while not glfw.window_should_close(window):
        glfw.poll_events()
        if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
            glfw.set_window_should_close(window, True)

        ctx.clear(0.10, 0.14, 0.20)
        vao.render(moderngl.TRIANGLES)   # GPU: 3x vertex shader -> rasteriza -> fragment shader
        glfw.swap_buffers(window)

    glfw.terminate()


if __name__ == "__main__":
    main()
