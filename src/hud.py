"""
=============================================================================
 hud.py  —  Sobreposições 2D: boas-vindas, legenda, status e foto
=============================================================================

OpenGL não desenha texto. A saída aqui é: montar cada painel como uma
IMAGEM (com a Pillow) uma única vez, subir como textura, e desenhar essa
textura num quad em espaço de tela (coordenadas -1..1), com transparência.

Painéis:
  - BOAS-VINDAS : tela inicial explicando o objetivo, em português simples
                  (some ao mover a câmera; tecla `I` mostra de novo)
  - AJUDA       : lista de comandos, em 2 níveis — básico (tecla `H` uma vez)
                  e completo (`H` de novo, com LOD/morphing explicados em
                  1 linha cada); mais um `H` esconde tudo
  - STATUS      : nível do mar + selo colorido + modo de LOD/morphing atual +
                  tempo de render do quadro, sempre visível e atualizado ao
                  vivo — é a confirmação de que apertar uma tecla realmente
                  mudou alguma coisa (inclusive o próprio ganho do LOD).
  - BÚSSOLA     : direção do olhar (N/L/S/O + graus), canto inferior-esquerdo.
  - MINIMAPA / FOTO : o mesmo canto (inferior-direito) alterna entre um
                  mapa de topo com um marcador de posição/direção (padrão)
                  e a foto real do local (tecla `P`).

Ajuda/boas-vindas são texturas estáticas (montadas 1x). Status, bússola e
minimapa são dinâmicos: a textura é **reescrita** (não recriada) sempre que
o conteúdo muda, mantendo o mesmo tamanho — trocar o conteúdo de uma
textura já existente é muito mais barato do que criar uma nova a cada frame.
"""

from __future__ import annotations

import math
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_VERT = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

_FRAG = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
void main() { f_color = texture(u_tex, v_uv); }
"""

# A HUD usa uma unidade de textura própria para não colidir com a unidade 0,
# que a cena (scene.py) usa para o heightmap.
_UNIDADE_TEX = 4


def _fonte(tam: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidatos = (
        ["C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf"]
        if mono
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]
    )
    for nome in candidatos:
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _quad(x0: float, ytopo: float, x1: float, ybase: float) -> np.ndarray:
    """6 vértices (pos.xy, uv.xy) de um retângulo em espaço de tela.
    uv (0,0) = canto superior-esquerdo da imagem."""
    return np.array([
        x0, ytopo, 0.0, 0.0,
        x0, ybase, 0.0, 1.0,
        x1, ytopo, 1.0, 0.0,
        x1, ytopo, 1.0, 0.0,
        x0, ybase, 0.0, 1.0,
        x1, ybase, 1.0, 1.0,
    ], dtype="f4")


class _Painel:
    def __init__(self, ctx, prog, imagem: Image.Image, ancora: str, margem: int = 12):
        self.ctx = ctx
        self.prog = prog
        self.ancora = ancora  # "superior-esquerda" | "superior-direita" | "inferior-direita" | "centro"
        self.margem = margem
        self.w, self.h = imagem.size
        self.tex = ctx.texture(imagem.size, 4, imagem.convert("RGBA").tobytes())
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._vao = None
        prog["u_tex"].value = _UNIDADE_TEX

    def posicionar(self, larg_janela: int, alt_janela: int) -> None:
        m = self.margem
        dx = 2.0 * self.w / larg_janela
        dy = 2.0 * self.h / alt_janela
        mx = 2.0 * m / larg_janela
        my = 2.0 * m / alt_janela
        if self.ancora == "inferior-direita":
            x1 = 1.0 - mx
            x0 = x1 - dx
            ybase = -1.0 + my
            ytopo = ybase + dy
        elif self.ancora == "inferior-esquerda":
            x0 = -1.0 + mx
            x1 = x0 + dx
            ybase = -1.0 + my
            ytopo = ybase + dy
        elif self.ancora == "superior-direita":
            x1 = 1.0 - mx
            x0 = x1 - dx
            ytopo = 1.0 - my
            ybase = ytopo - dy
        elif self.ancora == "centro":
            x0, x1 = -dx / 2.0, dx / 2.0
            ytopo, ybase = dy / 2.0, -dy / 2.0
        else:  # superior-esquerda
            x0 = -1.0 + mx
            x1 = x0 + dx
            ytopo = 1.0 - my
            ybase = ytopo - dy
        if self._vao is not None:
            self._vao.release()
        vbo = self.ctx.buffer(_quad(x0, ytopo, x1, ybase).tobytes())
        self._vao = self.ctx.vertex_array(self.prog, [(vbo, "2f 2f", "in_pos", "in_uv")])

    def atualizar_imagem(self, imagem: Image.Image) -> None:
        """Rescreve o conteúdo da textura (a imagem deve ter o MESMO tamanho
        da usada na criação). Mais barato que recriar a textura a cada frame."""
        self.tex.write(imagem.convert("RGBA").tobytes())

    def desenhar(self) -> None:
        self.tex.use(location=_UNIDADE_TEX)
        self._vao.render(moderngl.TRIANGLES)


class Hud:
    def __init__(
        self,
        ctx: moderngl.Context,
        comandos_basicos: list[tuple[str, str]],
        comandos_avancados: list[tuple[str, str]] | None = None,
        *,
        foto: Path | None = None,
        legenda_foto: str = "",
        minimapa_fundo: Image.Image | None = None,
        minimapa_meia_largura: float = 1.0,
    ):
        self.ctx = ctx
        self.prog = ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        self.prog["u_tex"].value = _UNIDADE_TEX

        self._ajuda_basica = _Painel(
            ctx, self.prog, self._img_ajuda("COMANDOS", comandos_basicos), "superior-esquerda"
        )
        self._ajuda_completa = _Painel(
            ctx, self.prog,
            self._img_ajuda("COMANDOS (completo)", comandos_avancados or comandos_basicos, largura=460),
            "superior-esquerda",
        )

        self._boasvindas = _Painel(ctx, self.prog, self._img_boasvindas(), "centro")

        self._foto = None
        if foto is not None and Path(foto).exists():
            self._foto = _Painel(
                ctx, self.prog, self._img_foto(Path(foto), legenda_foto), "inferior-direita"
            )

        # Painel de status — sempre visível, atualizado a cada mudança de
        # nível do mar, modo (LOD/morphing) ou tempo de render. É a
        # confirmação de que apertar uma tecla realmente fez alguma coisa.
        self._status = _Painel(
            ctx, self.prog, self._img_status(0.0, True, True, 0.0), "superior-direita"
        )
        self._status_chave = None

        # Bússola — direção do olhar (canto inferior-esquerdo), sempre visível.
        self._bussola = _Painel(ctx, self.prog, self._img_bussola(0.0), "inferior-esquerda")
        self._bussola_chave = None

        # Minimapa — mesmo canto que a foto (inferior-direito); `desenhar()`
        # escolhe qual dos dois mostrar. `minimapa_fundo` é um render de
        # topo feito 1x pelo main.py (ver gerar_minimapa em main.py).
        self._minimapa = None
        self._minimapa_meia_largura = minimapa_meia_largura
        if minimapa_fundo is not None:
            self._minimapa_fundo = minimapa_fundo.convert("RGBA")
            self._minimapa = _Painel(
                ctx, self.prog, self._compor_minimapa(0.0, 0.0, 0.0), "inferior-direita"
            )
        self._minimapa_chave = None

    # ------------------------------------------------------------------
    @staticmethod
    def _img_ajuda(titulo: str, comandos: list[tuple[str, str]], largura: int = 360) -> Image.Image:
        f_tecla = _fonte(15, mono=True)
        f_desc = _fonte(14)
        f_tit = _fonte(15)
        pad, alt_linha, larg_col1 = 14, 21, 130
        larg = largura
        alt = pad * 2 + alt_linha * (len(comandos) + 1)

        img = Image.new("RGBA", (larg, alt), (10, 14, 20, 205))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, larg - 1, alt - 1], outline=(255, 255, 255, 55))
        d.text((pad, pad), titulo, font=f_tit, fill=(120, 200, 255, 255))
        y = pad + alt_linha
        for tecla, desc in comandos:
            d.text((pad, y), tecla, font=f_tecla, fill=(255, 214, 120, 255))
            d.text((pad + larg_col1, y), desc, font=f_desc, fill=(232, 232, 232, 255))
            y += alt_linha
        return img

    @staticmethod
    def _img_boasvindas() -> Image.Image:
        larg, alt = 620, 320
        img = Image.new("RGBA", (larg, alt), (8, 12, 18, 232))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, larg - 1, alt - 1], outline=(255, 255, 255, 80), width=2)

        d.text((larg / 2, 34), "VISUALIZAÇÃO DE ELEVAÇÃO COSTEIRA", font=_fonte(23),
               fill=(255, 255, 255, 255), anchor="mm")
        d.text((larg / 2, 60), "Baixada Santista — Santos / São Vicente / Guarujá",
               font=_fonte(14), fill=(150, 195, 255, 255), anchor="mm")

        linhas = [
            "Este programa mostra o que pode acontecer com essa costa real",
            "se o nível do mar subir — usando dados de elevação de verdade.",
            "",
            "WASD + mouse    andar pelo terreno e olhar ao redor",
            "1  2  3  4      subir o mar (cenários reais: 0 / +0,5 / +1 / +2 m)",
            "5  6  7         cenários extremos, só para demonstração",
            "H               mostrar / esconder os comandos (2 níveis de detalhe)",
            "I               mostrar esta tela de novo, a qualquer momento",
            "",
            "Pressione W, A, S ou D para começar a explorar.",
        ]
        y = 96
        f = _fonte(14)
        for linha in linhas:
            d.text((30, y), linha, font=f, fill=(225, 225, 225, 255))
            y += 23
        return img

    @staticmethod
    def _img_foto(caminho: Path, legenda: str) -> Image.Image:
        foto = Image.open(caminho).convert("RGB")
        largura_alvo = 360
        escala = largura_alvo / foto.width
        foto = foto.resize((largura_alvo, round(foto.height * escala)), Image.LANCZOS)

        barra = 22 if legenda else 0
        img = Image.new("RGBA", (foto.width + 4, foto.height + 4 + barra), (10, 14, 20, 230))
        img.paste(foto, (2, 2))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(255, 255, 255, 60))
        if legenda:
            d.text((6, foto.height + 5), legenda, font=_fonte(11), fill=(200, 200, 200, 255))
        return img

    @staticmethod
    def _img_status(
        metros: float, lod_ligado: bool, morph_ligado: bool, tempo_render_ms: float,
        culling_ligado: bool = False,
    ) -> Image.Image:
        """Painel de status: nível do mar + selo colorido + modo atual +
        tempo de render do quadro (o número que muda quando você aperta L).

        Limiares de "risco de alagamento" são didáticos (não são uma
        classificação científica oficial) — servem para dar leitura rápida
        a quem não é da área.
        """
        larg, alt = 300, 222
        img = Image.new("RGBA", (larg, alt), (10, 14, 20, 218))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, larg - 1, alt - 1], outline=(255, 255, 255, 60))

        if metros < -0.05:
            status, cor = "NIVEL ABAIXO DO ATUAL", (110, 190, 255)
        elif metros <= 0.05:
            status, cor = "NIVEL ATUAL", (110, 190, 255)
        elif metros <= 1.0:
            status, cor = "RISCO DE ALAGAMENTO", (255, 205, 80)
        else:
            status, cor = "ALAGAMENTO", (255, 95, 95)

        d.text((14, 10), "NIVEL DO MAR", font=_fonte(13), fill=(190, 190, 190, 255))
        d.text((14, 30), f"{metros:+.2f} m", font=_fonte(34, mono=True), fill=(255, 255, 255, 255))
        # bolinha + texto na cor do status, direto sobre o fundo escuro do
        # painel (contraste garantido para as 3 cores — um selo preenchido
        # na própria cor, com texto por cima, ficava ilegível).
        d.ellipse([16, 90, 30, 104], fill=(*cor, 255))
        d.text((38, 90), status, font=_fonte(15), fill=(*cor, 255))

        d.line([(14, 122), (larg - 14, 122)], fill=(255, 255, 255, 40))
        txt_lod = "CDLOD (adaptativo)" if lod_ligado else "malha completa"
        txt_morph = "ligada" if morph_ligado else "DESLIGADA (cracks!)"
        cor_morph = (200, 200, 200) if morph_ligado else (255, 150, 90)
        d.text((14, 130), f"Detalhe: {txt_lod}", font=_fonte(13), fill=(210, 210, 210, 255))
        d.text((14, 150), f"Suavização: {txt_morph}", font=_fonte(13), fill=(*cor_morph, 255))
        txt_culling = "ligado" if culling_ligado else "desligado"
        d.text((14, 170), f"Corte fora da tela: {txt_culling}", font=_fonte(13), fill=(210, 210, 210, 255))

        # Tempo de render do quadro — o número que muda de verdade quando
        # se aperta L (o FPS na tela, com V-Sync, fica travado em ~60 e
        # some a diferença; este tempo é medido igual ao benchmark).
        fps_equiv = 1000.0 / tempo_render_ms if tempo_render_ms > 0 else 0.0
        d.text((14, 194), f"Render: {tempo_render_ms:.2f} ms  (~{fps_equiv:.0f} fps sem limite)",
               font=_fonte(12), fill=(150, 210, 150, 255))
        return img

    @staticmethod
    def _img_bussola(bearing_graus: float) -> Image.Image:
        """Painel de bússola: anel N/L/S/O fixo + agulha que gira conforme
        a direção do olhar (ver Camera.bearing_graus)."""
        larg, alt = 150, 178
        img = Image.new("RGBA", (larg, alt), (10, 14, 20, 205))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, larg - 1, alt - 1], outline=(255, 255, 255, 55))

        cx, cy, r = larg / 2.0, 76.0, 50.0
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(190, 190, 190, 180), width=2)

        f = _fonte(14)
        for letra, ang, cor in (
            ("N", 0.0, (140, 205, 255)), ("L", 90.0, (200, 200, 200)),
            ("S", 180.0, (200, 200, 200)), ("O", 270.0, (200, 200, 200)),
        ):
            rad = math.radians(ang)
            lx = cx + (r + 15) * math.sin(rad)
            ly = cy - (r + 15) * math.cos(rad)
            d.text((lx, ly), letra, font=f, fill=(*cor, 255), anchor="mm")

        # agulha: aponta na direção que a câmera está olhando
        rad = math.radians(bearing_graus)
        ponta = (cx + r * 0.85 * math.sin(rad), cy - r * 0.85 * math.cos(rad))
        cauda = (cx - r * 0.35 * math.sin(rad), cy + r * 0.35 * math.cos(rad))
        d.line([cauda, ponta], fill=(255, 110, 90, 255), width=3)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 255, 255, 255))

        pontos8 = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
        indice = int(((bearing_graus + 22.5) % 360) // 45)
        d.text((larg / 2, alt - 15), f"{pontos8[indice]}  {bearing_graus:0.0f}°",
               font=_fonte(13), fill=(220, 220, 220, 255), anchor="mm")
        return img

    def _compor_minimapa(self, cam_x: float, cam_z: float, bearing_graus: float) -> Image.Image:
        """Copia o mapa de topo (fundo estático) e desenha por cima o
        marcador de posição + seta de direção da câmera."""
        img = self._minimapa_fundo.copy()
        d = ImageDraw.Draw(img)
        tam = img.width
        meia = self._minimapa_meia_largura
        px = (cam_x + meia) / (2.0 * meia) * tam
        py = (cam_z + meia) / (2.0 * meia) * tam
        px = max(8.0, min(tam - 8.0, px))
        py = max(8.0, min(tam - 8.0, py))

        rad = math.radians(bearing_graus)
        ponta = (px + 14 * math.sin(rad), py - 14 * math.cos(rad))
        d.line([(px, py), ponta], fill=(255, 255, 255, 230), width=2)
        d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(255, 70, 60, 255),
                  outline=(255, 255, 255, 255), width=1)
        return img

    # ------------------------------------------------------------------
    def atualizar_viewport(self, larg: int, alt: int) -> None:
        self._ajuda_basica.posicionar(larg, alt)
        self._ajuda_completa.posicionar(larg, alt)
        self._boasvindas.posicionar(larg, alt)
        self._status.posicionar(larg, alt)
        self._bussola.posicionar(larg, alt)
        if self._foto is not None:
            self._foto.posicionar(larg, alt)
        if self._minimapa is not None:
            self._minimapa.posicionar(larg, alt)

    def atualizar_status(
        self, metros: float, lod_ligado: bool, morph_ligado: bool, tempo_render_ms: float,
        culling_ligado: bool = False,
    ) -> None:
        """Chamar 1x por frame. Só redesenha a textura quando algo muda de
        verdade (nível arredondado a 1 cm, tempo de render arredondado a
        0,1 ms, ou os modos de LOD/morphing/culling)."""
        chave = (round(metros, 2), lod_ligado, morph_ligado, round(tempo_render_ms, 1), culling_ligado)
        if chave == self._status_chave:
            return
        self._status_chave = chave
        self._status.atualizar_imagem(
            self._img_status(metros, lod_ligado, morph_ligado, tempo_render_ms, culling_ligado)
        )

    def atualizar_bussola(self, bearing_graus: float) -> None:
        """Chamar 1x por frame com Camera.bearing_graus(). Arredonda a 2°
        para não redesenhar a textura a cada pixel de movimento do mouse."""
        chave = round(bearing_graus / 2.0) * 2.0
        if chave == self._bussola_chave:
            return
        self._bussola_chave = chave
        self._bussola.atualizar_imagem(self._img_bussola(bearing_graus))

    def atualizar_minimapa(self, cam_x: float, cam_z: float, bearing_graus: float) -> None:
        """Chamar 1x por frame com a posição XZ da câmera (unidades de
        mundo) e o rumo atual. Sem custo se `minimapa_fundo` não foi
        passado ao construtor."""
        if self._minimapa is None:
            return
        chave = (round(cam_x, 1), round(cam_z, 1), round(bearing_graus / 3.0) * 3.0)
        if chave == self._minimapa_chave:
            return
        self._minimapa_chave = chave
        self._minimapa.atualizar_imagem(self._compor_minimapa(cam_x, cam_z, bearing_graus))

    def desenhar(
        self,
        nivel_ajuda: int = 1,
        mostrar_foto: bool = False,
        mostrar_boasvindas: bool = False,
    ) -> None:
        """nivel_ajuda: 0 = esconde a legenda, 1 = básica, 2 = completa."""
        ctx = self.ctx
        ctx.wireframe = False
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        if nivel_ajuda == 1:
            self._ajuda_basica.desenhar()
        elif nivel_ajuda >= 2:
            self._ajuda_completa.desenhar()
        # Canto inferior-direito: a foto (sob pedido) ou o minimapa (padrão).
        if mostrar_foto and self._foto is not None:
            self._foto.desenhar()
        elif self._minimapa is not None:
            self._minimapa.desenhar()
        self._status.desenhar()    # sempre visível
        self._bussola.desenhar()   # sempre visível
        if mostrar_boasvindas:
            self._boasvindas.desenhar()
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
