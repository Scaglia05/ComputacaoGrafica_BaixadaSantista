# Guia de apresentação — Visualização de Elevação Costeira

Documento de estudo para apresentar o projeto ao professor. Cobre, de ponta
a ponta: o tema, a stack, os conceitos de Computação Gráfica, o código
módulo a módulo, o que é herdado dos artigos-base, o que é contribuição
nossa, a avaliação experimental, as limitações e as perguntas prováveis.

---

## 1. O tema

### 1.1 Problema do mundo real

A subida do nível do mar e a erosão costeira ameaçam cidades litorâneas.
Para planejar (onde construir muro de contenção, o que vai alagar em 2100,
etc.) é preciso **visualizar** o terreno costeiro e simular cenários de
inundação sobre ele. Isso é *geovisualização*: transformar um Modelo
Digital de Elevação (DEM) em uma cena 3D navegável.

### 1.2 O desafio de Computação Gráfica

Um DEM de uma região costeira tem **milhões de pontos**. Renderizar tudo a
cada quadro, a 60 fps, num notebook ou celular, não fecha. Duas técnicas
resolvem isso e são o núcleo do projeto:

1. **Nível de detalhe adaptativo (LOD)** — desenhar o terreno em alta
   resolução só perto da câmera; longe, usar malha grosseira. Menos
   triângulos sem perda visível.
2. **Superfície de água procedural** — a "água que sobe" não é uma malha
   detalhada modelada à mão; é um plano cuja ondulação é calculada no
   shader, com a altura de base (nível do mar) como parâmetro ajustável.

### 1.3 Recorte escolhido

**Baixada Santista (Santos / São Vicente / Guarujá, SP)**: costa baixa e
plana com a **Serra do Mar** (escarpa de ~1.000 m) logo atrás. Escolha
técnica: o relevo forte da serra exercita bem o LOD, e a planície costeira
mostra claramente a área inundada quando o mar sobe. É também uma das
regiões mais estudadas do Brasil quanto a subida do mar e subsidência.

> O enunciado **proíbe** reproduzir o cenário original dos artigos-base
> (que tratam de outros contextos). Herdamos só a **metodologia**; a
> aplicação (costa brasileira + inundação) é nossa.

---

## 2. Artigos-base e metodologia herdada

| # | Artigo | O que herdamos |
|---|--------|----------------|
| 1 (obrigatório) | **Tanner, Migdal & Jones (1998)** — *The Clipmap: A Virtual Mipmap* (a especificação oficial atribui a eles o título "Terrain Rendering using Spherical Clipmaps", que na verdade é de **Clasen & Hege, 2006**) | Conceito de LOD organizado em "anéis" de detalhe em torno do observador. Adaptamos de esfera → terreno plano, e de clipmap → **quadtree** (via CDLOD, Strugar 2009). |
| 2 (obrigatório) | **R. Welch (2019)** — *Real-time ocean simulation* (TCC de B.Sc.; a especificação usa o título "GPU Clipmaps and Ocean Simulation", sem fonte localizável) | Conceito de superfície de água dinâmica gerada em tempo real no shader, em vez de malha animada. |
| 3 (complementar) | **Strugar (2009)** — *Continuous Distance-Dependent Level of Detail for Rendering Heightmaps* (CDLOD) | O algoritmo de LOD que efetivamente implementamos: quadtree + seleção por distância + **morphing** de vértices entre níveis. |
| 4 (complementar) | **Fournier & Reeves (1986)** — *A Simple Model of Ocean Waves* | A matemática das **ondas de Gerstner** (a partícula descreve um círculo; crista afiada, vale largo), já pensada para zona costeira. |
| 5–6 (complementares) | Estudo de geovisualização de subida do mar (Vancouver, arXiv); Brown, Jude et al. (2006) sobre erosão costeira via DEM | Embasamento científico da aplicação (visualizar inundação sobre DEM). |

> **Nota sobre a citação #1:** a especificação oficial do eixo atribui o
> título *"Terrain Rendering using Spherical Clipmaps"* a C. C. Tanner,
> C. J. Migdal e M. T. Jones. Na literatura, esse título costuma ser
> associado a Clasen & Hege (2006); Tanner/Migdal/Jones são mais conhecidos
> por *"The Clipmap: A Virtual Mipmap"* (1998). Decisão do grupo: **seguir a
> especificação oficial como fonte da verdade** — usar as ideias
> apresentadas nos artigos do eixo como base da implementação, sem depender
> de confirmação adicional do professor sobre a autoria exata.

### Por que CDLOD (quadtree) em vez de clipmap **esférico** literal

O artigo obrigatório usa uma malha esférica porque resolve o problema de
renderizar terreno em **escala planetária** — o "esférico" existe para
lidar com a curvatura da Terra quando o domínio é o globo inteiro (ex.:
simuladores de voo, visualização de todo o planeta). A Baixada Santista é
um recorte **plano e limitado** (~50 km de lado): não há curvatura
relevante a representar, e aplicar a máquina de reprojeção esférica aqui
não traria benefício nenhum — só complexidade sem propósito.

Por isso adaptamos o **princípio** do clipmap (detalhe decrescente com a
distância ao observador, por anéis/níveis) usando **CDLOD** (Strugar,
2009): a evolução direta e bem documentada do mesmo conceito, formulada
para terrenos planos e limitados via quadtree, e que resolve de quebra
o problema clássico de emenda entre níveis (*cracks*) com *morphing* de
vértices — o que o clipmap original não endereça. Medimos esse custo
(o *morphing*) experimentalmente e confirmamos que é desprezível (ver
`bench/custo_do_morph.png`).

Em resumo: manter as **ideias** do artigo (LOD hierárquico por distância,
independência entre resolução dos dados e custo de renderização) e trocar
a técnica de reprojeção (esférica → quadtree plano) porque o domínio da
aplicação não tem curvatura de planeta para justificar a original.

> **Pendência:** confirmar com o professor se os 4 complementares podem ser
> citados junto aos 2 obrigatórios.

---

## 3. A stack — o que cada biblioteca faz

Linguagem: **Python 3.11**. Ambiente isolado em `.venv`.

| Biblioteca | Papel | Por que ela |
|---|---|---|
| **ModernGL** (5.11) | Empacota o OpenGL moderno numa API de objetos Python: `Context`, `Buffer`, `Texture`, `Program` (shaders), `VertexArray`. NÃO cria janela. | Evita o boilerplate do OpenGL puro (C-style, `glGen*`, ponteiros). Continua sendo OpenGL 3.3 core "de verdade" — shaders GLSL, pipeline programável. |
| **GLFW** (2.7) | Fala com o sistema operacional: cria a janela, o **contexto OpenGL**, lê teclado e mouse, gerencia o *double buffering*. | Padrão de fato para janela + input em OpenGL. Leve. |
| **PyGLM** (2.7) | Vetores e matrizes (`vec3`, `mat4`) e funções de câmera: `lookAt`, `perspective`, `normalize`, `cross`. Import: `import glm`. | É a `glm` do C++ (usada em quase todo tutorial de OpenGL) portada, com o mesmo comportamento. Rápida (C++ por baixo). |
| **NumPy** (1.26) | Toda a geometria é construída como array: grades de vértices, índices de triângulos, o campo de altura. Operações vetorizadas (sem laço Python). | Enviar dados para a GPU exige buffers contíguos de `float32`/`uint32` — exatamente o que um `ndarray` é. |
| **Pillow** (10.4) | Lê a imagem do DEM (PNG dos tiles), lê a foto de referência, e **desenha o texto da HUD** numa imagem (OpenGL não tem texto). | Manipulação de imagem simples e sem dependências pesadas. |
| **opensimplex** (0.4.5) | Ruído Simplex — usado no modo procedural (terreno fictício) como alternativa ao DEM real. | Ruído coerente e suave, bom para relevo. |
| **matplotlib** (3.x) | Só no `bench.py`: gera os gráficos do benchmark (FPS × resolução, etc.). | Padrão para gráficos científicos em Python. |

### Como elas se encaixam (o pipeline)

```
GLFW  ──cria──►  janela + contexto OpenGL
                        │
ModernGL  ──envolve──►  contexto  ◄── NumPy sobe os arrays (buffers/texturas)
                        │
                 shaders GLSL (vertex + fragment) rodam na GPU
                        │  matrizes vindas da PyGLM
                        ▼
                 imagem no framebuffer  ──►  GLFW troca os buffers ──► tela
```

---

## 4. Conceitos de Computação Gráfica usados

Um mini-glossário para não travar na banca:

- **Pipeline gráfico programável**: a GPU processa vértices → rasteriza
  (descobre quais pixels o triângulo cobre) → processa fragmentos (pixels).
  Nós programamos duas etapas com *shaders*.
- **Vertex shader**: roda 1× por vértice. Decide a posição final na tela
  (`gl_Position`). No nosso terreno, ele também **lê a altura de uma
  textura** e desloca o vértice para cima (*displacement mapping*).
- **Fragment shader**: roda 1× por pixel coberto. Decide a cor.
- **VBO / VAO / EBO**: *Vertex Buffer Object* = os vértices na memória da
  GPU; *Element Buffer* = os índices dos triângulos; *Vertex Array Object* =
  a "planta baixa" que diz à GPU como ler o VBO.
- **Espaços de coordenadas e o pipeline M-V-P**: `Model` (objeto → mundo),
  `View` (mundo → câmera), `Projection` (câmera → tela, com perspectiva).
  São 3 matrizes 4×4 multiplicadas no vertex shader.
- **Textura**: imagem na GPU, amostrada por coordenada `uv ∈ [0,1]`. Nós
  usamos uma textura de 1 canal `float` (R32F) para guardar a altura.
- **Blending (transparência)**: `cor_final = α·frente + (1-α)·fundo`. Usado
  na água (α ≈ 0,8) para ver o terreno submerso por baixo.
- **Iluminação**:
  - *Lambert (difuso)*: brilho ∝ `max(0, n·l)` — quanto a superfície
    encara a luz.
  - *Blinn-Phong (especular)*: o ponto brilhante do sol na água.
  - *Fresnel (Schlick)*: superfície vista de raspão reflete mais (a água
    vira espelho no horizonte).
- **Normal**: vetor perpendicular à superfície, necessário para iluminar.
  No terreno, estimada por **diferenças finitas** da altura; na água,
  **analítica** (derivada da soma das ondas).
- **LOD (Level of Detail)**: usar menos geometria onde o detalhe não é
  perceptível (longe da câmera).
- **Quadtree**: árvore em que cada nó quadrado se divide em 4. Estrutura
  espacial para organizar os blocos do terreno por nível de detalhe.

---

## 5. O código, módulo a módulo

Ordem de leitura recomendada: `exemplos/` → `camera.py` → `heightmap.py` →
`dem.py` → `lod.py` → `shaders/terrain.*` → `water.*` → `scene.py` →
`main.py` → `bench.py`.

### `exemplos/janela.py` (≈70 linhas)
O "hello world": GLFW cria janela + contexto; ModernGL pega o contexto; um
*render loop* que a cada frame limpa a tela e troca os buffers. Sem
geometria ainda. **Conceito:** janela, contexto, double buffering, loop.

### `exemplos/triangulo.py` (≈110 linhas)
Um triângulo colorido em coordenadas de tela (NDC). Introduz **VBO, shaders
(vertex/fragment), VAO** e a interpolação automática entre os vértices (o
degradê de cor). **Conceito:** o pipeline programável mínimo.

### `camera.py` (107 linhas) — câmera livre
Guarda `position` e dois ângulos, `yaw` (girar para os lados) e `pitch`
(olhar para cima/baixo, travado em ±89° para não "capotar"). A cada
mudança recalcula os vetores `front`, `right`, `up`.
- `process_keyboard(dir, dt)` — move ao longo de `front`/`right`.
- `process_mouse(dx, dy)` — soma o deslocamento do mouse aos ângulos.
- `get_view_matrix()` → `glm.lookAt(pos, pos+front, up)`.
- `get_projection_matrix(aspect)` → `glm.perspective(60°, aspect, 0.1, 2000)`.

**Conceito:** transformações, matrizes View e Projection, espaço de câmera.

### `heightmap.py` (166 linhas) — geração procedural + grades
- `generate_heightmap(resolution, height_scale, seed, octaves)` — soma
  **5 oitavas** de ruído Simplex (frequência dobra, amplitude cai pela
  metade a cada oitava — *fractal Brownian motion*). Normaliza para
  `±height_scale`. Retorna matriz `(N,N) float32`. É a alternativa fictícia
  ao DEM real.
- `build_unit_grid(subdivisions)` — a grade quadrada `[0,1]×[0,1]`
  **reaproveitável** do CDLOD: o vertex shader recebe canto e tamanho de
  cada bloco e "estica" esta grade para o lugar certo no mundo.
- `grid_indices(resolution)` — os índices que ligam os vértices de uma
  grade N×N em triângulos (2 por célula). Compartilhado por terreno e água.

**Conceito:** ruído procedural, malha indexada, *fBm*.

### `dem.py` (158 linhas) — o DEM real da Baixada Santista
- **Fonte:** AWS Terrain Tiles (`elevation-tiles-prod`), formato
  *terrarium* — PNG em que a elevação em metros é
  `(R·256 + G + B/256) − 32768`. **Sem chave de API.** Dados primários:
  NASA SRTM (terra) + GEBCO (batimetria — por isso há valores **negativos**
  no mar; ao subir o nível, ele preenche o relevo submarino real).
- `_lonlat_para_tile` / `_baixar_tile` — converte a *bounding box*
  (`-23,70..-24,10` lat, `-46,60..-46,05` lon) em coordenadas de tile do
  esquema *slippy map* (zoom 11), baixa e faz **cache** em `data/tiles/`.
- `_mosaico_metros` — junta os tiles num mosaico e recorta na bbox exata.
- `_remover_spikes` — troca texels absurdos (spikes de radar, comuns perto
  de água) pela mediana 3×3. **2 passadas.** (Removeu um pico falso de
  ~1.980 m; o máximo real ficou ~1.180 m, coerente com a Serra do Mar.)
- `carregar_heightmap(...)` — junta tudo, reamostra para 1024×1024
  (bilinear), calcula a escala horizontal real (~50 km) e aplica **exagero
  vertical de 6×** (a razão relevo:largura é ~40:1 — sem exagero a serra
  vira uma lombada). Retorna `(alturas, unidades_por_metro)`, onde
  `unidades_por_metro` converte "mar +X m" em unidades de mundo.

**Conceito:** aquisição de DEM, projeção Web Mercator, reamostragem,
limpeza de dados, exagero vertical (prática padrão de geovisualização —
**declarar no artigo**).

### `lod.py` (116 linhas) — quadtree + seleção CDLOD
- `QuadNode` — bloco quadrado: centro `(cx,cz)`, `size`, `depth`, filhos.
- `build_quadtree(world_size, max_depth=5)` — monta a árvore inteira **uma
  vez** na inicialização (4⁵ = até 1024 folhas).
- `_dist_para_bloco` — menor distância (no plano XZ) da câmera até a **borda**
  do bloco (não o centro — evita que um bloco grande e próximo deixe de
  subdividir só porque o centro dele está longe).
- `select(node, cam_x, cam_z, split_factor, out)` — **a cada frame**,
  percorre a árvore de cima para baixo: se o bloco tem filhos **e** a
  câmera está a menos de `size · split_factor` (2,2) da borda → desce; senão
  → desenha este bloco. Resultado: muitos blocos pequenos perto, poucos
  grandes ao longe.

**Conceito:** estrutura de dados espacial (quadtree), seleção de LOD por
distância.

### `shaders/terrain.vert` (86 linhas) — vertex shader do terreno
Para cada bloco selecionado, recebe `u_node_offset` (canto) e
`u_node_scale` (tamanho). Passos:
1. Posiciona o vértice da grade unitária no mundo; amostra `u_heightmap`
   para pegar a altura → estima a **distância à câmera**.
2. Calcula o **fator de morph** `∈ [0,1]`: 0 no miolo do alcance do bloco,
   1 na borda externa (`u_morph_start`..`u_morph_end`).
3. `aplicar_morph`: desliza os vértices de índice **ímpar** da grade em
   direção aos **pares** (grade mais grossa), proporcional ao fator. Na
   borda entre um bloco fino e um grosso, o fino passa a ter o **mesmo
   espaçamento** do grosso → as duas malhas coincidem, **sem fresta
   (crack) e sem "pop"** quando o bloco troca de nível.
4. Reamostra a altura na posição morphada; calcula a **normal** por
   diferenças finitas (amostra a altura em 4 vizinhos, ~2,5 texels).
5. `gl_Position = proj · view · vec4(mundo, 1)`.

**Conceito:** displacement mapping, CDLOD morphing (contribuição do Strugar).

### `shaders/terrain.frag` (88 linhas) — fragment shader do terreno
- **Cor por altitude + inclinação:** restinga/areia → Mata Atlântica
  (verde) → encosta densa (verde escuro) → rocha exposta nos cumes.
  Paredões íngremes (`1 − n.y` alto) mostram rocha em vez de mata — dá o
  visual de escarpa.
- **Iluminação:** ambiente + difuso de Lambert.
- **Faixa submersa:** se `v_height < u_sea_level`, tinge de verde-escuro,
  mais forte quanto mais fundo. **É o objetivo do projeto** — mostrar o
  que fica debaixo d'água.
- **Debug do LOD** (`u_debug_lod`, tecla K): pinta o bloco pela
  profundidade no quadtree (azul = grande/longe, vermelho = pequeno/perto).
- **Névoa de distância:** longe, mistura com a cor do céu → sensação de
  escala.

### `water.py` (54 linhas) + `shaders/water.*`
- `build_water_plane(resolution=256, world_size)` — só uma **grade plana**
  em `y = 0`, maior que o terreno (1,6×) para alcançar o horizonte.
- `water.vert` (70 linhas) — **ondas de Gerstner**: soma de 6 ondas, cada
  uma com direção, amplitude, comprimento (λ), velocidade e *steepness* Q.
  Cada onda move o vértice na horizontal (na direção de propagação) **e**
  na vertical → crista afiada, vale largo (visual de mar; um seno puro só
  "sobe e desce"). A **normal é analítica** (derivada da soma). A altura de
  base é `u_sea_level` — o nível do mar ajustável.
- `water.frag` (39 linhas) — cor da água: difuso + **especular
  (Blinn-Phong)** para o sol + **Fresnel (Schlick)** para o reflexo do céu
  na rasância + `α = 0,8` (translúcida).

**Conceito:** animação procedural, ondas de Gerstner (Fournier & Reeves),
Blinn-Phong, Fresnel, blending.

### `scene.py` (210 linhas) — a classe `Cena`
Isola **todo o setup de GPU** e o desenho, para que `main.py` (janela) e
`bench.py` (medição) exercitem exatamente o mesmo caminho de render.
- `__init__` — carrega o DEM (ou procedural) → sobe como **textura R32F**;
  cria o `Program` do terreno; monta 2 grades: a pequena 32×32 (um bloco
  do LOD) e a grande na resolução total (o modo "ingênuo", sem LOD); monta
  o quadtree; monta a água.
- `selecionar_blocos(cam_x, cam_z)` — chama `lod.select`.
- `desenhar(view, proj, cam_pos, nivel_mar, tempo, lod_ligado, morph,
  debug_lod)` — reafirma a textura de altura na unidade 0; escreve os
  uniforms; se LOD ligado, faz **1 draw call por bloco** (com canto,
  tamanho, profundidade e faixa de morph); senão, 1 draw call na malha
  única. Depois desenha a água com blending. Retorna `EstatisticasFrame`
  (blocos, draw calls, triângulos) — usado pelo benchmark.

### `hud.py` (188 linhas) — sobreposições 2D
OpenGL não desenha texto → cada painel é montado como **imagem** (Pillow),
subido como textura e desenhado num quad em **espaço de tela**.
- Painel de **comandos** (canto superior-esquerdo, tecla H).
- Painel de **foto** (canto inferior-direito, tecla P) — foto real da Baía
  de Santos com o crédito embutido.
- Usa uma **unidade de textura própria (4)** para não colidir com o
  heightmap (unidade 0).

### `main.py` (226 linhas) — janela + input + laço
Só a "cola": abre a janela GLFW, cria a `Cena` e a `Hud`, e roda o loop:
- lê o teclado/mouse, atualiza a câmera com o `dt` do frame;
- teclas de nível do mar (`,`/`.` contínuo; `1`–`4` cenários em metros);
- `alterna(...)` para as flags de borda (`L`, `M`, `K`, `Z`, `H`, `P`);
- `cena.desenhar(...)` → `hud.desenhar(...)` → `swap_buffers`.

### `bench.py` (247 linhas) — avaliação experimental
Roda **sem janela** (contexto standalone + framebuffer 1280×720),
sincronizando a GPU a cada frame (`ctx.finish()`). Varre:
`{sem_lod, cdlod, cdlod_sem_morph} × {256,512,1024,1536,2048} × {4 câmeras}`,
com 30 frames de aquecimento + 150 medidos. Salva `bench/resultados.csv` e
4 gráficos (matplotlib).

---

## 6. Fluxo de um frame (resumo para a banca)

```
1. main.py lê input → atualiza Camera
2. Camera → matrizes view e projection (PyGLM)
3. lod.select() percorre o quadtree → ~100 a 184 blocos a desenhar (52 a 73 com o frustum culling ligado, tecla `C`)
4. para cada bloco:
     vertex shader: grade unitária → mundo, lê altura da textura,
                    faz morphing, calcula normal
     fragment shader: cor por altitude/inclinação + luz + faixa submersa
5. água: 1 plano, ondas de Gerstner no vertex shader, blending
6. HUD: legenda + foto como quads em espaço de tela
7. GLFW troca os buffers → aparece na tela
```

---

## 7. O que é herdado × o que é novo

| Aspecto | Herdado dos artigos | Nosso |
|---|---|---|
| LOD de terreno | Ideia de anéis de detalhe (Tanner, Migdal & Jones — clipmap esférico); algoritmo CDLOD (Strugar) | Implementação simplificada e didática em Python; **quadtree + seleção por distância + morphing**; chave liga/desliga para comparar |
| Água | Superfície dinâmica no shader (Welch); ondas de Gerstner (Fournier&Reeves) | 6 ondas somadas, normal analítica, Fresnel + Blinn-Phong, **nível de base como parâmetro interativo** |
| Dados | — | **DEM real da Baixada Santista** (SRTM + batimetria GEBCO), com despike e reamostragem |
| Aplicação | Embasamento (estudos de erosão / subida do mar sobre DEM) | **Realce da faixa submersa** reagindo ao nível do mar; **cenários em metros reais** (0 / +0,5 / +1 / +2 m) |
| Combinação | Cada artigo trata terreno **ou** água | **Acoplamento** terreno + água + parâmetro de inundação, com propósito analítico |
| Avaliação | Os artigos **apresentam** o algoritmo | **Experimento controlado** que mediu o *trade-off* e achou o **ponto de virada** (~4 M de triângulos numa RTX 3060 (2,7 a 4,3 M conforme o critério e a execução; ~2,3 M com culling)) |

**Frase-resumo para a apresentação:** *"Pegamos o LOD de terreno de um
artigo e a água dinâmica de outro, implementamos os dois em cima de um DEM
real da Baixada Santista, acoplamos com um controle interativo de nível do
mar para visualizar inundação costeira, e medimos experimentalmente quando
o LOD compensa."*

---

## 8. Avaliação experimental — o resultado

Rodando `bench.py` numa **RTX 3060**:

- O **CDLOD** mantém o tempo de frame quase **constante** (~1 ms) em
  qualquer resolução do heightmap, porque desenha sempre ~0,4 M triângulos.
- A **malha ingênua** (sem LOD) cresce linearmente com a resolução e
  **ultrapassa o CDLOD entre 1024² e 2048² (~5 M de triângulos; faixa 4,4–5,6 M)** — o *ponto
  de virada*.
- O custo do **morphing** é desprezível (dentro do ruído de medição).
- O ~1 ms fixo do CDLOD é **overhead de CPU** (percorrer o quadtree em
  Python + ~100 a 184 draw calls). Numa GPU fraca ou **mobile** (o eixo do
  projeto), o ponto de virada chega **muito antes** — é o argumento a favor
  do LOD.
- **Frustum culling:** reduz o tempo de quadro em ~22% em média (−33% a −38%
  nas câmeras rasante e encosta, ≈0% na aérea) e leva o ponto de virada a
  ~2,3 M de triângulos. A imagem é idêntica com e sem culling (testado).
- **Memória (cada modo em processo isolado):** a 2048², a malha do CDLOD ocupa
  19 MB contra 153 MB da malha completa; pico de RAM de 191 contra 595 MB.

Gráficos em `bench/`: `fps_vs_resolucao.png`, `tempo_por_camera.png`,
`triangulos_vs_tempo.png`, `custo_do_morph.png`.

---

## 9. Limitações (dizer antes que a banca pergunte)

1. **CDLOD simplificado**: o *frustum culling* usa caixas conservadoras, sem
   oclusão, e vem desligado por padrão (tecla `C`); as faixas de morph não
   seguem exatamente as fórmulas do Strugar.
2. **Benchmark em 1 GPU desktop**: sem número de dispositivo móvel, embora
   o eixo seja "Sistemas Mobile". Discutimos por que o resultado se
   traduz (o overhead é constante, a geometria evitada escala).
3. **Exagero vertical de 6×**: necessário para a Serra do Mar aparecer;
   é prática padrão de geovisualização, mas precisa ser declarado.
4. **Água não interage com o terreno**: sem espuma na linha de costa, sem
   refração. Fora do escopo.
5. **Sem testes automatizados**; validação por execução e inspeção visual.
6. **Overhead de Python**: um port em C++ eliminaria o ~1 ms fixo.

---

## 10. Perguntas prováveis da banca — e como responder

**"Por que quadtree e não o clipmap do artigo 1?"**
O clipmap esférico assume uma esfera (planeta). Para um recorte plano de
terreno, o quadtree do CDLOD é a adaptação natural e é o que o Strugar
formaliza. Herdamos a **ideia** (detalhe decrescente com a distância).

**"O que exatamente o morphing resolve?"**
Dois blocos de tamanhos diferentes que se encostam: o grande tem menos
vértices naquela borda e faz uma reta onde o pequeno segue a curva → sobra
uma fresta (*crack*) e há um "pulo" quando o bloco troca de nível. O
morphing desliza os vértices do bloco fino até casarem com os do grosso.
Demonstrável ao vivo com a tecla `M`.

**"De onde vêm os dados e são confiáveis?"**
AWS Terrain Tiles, derivados de NASA SRTM (terra, ~30 m) e GEBCO
(batimetria). Fonte aberta, sem chave. Fazemos limpeza de *spikes*.

**"Por que a inundação de +2 m quase não aparece?"**
Porque é fisicamente correto: +2 m contra ~1.000 m de serra é um fio. O
que importa é a **linha de costa avançando** na planície plana — visível
descendo até o estuário e usando as teclas `1`–`4`.

**"Qual a contribuição de CG, e não só de aplicação?"**
A implementação e a **medição** do CDLOD: quantificamos o *trade-off*
(triângulos evitados × draw calls adicionados) e identificamos o ponto de
virada, que os artigos originais não medem nesse formato.

**"Roda em tempo real?"**
Sim — no desktop, centenas de fps sem V-Sync; com V-Sync, 60 fps
travados. O CDLOD é o que torna isso possível em resolução alta.

---

## 11. Checklist para fechar o projeto

- [ ] Escrever o artigo IEEE (4–8 páginas, template Overleaf)
- [ ] Escrever o relatório da Fase 1 (revisão bibliográfica)
- [ ] Confirmar com o professor os 4 artigos complementares
- [ ] Rodar o benchmark numa 2ª máquina (de preferência mais fraca)
- [ ] Capturar as figuras (ver `bench/` + prints do `main.py`)
- [ ] Justificar o exagero vertical de 6× no texto
