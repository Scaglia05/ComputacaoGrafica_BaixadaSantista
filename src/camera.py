"""
=============================================================================
 camera.py  —  Câmera livre (free-fly / "modo espectador")
=============================================================================

Por que uma câmera?
-------------------
No triângulo em NDC nós escrevíamos as posições já "na tela". Para um mundo
3D navegável isso não serve: precisamos poder olhar a cena de qualquer
posição e ângulo. Isso é feito com duas matrizes que o shader multiplica:

  VIEW        Leva o mundo para o "espaço da câmera" (câmera na origem,
              olhando para -Z). É o inverso da pose da câmera.
              Construída aqui com glm.lookAt(pos, alvo, up).

  PROJECTION  Aplica a perspectiva: objetos distantes encolhem, e define o
              frustum (campo de visão, near/far). glm.perspective(fovy,
              aspect, near, far).

Orientação por YAW / PITCH
--------------------------
Guardamos a direção do olhar como dois ângulos:
  yaw   : rotação em torno do eixo Y (olhar para os lados).
  pitch : rotação para cima/baixo (limitado a ~±89° para não "capotar").
A cada mudança recalculamos os vetores front / right / up.

Convenção de eixos (igual a heightmap.py): X = leste, Y = cima, Z = sul.
"""

from __future__ import annotations

import math

import glm


class Camera:
    def __init__(
        self,
        position=(0.0, 40.0, 90.0),
        yaw: float = -90.0,   # -90° => olhando para -Z (para "dentro" da cena)
        pitch: float = -20.0,
        speed: float = 40.0,          # unidades de mundo por segundo
        sensitivity: float = 0.12,    # graus por pixel de mouse
        fov: float = 60.0,            # campo de visão vertical, em graus
    ):
        self.position = glm.vec3(position)
        self.yaw = yaw
        self.pitch = pitch
        self.speed = speed
        self.sensitivity = sensitivity
        self.fov = fov

        self.world_up = glm.vec3(0.0, 1.0, 0.0)
        self._update_vectors()

    # ------------------------------------------------------------------
    # Recalcula front/right/up a partir de yaw e pitch
    # ------------------------------------------------------------------
    def _update_vectors(self) -> None:
        y = glm.radians(self.yaw)
        p = glm.radians(self.pitch)
        front = glm.vec3(
            glm.cos(y) * glm.cos(p),
            glm.sin(p),
            glm.sin(y) * glm.cos(p),
        )
        self.front = glm.normalize(front)
        # right = front x world_up  (perpendicular aos dois)
        self.right = glm.normalize(glm.cross(self.front, self.world_up))
        # up "real" da câmera, já considerando o pitch
        self.up = glm.normalize(glm.cross(self.right, self.front))

    # ------------------------------------------------------------------
    # Input de teclado — 'direction' é uma string; dt = tempo do frame (s)
    # ------------------------------------------------------------------
    def process_keyboard(self, direction: str, dt: float) -> None:
        v = self.speed * dt
        if direction == "FORWARD":
            self.position += self.front * v
        elif direction == "BACKWARD":
            self.position -= self.front * v
        elif direction == "LEFT":
            self.position -= self.right * v
        elif direction == "RIGHT":
            self.position += self.right * v
        elif direction == "UP":
            self.position += self.world_up * v
        elif direction == "DOWN":
            self.position -= self.world_up * v

    # ------------------------------------------------------------------
    # Input de mouse — dx, dy = deslocamento em pixels desde o último frame
    # ------------------------------------------------------------------
    def process_mouse(self, dx: float, dy: float) -> None:
        self.yaw += dx * self.sensitivity
        self.pitch += dy * self.sensitivity
        # Trava vertical: evita virar de cabeça para baixo.
        self.pitch = max(-89.0, min(89.0, self.pitch))
        self._update_vectors()

    # ------------------------------------------------------------------
    # Resgate de quem se perdeu voando livre (tecla R em main.py)
    # ------------------------------------------------------------------
    def resetar(self, position, yaw: float = -90.0, pitch: float = -20.0) -> None:
        self.position = glm.vec3(position)
        self.yaw = yaw
        self.pitch = pitch
        self._update_vectors()

    # ------------------------------------------------------------------
    # Direção do olhar em graus de bússola, para o painel de bússola/minimapa
    # ------------------------------------------------------------------
    def bearing_graus(self) -> float:
        """0° = Norte, 90° = Leste, 180° = Sul, 270° = Oeste.

        Convenção de eixos do projeto (heightmap.py/dem.py): Norte = -Z,
        Leste = +X. O componente horizontal de `front` já dá isso: quanto
        mais `front` aponta para -Z, mais perto do Norte; quanto mais para
        +X, mais perto do Leste.
        """
        graus = math.degrees(math.atan2(self.front.x, -self.front.z))
        return graus % 360.0

    # ------------------------------------------------------------------
    # Matrizes para enviar ao shader
    # ------------------------------------------------------------------
    def get_view_matrix(self) -> glm.mat4:
        return glm.lookAt(self.position, self.position + self.front, self.up)

    def get_projection_matrix(self, aspect: float) -> glm.mat4:
        return glm.perspective(glm.radians(self.fov), aspect, 0.1, 2000.0)
