# Guia do código — o essencial para desenvolver ideias

Este guia reúne só o que você precisa para entender o projeto e saber onde mexer.
Foi escrito a partir do **código atual da `main`** (não dos documentos antigos de `docs/`,
que têm trechos desatualizados — ver seção 9).

---

## 1. A ideia em uma frase

Mostrar em 3D, em tempo real, o **relevo real da Baixada Santista** com uma **água animada
cuja altura o usuário ajusta**, e medir **a partir de quantos triângulos o LOD (nível de
detalhe) deixa de ser opcional**.

Duas técnicas sustentam isso:

| Técnica | Resolve o quê |
|---|---|
| **CDLOD** (quadtree + morphing) | Desenhar muito detalhe só perto da câmera; longe, poucos triângulos |
| **Ondas de Gerstner** no shader | Água animada sem malha animada; o nível do mar é só um número (uniform) |

---

## 2. Como tudo se encaixa (pipeline)

```
dem.py ──► alturas (matriz 1024×1024, em unidades de mundo)
             │
             ▼  vira textura R32F na GPU (scene.py)
lod.py ──► quadtree (montada 1× no início) ──► a cada frame escolhe os BLOCOS a desenhar
             │                                   (por distância + frustum culling)
             ▼
terrain.vert: pega a grade unitária 33×33, posiciona no mundo, lê a altura da textura,
              faz morphing e calcula a normal
terrain.frag: cor por altitude/inclinação + luz + tom "submerso" abaixo do nível do mar
water.vert:   plano com 6 ondas de Gerstner, altura de base = nível do mar
water.frag:   Blinn-Phong + Fresnel + transparência (α = 0,8)
             │
main.py: janela, teclado, laço  ──►  imagem na tela
bench.py: o mesmo desenho, sem janela, medindo tempo/memória
```

Ideia-chave: **a malha é sempre a mesma grade 33×33**. O que muda por bloco são só o canto,
o tamanho e a profundidade (uniforms). A altura vem da **textura**, não dos vértices.

---

## 3. Mapa de arquivos

| Arquivo | O que faz | Depende de |
|---|---|---|
| `exemplos/janela.py`, `triangulo.py` | Fundamentos: janela, contexto OpenGL, VBO/VAO/shaders | — |
| `src/dem.py` | Baixa tiles de elevação da AWS, limpa *spikes*, reamostra, aplica exagero vertical 6× | NumPy, Pillow |
| `src/heightmap.py` | Terreno procedural (ruído) + **grade unitária** reutilizável + índices de triângulos | NumPy, opensimplex |
| `src/lod.py` | Quadtree, seleção de blocos por distância, **frustum culling vetorizado** | NumPy |
| `src/water.py` | Plano plano de água (as ondas ficam no shader) | `heightmap.grid_indices` |
| `src/shaders/*` | Vertex/fragment do terreno e da água (GLSL 330) | — |
| `src/camera.py` | Câmera livre (yaw/pitch, matrizes view/projection) | PyGLM |
| `src/scene.py` | Classe `Cena`: monta tudo na GPU e desenha **1 frame** | todos acima |
| `src/hud.py` | Texto/painéis 2D (legenda, status, bússola, minimapa) como texturas | Pillow |
| `src/main.py` | Janela GLFW, teclado, laço principal, `Tab`/`F11` | `scene`, `hud`, `camera` |
| `src/bench.py` | Benchmark sem janela: tempo e memória por modo | `scene` |
| `src/area_alagada.py` | Calcula a área emersa que alaga em cada cenário (tabela do artigo) | `dem` |
| `tests/` | 38 testes (culling, memória isolada, benchmark) | — |

`main.py` e `bench.py` usam **a mesma `Cena`** — por isso o benchmark mede exatamente o que o
usuário vê.

---

## 4. Bibliotecas: o papel de cada uma

| Biblioteca | Papel exato no projeto | Por que ela | Alternativa descartada |
|---|---|---|---|
| **GLFW** | Janela, contexto OpenGL, teclado/mouse, V-Sync, tela cheia | Leve e padrão; o ModernGL não cria janela | Pygame/Pyglet (mais pesados) |
| **ModernGL** | Buffers (VBO/IBO), VAO, texturas, shaders, `render()` | OpenGL 3.3 core com API enxuta; também cria contexto **sem janela** (benchmark e testes) | PyOpenGL (verboso) |
| **PyGLM** | `lookAt`, `perspective`, vetores; envia matrizes aos uniforms | É a `glm` do C++ (mesma matemática dos tutoriais) | Escrever matrizes à mão em NumPy |
| **NumPy** | Heightmap, vértices, índices, planos do frustum, máscara do culling | Buffers da GPU são arrays contíguos; vetorização (9 ms → 0,1 ms no culling) | Laços Python |
| **Pillow** | Lê tiles PNG, reamostra o DEM, **desenha o texto da HUD** | OpenGL não renderiza texto; reaproveita a mesma lib | FreeType/imgui |
| **opensimplex** | Ruído do terreno procedural | Puro Python, sem compilar | Perlin próprio |
| **matplotlib** | Gráficos do benchmark | Padrão para figuras do artigo | — |
| **psutil** | RAM/pico por processo no `--memoria` | Cross-platform | — |
| **unittest** (stdlib) | 38 testes, sem pytest | Sem dependência extra | pytest |

Sem GDAL/rasterio: o DEM vem em PNG *terrarium*, com `elev = R·256 + G + B/256 − 32768`.

**Padrão de uso do OpenGL no projeto:** (1) cria o buffer uma vez; (2) a cada frame só troca
**uniforms** (matrizes, tempo, nível do mar, offset do bloco) e chama `render()`.
Por isso o custo por quadro é dominado por **quantas chamadas** (`draw calls`) o Python faz.

---

## 5. Os conceitos que importam

### 5.1 Heightmap + displacement
O terreno é uma **textura de alturas** (R32F). O vertex shader pega um vértice da grade plana
e o **empurra para cima** pela altura lida. Vantagem: a malha é barata e reutilizável;
a resolução do dado (1024²) é independente da quantidade de triângulos.

### 5.2 CDLOD (o LOD que usamos)
- **Quadtree** com 5 níveis → até 1365 nós (1+4+16+64+256+1024), montada **uma vez**.
- A cada frame, `select()` desce a árvore: se a câmera está a menos de `tamanho × 2,2` da
  **borda** do bloco, troca o bloco pelos 4 filhos; senão desenha o bloco.
- Resultado: blocos pequenos perto, grandes longe; ~100 a 184 blocos por quadro.
- **Morphing:** perto do limite do alcance de um bloco, os vértices "ímpares" deslizam até
  a posição dos "pares". Assim a borda do bloco fino coincide com a do grosso ao lado:
  **sem frestas (cracks) e sem "pop"** na troca de nível. Custo medido: desprezível.

### 5.3 Frustum culling (nossa extensão)
Cada nó vira uma **caixa** (AABB): XZ vem da quadtree, `[y_min, y_max]` vem do heightmap.
Se a caixa está inteira fora de algum dos 6 planos da câmera, o bloco **e seus filhos**
são podados. Calculado em NumPy para todos os 1365 nós de uma vez (~0,1 ms; em laço Python
seria ~9 ms). É conservador: uma caixa que só encosta no campo de visão é mantida, então a
**imagem é idêntica** com ou sem culling (testado). Tecla `C`; vem desligado por padrão para
as medições antigas continuarem reproduzíveis.

### 5.4 Ondas de Gerstner
Cada partícula descreve um **círculo**: além de subir, é empurrada na horizontal. Resultado:
crista afiada e vale largo. **6 ondas** somadas (direção, amplitude, comprimento, velocidade,
*steepness*); a normal é calculada **analiticamente**. O nível do mar é só `u_sea_level`
somado à altura de base — por isso é fácil animar e ajustar.

### 5.5 Iluminação e cor
Lambert (difuso) no terreno; Blinn-Phong (brilho do sol) + Fresnel (reflexo de raspão) na água.
Terreno abaixo de `u_sea_level` recebe um tom verde-escuro mais forte quanto mais fundo — é
**a parte que mostra o que alaga**.

---

## 5A. Como as ondas são desenhadas (passo a passo)

**Onde:** `water.py` cria só uma grade plana (256×256 vértices, 480 u de lado = 1,6 × o terreno).
**Quem faz a onda:** o `water.vert`, 1× por vértice, a cada frame. A CPU não toca na malha.

Para cada um dos 6 componentes `i` e cada vértice com posição `xz`:

```
w     = 2π / λᵢ                       frequência espacial
θ     = w · (Dᵢ · xz) + (vᵢ · w) · t  fase (D = direção, v = velocidade, t = tempo)
Q     = steepᵢ / (w · Aᵢ · 6)         "pontudez" normalizada

pos.x += Q · A · Dx · cos θ           ← empurrão horizontal (é o que faz Gerstner ≠ seno)
pos.z += Q · A · Dz · cos θ
pos.y += A · sin θ                    ← sobe e desce
```

Depois soma-se tudo e a **normal sai analítica** (derivadas), sem olhar vizinhos:

```
n.x = −Σ Dx·w·A·cos θ     n.z = −Σ Dz·w·A·cos θ     n.y = 1 − Σ Q·w·A·sin θ
```

**Por que o Q é dividido por (w·A·6):** o termo Q·w·A de cada onda vira `steep/6`, e a soma
das 6 fica < 1. Isso garante que as cristas **não se cruzem** (laços na superfície). É o limite
clássico das ondas de Gerstner.

**Os 6 componentes** (direções, λ, A, velocidade, pontudez — tabela do `water.vert`):

| Onda | λ (u) | Amplitude (u) | Velocidade | Papel visual |
|---|---|---|---|---|
| 1 | 70 | 1,10 | 8,5 | Marulho longo |
| 2 | 48 | 0,90 | 7,0 | Ondulação principal |
| 3 | 26 | 0,50 | 5,5 | Média |
| 4 | 14 | 0,28 | 4,0 | Detalhe |
| 5 | 7 | 0,14 | 3,0 | Textura fina |
| 6 | 4 | 0,07 | 2,2 | Respingo |

Direções diferentes + comprimentos diferentes = o mar não parece repetir.

**Depois do vértice, no pixel (`water.frag`):**
1. **Difuso** (Lambert): `max(n·L, 0)` escolhe entre azul fundo e azul claro.
2. **Fresnel** (Schlick): `0,02 + 0,98·(1 − n·V)⁵` — olhando de raspão vira espelho do céu.
3. **Especular** (Blinn-Phong): `(n·H)⁹⁰` — o ponto brilhante do sol.
4. **Alpha 0,8** com *blending* ligado só durante a água: dá para ver o terreno por baixo.

**Ordem de desenho:** terreno primeiro (opaco), água por último (translúcida). Água translúcida
precisa vir depois do que está atrás dela.

**O que é artístico, não físico:** velocidades e amplitudes foram escolhidas à mão (não seguem
a relação de dispersão `c = √(gλ/2π)`) e estão em unidades de mundo, não em metros.

**Duas observações honestas (úteis para melhorar):**
- A malha da água tem ~1,9 u por célula; as ondas de λ = 4 e 7 u ficam com ~2 a 4 vértices por
  ciclo, perto do limite de amostragem. Mais resolução (`resolucao_agua`) ou LOD na água melhoraria o detalhe fino.
- 1 m de mar vale ≈ 0,036 u (ver 5B), então +2 m ≈ 0,07 u, enquanto as ondas somam até ~3 u de
  amplitude. Visualmente, **as ondas são muito maiores que a diferença entre os cenários**;
  quem mostra de verdade o que alaga é a faixa submersa do terreno, não a crista da água.

---

## 5B. Como o cenário é modelado

**Etapa 1 — dado.** `dem.py` baixa os tiles PNG (zoom 11) que cobrem lat −23,70…−24,10 e
lon −46,60…−46,05 (~56 × 44 km), decodifica `R·256 + G + B/256 − 32768` → metros.

**Etapa 2 — limpeza.** Mediana 3×3 para remover *spikes* (limiar de 60 m, 2 passadas) e `clip` com
`piso_metros` (o oceano fundo vira piso, para não estourar a escala de cor).

**Etapa 3 — escala.**
```
extensao_m        = média(largura_m, altura_m) da bbox ≈ 50 km
unidades_por_metro = (300 / extensao_m) · 6        ≈ 0,036 u/m
alturas (u)       = elevação_m · unidades_por_metro
```
- O **6×** é o exagero vertical (declarado). Sem ele a Serra do Mar (razão ~40:1) vira lombada.
- Esse mesmo fator converte "mar +X m" em unidades de mundo → é como as teclas 1–4 funcionam.
- O recorte retangular (~56 × 44 km) é reamostrado para **1024 × 1024** e mapeado num mundo
  **quadrado** de 300 × 300 u; a escala horizontal é a média das duas dimensões, então há uma
  pequena distorção de proporção (~1,27 entre eixos). É uma simplificação a declarar se perguntarem.

**Etapa 4 — GPU.** As alturas viram uma textura R32F (1 float por texel, filtro linear). O terreno
não guarda altura nos vértices: guarda uma grade 0–1 e **lê a altura da textura no shader**.

**Etapa 5 — geometria.** Quadtree (5 níveis) + a mesma grade 33×33 para todo bloco. Os uniforms
`u_node_offset`, `u_node_scale` e `u_node_level` dizem onde cada cópia fica e que tamanho tem.

**Etapa 6 — normal e cor (`terrain.frag`/`.vert`):**
- Normal por diferenças finitas a ~2,5 texels: `n = normalize(hL−hR, 2e, hD−hU)`.
- Cor por altitude normalizada `h = altura / altura_ref`:
  areia/restinga (h<0,04) → mata (até 0,55) → mata densa → rocha nos cumes.
- Rocha também onde é íngreme (`1 − n.y`): a escarpa da Serra aparece como parede.
- Luz: Lambert com `0,25 + 0,85·difuso` (nada fica preto). Sol vindo de `(−0,5, −1, −0,3)`.
- **Faixa submersa:** `altura < u_sea_level` → mistura 65% com verde-escuro, mais forte quanto
  mais fundo (escala de 10 u). **É a visualização do alagamento.**
- Névoa: de 120 a 380 u, mistura até 75% com a cor do céu → dá escala e esconde o fim do mundo.

**Terreno procedural** (alternativa sem internet): ruído OpenSimplex, 5 oitavas (fBm), mesma
interface. Serve para testes e para o benchmark ficar independente do DEM.

---

## 5C. Onde está a Computação Gráfica (mapa conceito → código)

| Conceito de CG | Onde aparece | Observação |
|---|---|---|
| Pipeline programável (vertex → raster → fragment) | `shaders/*` | Terreno e água são dois programas |
| Transformações (modelo, vista, projeção) | `camera.py`, `u_view`/`u_proj` | Perspectiva FOV 60° |
| Espaços de coordenadas | mundo [−150,150]; UV [0,1]; clip | `mundo/size + 0.5` converte mundo→UV |
| Malha indexada | `grid_indices` | 2 triângulos por célula |
| Textura como dado (não como cor) | heightmap R32F | *Displacement mapping* |
| Filtro linear de textura | altura suave entre texels | Por isso a caixa do culling tem margem |
| Iluminação local | Lambert, Blinn-Phong | Sem sombras projetadas, sem GI |
| Fresnel (Schlick) | `water.frag` | Reflexo cresce no raspão |
| Normais (diferenças finitas × analítica) | terreno × água | Dois jeitos de obter normal |
| Mistura (*alpha blending*) | água | Ordem importa |
| Teste de profundidade (Z-buffer) | padrão do OpenGL | Terreno/água se ocultam corretamente |
| Névoa | `terrain.frag` | Atenuação por distância |
| LOD | `lod.py` + morph | O tema do Eixo 6 |
| *Frustum culling* (AABB × 6 planos) | `lod.py` | Gribb–Hartmann |
| Instrumentação de desempenho | `bench.py` | Tempo por quadro, memória, triângulos |

Resumo da aplicação: **CG aqui é ferramenta de análise** — o objetivo é transformar um DEM em uma
cena 3D navegável onde a altura da água é uma variável de cenário, e medir o custo.

---

## 5D. Relação com os trabalhos citados

| Trabalho | O que propõe | O que aproveitamos | O que NÃO fazemos |
|---|---|---|---|
| **Tanner, Migdal & Jones (1998)** — *The Clipmap* | Janelas de dados em resolução decrescente ao redor do observador | A ideia central: detalhe concentrado perto da câmera | Não guardamos anéis/janelas de textura; só um heightmap 1024² único |
| **Clasen & Hege (2006)** — clipmaps esféricos | Mesma ideia em esfera, para planetas | Referência de LOD em escala grande | Não precisamos de esfera: o recorte tem ~50 km, é plano |
| **Strugar (2009)** — CDLOD | Quadtree + distância contínua + *geomorphing* | **É o algoritmo realmente implementado** (quadtree, seleção por distância, morph no vertex shader) | Versão simplificada: faixas de morph baseadas em `size × 2,2`; sem oclusão |
| **Fournier & Reeves (1986)** — ondas de Gerstner | Modelo procedural de ondas, inclusive zona costeira | **A matemática da água** (6 componentes somados) | Sem quebra de onda na praia nem interação com o relevo |
| **Welch (2019)** — *Real-time ocean simulation* | Oceano em tempo real com Gerstner em GLSL, PBR, espuma | Prova de que Gerstner no vertex shader roda em tempo real | Sem PBR, sem espuma; **nosso diferencial: nível médio ajustável** |
| **Brown et al. (2006)** — erosão costeira | Visualizar linhas de costa em evolução com DEM + SIG | Motivação e escolha do cenário | Não modelamos erosão em si, só a subida do nível |
| **DiPaola, Bhardwaj & Sam (2023)** — SLR em Vancouver | Mapas 2D interativos com LiDAR e % de área afetada | Motivação e a ideia de "% de área alagada" (`area_alagada.py`) | Não usamos LiDAR; usamos SRTM (menos preciso) |

**Posicionamento em uma frase:** não inventamos técnica nova; **integramos** terreno com LOD (Strugar)
e água procedural (Fournier & Reeves / Welch) num cenário ambiental, com o nível do mar como
parâmetro, e **medimos** a partir de quantos triângulos o LOD compensa.

**Lacuna que justifica o trabalho** (do próprio artigo): nenhum dos trabalhos de ondas trata o nível
médio como variável de cenário, e nenhum dos de geovisualização simula a superfície da água em 3D.

**Nota:** o ano correto de Strugar (via DOI) é **2009**; os comentários do código já foram corrigidos.

---

## 6. Um frame, do começo ao fim

1. `main.py` lê teclado/mouse e atualiza a `Camera` (com `dt`).
2. A câmera gera as matrizes `view` e `projection`.
3. `Cena.desenhar()`:
   - (opcional) `nos_visiveis()` calcula a máscara do culling;
   - `lod.select()` escolhe os blocos;
   - **1 draw call por bloco**, passando canto/tamanho/profundidade/faixa de morph;
   - sem LOD: 1 draw call numa malha única (modo "ingênuo", só para comparação);
   - desenha a água por último, com *blending*.
4. A HUD desenha seus quads em espaço de tela.
5. `swap_buffers` mostra o quadro.

`desenhar()` devolve `EstatisticasFrame` (blocos, draw calls, triângulos, nós podados) — é o
que o benchmark registra.

---

## 7. Decisões de projeto e por quê

| Decisão | Motivo |
|---|---|
| **Quadtree (CDLOD) em vez de clipmap esférico** | O clipmap esférico resolve a curvatura da Terra; nosso recorte (~50 km) é plano. Mantemos o *princípio* (detalhe decrescente com a distância) sem a complexidade esférica |
| **Textura R32F + grade unitária** | Malha pequena e reaproveitável; a altura sai do dado, não do vértice |
| **DEM via PNG da AWS** | Sem chave de API, sem GDAL |
| **Exagero vertical de 6×** | Razão relevo:largura ≈ 40:1; sem exagero a Serra do Mar vira lombada. **Declarado** no artigo |
| **Cena com `construir_lod` / `construir_ingenuo`** | Cada modo só aloca a malha que usa — base da medição de memória isolada |
| **Culling desligado por padrão** | Preserva a reprodutibilidade dos dados do artigo |
| **Culling em NumPy** | 9 ms → 0,1 ms; o quadro inteiro leva ~1 ms |
| **Água maior que o terreno (1,6×)** | Chega ao horizonte sem "acabar" na tela |

---

## 8. Números para guardar

**Parâmetros** (código): quadtree 5 níveis · 33×33 vértices por bloco · divide se
distância < tamanho × 2,2 · 6 ondas · FOV 60° · velocidade 40 u/s (120 com Shift) ·
heightmap 1024² · mundo 300 u · água 256×256 · cenários 0 / +0,5 / +1 / +2 m (e 5/10/20 m só para demonstração).

**Resultados** (RTX 3060, 3 execuções extras):
- CDLOD fica em ~1 ms por quadro em qualquer resolução (~0,4 M triângulos).
- Malha sem LOD cresce linearmente e **cruza o CDLOD em ~4 M de triângulos** (2,7 a 4,3 M conforme o critério e a execução).
- **Culling:** −22% de tempo de quadro em média (rasante −33%, encosta −38%, horizonte −7%, aérea ≈ 0%); blocos 100–184 → 52–73; ponto de virada → **~2,3 M**.
- **Memória a 2048²:** malha 19 MB (CDLOD) × 153 MB (completa); pico de RAM 191 × 595 MB.
- O ~1 ms do CDLOD é **overhead de CPU** (percorrer a árvore + draw calls em Python), não GPU.

---

## 9. Atenção: documentos antigos em `docs/`

`APRESENTACAO.md` e `COMPLEMENTO_TECNICO.md` foram escritos antes das últimas mudanças. Não confie neles em:
- "sem frustum culling" → **já existe** (seção 5.3);
- "4 ondas de Gerstner" → são **6**;
- "RAM e VRAM não diferem por modo" → só na medição antiga; a **medição isolada** mostra 19 × 153 MB;
- ponto de virada "1024²–1536², 2,7–4,2 M" → ver seção 8;
- `build_mesh` em `heightmap.py` → **foi removida** (código morto);
- "Welch — GPU Clipmaps…" → o título real é *Real-time ocean simulation* (2019).

Fonte da verdade para parâmetros: `docs/metodologia_atual.md` e o próprio código.

---

## 10. Limitações (para saber responder)

1. CDLOD **simplificado**: faixas de morph não seguem exatamente as fórmulas de Strugar; culling sem oclusão.
2. Benchmark em **uma GPU de desktop**.
3. Água **não interage** com o terreno (sem espuma/refração).
4. Exatidão vertical do DEM **não validada**; se for da ordem de +0,5 a +2 m, a área alagada é demonstração, não previsão.
5. Poucas execuções, sem intervalo de confiança; o ponto de virada foi interpolado entre duas resoluções.

---

## 11. Onde mexer, conforme a ideia

| Quero… | Mexa em |
|---|---|
| Outra região ou outra fonte de dados | `dem.py` (`BAIXADA_SANTISTA`, `zoom`, `exagero_vertical`) |
| Mais ou menos detalhe | `scene.py` (`lod_profundidade`, `lod_subdivisoes`, `lod_fator_split`) |
| Água mais realista (espuma, refração) | `shaders/water.*` |
| Cor/aparência do terreno, mostrar erosão | `shaders/terrain.frag` |
| Interação água × terreno | `terrain.frag` (faixa submersa) + `scene.py` |
| Novos cenários de mar | `main.py` (`CENARIOS_MAR`) |
| Mudar o mar (altura, velocidade, pontudez das ondas) | arrays `AMP`, `LAMBDA`, `SPEED`, `STEEP`, `DIR` em `water.vert` |
| Água mais fina nas ondas curtas | `resolucao_agua` em `scene.py` |
| Ondas proporcionais ao mar real (em metros) | escalar `AMP` por `unidades_por_metro` |
| Mudar luz/horário | `DIRECAO_LUZ` em `scene.py` |
| Névoa e cor do céu | `terrain.frag` (120/260, `c_ceu`) |
| Novo painel ou legenda | `hud.py` |
| Novo teste ou medição | `bench.py`, `tests/` |
| Rodar em outras GPUs (inclusive integradas) | `bench.py` (sem mudar código: só rodar) |

---

## 12. Ordem sugerida de leitura do código

`exemplos/janela.py` → `triangulo.py` → `camera.py` → `heightmap.py` → `dem.py` → `lod.py` →
`shaders/terrain.vert` → `terrain.frag` → `water.py` + `water.vert` → `scene.py` → `main.py` →
`bench.py` → `tests/`.

Cada arquivo tem comentários em português explicando o **porquê**, não só o quê.
