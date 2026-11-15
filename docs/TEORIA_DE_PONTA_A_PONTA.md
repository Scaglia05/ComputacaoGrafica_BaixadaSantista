# Teoria de ponta a ponta

Guia de estudo pragmático: como cada parte funciona e por que cada decisão foi tomada. Todos os valores vêm do código em `src/` (conferidos). Onde a decisão foi uma simplificação ou escolha manual, isso está dito.

Leitura sugerida: seções 1 a 3 dão o mapa; 4 a 7 são o núcleo técnico; 8 e 9 são o que o artigo mede; 10 e 11 preparam a defesa.

## Sumário

1. [O problema e a ideia geral](#1-o-problema-e-a-ideia-geral)
2. [Base mínima de GPU](#2-base-mínima-de-gpu)
3. [Dados: do satélite ao heightmap](#3-dados-do-satélite-ao-heightmap)
4. [Terreno na GPU](#4-terreno-na-gpu)
5. [CDLOD: nível de detalhe por distância](#5-cdlod-nível-de-detalhe-por-distância)
6. [Frustum culling](#6-frustum-culling)
7. [Água: ondas de Gerstner](#7-água-ondas-de-gerstner)
8. [Câmera, projeção e o nível do mar](#8-câmera-projeção-e-o-nível-do-mar)
9. [Benchmark: o que foi medido e como](#9-benchmark-o-que-foi-medido-e-como)
10. [Tabela de decisões](#10-tabela-de-decisões)
11. [Limitações e perguntas prováveis](#11-limitações-e-perguntas-prováveis)

---

## 1. O problema e a ideia geral

**Objetivo.** Mostrar em 3D, em tempo real, quais áreas da Baixada Santista ficam sob a água quando o nível do mar sobe (0, +0,5, +1, +2 m).

**Dificuldade.** O terreno real vira uma malha enorme. Com o DEM em 2048×2048, a malha completa tem 8.388.608 triângulos. Desenhar tudo em alta resolução, o tempo todo, é desperdício: longe da câmera um triângulo ocupa menos de um pixel.

**Solução.** CDLOD (*Continuous Distance-Dependent Level of Detail*, Strugar, 2009): blocos pequenos e detalhados perto da câmera, blocos grandes e simples longe, com transição suave entre eles.

**Pipeline por quadro** (`Cena.desenhar` em `src/scene.py`):

```
câmera → seleciona blocos (quadtree, por distância) → [opcional: descarta os fora da tela]
       → para cada bloco: desenha a MESMA grade 33×33, posicionada e esticada pelo shader
       → vertex shader lê a altura na textura e aplica o morphing
       → desenha o plano de água (ondas calculadas no vertex shader), translúcido
```

**Por que Python é suficiente.** A parte pesada (milhões de vértices e pixels) roda na GPU, em shaders. Python só escolhe os blocos e dispara de 50 a 200 chamadas de desenho por quadro.

---

## 2. Base mínima de GPU

Só o necessário para entender o resto.

| Conceito | O que é | Onde aparece |
|---|---|---|
| **Vertex shader** | Programa que roda uma vez por vértice e decide a posição final na tela | `terrain.vert`, `water.vert` |
| **Fragment shader** | Programa que roda uma vez por pixel coberto e decide a cor | `terrain.frag`, `water.frag` |
| **VBO / VAO / IBO** | Vértices na memória da GPU / como lê-los / índices que ligam vértices em triângulos | `Cena._grade` |
| **Uniform** | Valor igual para todos os vértices de uma chamada (câmera, offset do bloco, nível do mar) | `self.prog[...]` |
| **Textura** | Imagem na GPU, que o shader pode amostrar; aqui guarda as alturas | `u_heightmap` |
| **Draw call** | Uma ordem de desenho enviada da CPU à GPU; tem custo fixo em CPU | uma por bloco |
| **Matrizes view e proj** | `view` leva o mundo ao referencial da câmera; `proj` aplica a perspectiva | `camera.py` |

**Por que importa:** o gargalo medido é a CPU (muitas draw calls em Python), não a GPU. Isso explica o resultado do benchmark (seção 9).

---

## 3. Dados: do satélite ao heightmap

Arquivo: `src/dem.py`.

**Fonte.** AWS Terrain Tiles, formato *terrarium*: PNGs em que a elevação fica codificada nas cores.

```
elev (m) = R·256 + G + B/256 − 32768
```

Dados primários: NASA SRTM em terra (cerca de 30 m) e GEBCO no mar. Por isso há valores negativos na água. Isso é útil: ao subir o nível do mar, ele preenche o relevo submarino real.

**Por que essa fonte.** Não exige chave de API e é PNG comum (Pillow lê). Alternativas como `rasterio`/GDAL foram descartadas por instabilidade de instalação no Windows.

**Região.** Latitude −23,70 a −24,10, longitude −46,60 a −46,05 (cerca de 56 × 44 km). É mais larga que um recorte só de Cubatão porque precisa incluir a escarpa da Serra do Mar e o estuário e o oceano, senão a inundação não faz sentido.

**Etapas e motivo de cada uma:**

| Etapa | O que faz | Por quê |
|---|---|---|
| Mosaico de tiles (zoom 11) | Baixa, cacheia e cola os PNGs; recorta na caixa exata | Os tiles inteiros cobrem um pouco mais que a região |
| Remoção de *spikes* | Mediana 3×3, 2 passadas, limiar de 60 m | Dados de radar têm pixels absurdos perto de água e bordas de tile; viram "agulhas" no relevo |
| Piso em −40 m | `np.clip(elev, −40, None)` | Abaixo disso está tudo submerso de qualquer forma; evita que o oceano profundo estrague a normalização das cores |
| Reamostragem bilinear para 1024² | Uniformiza o tamanho | A GPU precisa de uma textura quadrada de tamanho fixo |

**Escala (o ponto mais cobrado).** O mundo da cena tem 300 unidades (u.m.) de lado:

```
extensão horizontal ≈ média(56,0 km ; 44,2 km) ≈ 50,1 km
1 u.m. horizontal ≈ 167 m
unidades_por_metro = (300 / extensão_m) × 6 ≈ 0,03593 u.m./m   (já inclui o exagero vertical)
```

**Exagero vertical de 6×.** A região tem 50 km de largura para cerca de 1,2 km de relevo (razão perto de 40:1). Sem exagero, a Serra do Mar vira uma lombada. 6× deixa a escarpa legível. É prática comum em geovisualização e **deve ser declarado** (o artigo declara). Consequência: o mundo é verticalmente esticado, e 1 u.m. na vertical vale cerca de 27,8 m reais.

**Cenários em metros reais.** O nível do mar é guardado em u.m.: `nivel = metros × unidades_por_metro`. Assim, +2 m vale cerca de 0,072 u.m. O exagero multiplica altura do terreno e nível da água igualmente, então a **relação entre eles** (o que fica submerso) continua correta em metros.

**Área alagada** (`src/area_alagada.py`): conta, no DEM, as células emersas (elevação ≥ 0) abaixo de cada nível. Resultado da execução de verificação: 1927 km² emersos; +0,5 m alaga 119,4 km² (6,2%), +1 m 127,7 km², +2 m 143,5 km². Atenção: cerca de 104,6 km² são células com elevação exatamente 0 (provavelmente corpos d'água do produto de origem), que "alagam" assim que o nível passa de zero; por isso o script informa também a coluna sem elas.

---

## 4. Terreno na GPU

**Textura de altura.** A matriz 1024×1024 de alturas sobe como textura de 1 canal (R32F, 4 bytes por texel, filtro bilinear). O bilinear faz a GPU interpolar entre texels, dando altura contínua.

**Displacement mapping, sem malha fixa.** Não existe uma malha com um vértice por texel. Existe **uma única grade unitária** de 33×33 vértices em [0,1]² (`build_unit_grid`, 32×32 células, 2048 triângulos). Para cada bloco, o shader recebe o canto e o tamanho:

```
xz = u_node_offset + g · u_node_scale       (posição no mundo)
h  = texture(u_heightmap, xz/world_size + 0.5).r   (altura lida da textura)
```

**Por quê:** uma só grade serve a todos os blocos, em todos os níveis. Poupa memória (a malha do CDLOD tem poucos KB) e permite trocar o nível de detalhe só mudando dois uniforms.

**Normal.** Calculada no shader por diferenças finitas, amostrando 4 vizinhos a 2,5 texels de distância: `n = normalize(hL − hR, 2e, hD − hU)`. O afastamento de 2,5 texels alisa o ruído do heightmap, que daria um relevo "granulado" na iluminação.

**Cor** (`terrain.frag`):
- Por altitude normalizada `h = altura / altura_máxima`: areia (restinga) < 0,04; Mata Atlântica até 0,55; rocha acima.
- Por inclinação: `declive = (1 − n.y)·2,2` força rocha exposta nas escarpas íngremes, independente da altitude.
- Iluminação de Lambert (`0,25 + 0,85·difuso`: o ambiente 0,25 evita preto total na sombra).
- Névoa de distância: mistura com a cor do céu entre 120 e 380 unidades, dando sensação de escala.
- **Faixa submersa:** terreno abaixo de `u_sea_level` ganha tom verde-escuro, mais forte quanto mais fundo (profundidade normalizada por 10 u.m. ≈ 278 m). Esse é o realce do objetivo do projeto.

---

## 5. CDLOD: nível de detalhe por distância

Arquivo: `src/lod.py`. É o coração do trabalho.

### 5.1 Quadtree

O terreno inteiro é a raiz. Cada bloco se divide em 4 filhos de metade do lado, até a profundidade 5.

- Número de nós: 1 + 4 + 16 + 64 + 256 + 1024 = **1365**.
- Os 1024 blocos da base (folhas) têm 300/32 ≈ 9,4 u.m. de lado.
- A árvore é montada **uma vez**, na inicialização.

### 5.2 Seleção por distância

A cada quadro, desce-se da raiz:

```
se o bloco tem filhos  E  distância(câmera, borda do bloco) < tamanho × 2,2:
    desce para os 4 filhos          (mais detalhe)
senão:
    desenha este bloco
```

**Por que "distância até a borda" e não até o centro.** Com o centro, um bloco grande e próximo deixaria de se dividir só porque o centro dele está longe. A distância é medida no plano horizontal (XZ), `_dist_para_bloco`.

**Por que o alcance é proporcional ao tamanho (fator 2,2).** Como o tamanho dobra a cada nível acima, o alcance dobra também. Isso equivale ao esquema de raios por nível do artigo original (raio base com duplicação), mas sem tabela. O fator 2,2 é o valor adotado; não há estudo de sensibilidade registrado. Com ele, a cena tem cerca de 100 a 184 blocos por quadro (52 a 74 com culling). Fator menor gera menos triângulos e um LOD mais agressivo; maior, o contrário.

**Resultado.** Muitos blocos pequenos perto, poucos grandes ao longe, todos com a mesma grade 33×33. Por isso o custo fica em torno de 0,4 M triângulos por quadro **independentemente da resolução do DEM**: o DEM só muda a textura, não a quantidade de blocos.

### 5.3 O problema das fendas (cracks)

Um bloco detalhado ao lado de um bloco simples tem mais vértices na borda comum. Os vértices extras ficam fora da reta do bloco simples e deixam um buraco por onde se vê o céu.

### 5.4 Morphing (a solução)

Perto do limite externo do alcance de um bloco, os vértices de **índice ímpar** deslizam para o **vizinho par** de índice menor. No limite, a borda do bloco detalhado tem o mesmo espaçamento da borda do bloco grosso ao lado, e as duas malhas coincidem.

No shader (`terrain.vert`):

```
resto = fract(g · N · 0,5) · 2 / N      → vale 1/N para vértices ímpares, 0 para pares
g_morph = g − resto · k                  → k = 0: posição própria; k = 1: grade grossa
```

O fator `k` cresce linearmente de 0 a 1 com a distância do vértice à câmera:

```
k = clamp((dist − morph_start) / (morph_end − morph_start), 0, 1)
```

**De onde vêm os limites.** Um bloco de tamanho S é desenhado quando a distância está entre `r = 2,2·S` (abaixo disso ele se divide) e `2r` (acima disso o pai assume). A transição começa a 55% desse intervalo:

```
morph_start = r + 0,55·(2r − r) = 1,55·r        morph_end = 2r
```

Assim, quando o pai assume em `2r`, o filho já está completamente "achatado" na grade do pai e **não há salto visível** (*popping*).

**Decisão importante: distância horizontal.** O morphing usa `distance(camera.xz, vértice.xz)`, a mesma métrica da seleção. Antes usava distância 3D; numa vista aérea (câmera alta) isso fazia todos os blocos chegarem já "morphados" só pela altura da câmera.

**Evidência medida.** Em 40 câmeras aleatórias, as fendas finas (1 a 3 px de céu entre terreno, ausentes na malha completa) somaram **512 sem morphing e 1 com ele** (`python src/verificar_fendas.py`). O custo do morphing ficou dentro do ruído (no máximo 0,06 ms).

**Limites (declarados no artigo).** A faixa de morphing não segue exatamente as fórmulas do Strugar. A seleção usa a distância à borda do bloco e o morphing, a distância ao vértice, o que pode deixar uma fenda residual (a que sobrou nas medições). A contagem detecta só fendas verticais e o popping não foi medido.

---

## 6. Frustum culling

Arquivo: `src/lod.py` (funções `planos_do_frustum`, `nos_visiveis`).

**Ideia.** A seleção só olha distância; blocos atrás da câmera eram desenhados à toa. O culling descarta blocos fora do campo de visão.

**Como.**
1. Cada bloco vira uma **caixa** (AABB): o lado em XZ vem da quadtree e a faixa vertical `[y_min, y_max]` vem do heightmap (calculada uma vez, na inicialização).
2. O **frustum** (a pirâmide de visão) é descrito por 6 planos (esquerda, direita, baixo, cima, near, far), obtidos da matriz `proj × view` pelo **método de Gribb-Hartmann** (somas e diferenças de linhas da matriz).
3. Para cada plano, testa-se o **canto da caixa mais "para dentro"** do plano. Se até esse canto está fora, a caixa inteira está fora.
4. Um nó podado leva a subárvore junto (a caixa dos filhos cabe na do pai).

**Propriedades que importam:**
- **Conservador:** uma caixa que só encosta no frustum fica como visível. O pior caso é desenhar um bloco a mais, nunca um a menos. Por isso a imagem é **idêntica pixel a pixel** com e sem culling (testado em 4 + 40 câmeras).
- **Margem de 2 texels** nas caixas: a GPU amostra a textura com filtro linear, então um vértice na borda "puxa" a altura de texels vizinhos que estão fora do bloco. Sem a margem, a caixa podia ficar um pouco baixa ou alta e descartar um bloco visível.
- **Vetorizado em NumPy:** testar os 1365 nós em laço Python custa cerca de 7,7 ms por quadro; em NumPy, todos de uma vez, cerca de 0,11 ms. Como o quadro inteiro leva cerca de 1 ms, o laço Python anularia o ganho.

**Resultado medido.** O culling reduz o tempo de quadro em média 22% (1,12 → 0,88 ms): −37% nas câmeras rasante e de encosta, −6% no horizonte, 0% na aérea (que enquadra quase todo o terreno). O ganho depende de para onde a câmera olha.

---

## 7. Água: ondas de Gerstner

Arquivos: `src/water.py`, `src/shaders/water.vert`, `water.frag`.

**Geometria.** Um plano de 256×256 vértices (130.050 triângulos), de **480 u.m. de lado** (1,6 × o terreno), para a água alcançar o horizonte sem terminar dentro do campo de visão. As ondas não estão na malha: o *vertex shader* as calcula a cada quadro.

**Por que Gerstner e não só seno.** Uma onda de Gerstner move o ponto também na horizontal, em círculo, o que dá cristas afiadas e cavados largos, como no mar real. Um seno só sobe e desce e fica "borrachudo".

**Equação.** Para cada onda `i`, com direção `D_i` (no plano XZ), amplitude `A`, número de onda `k = 2π/λ` e velocidade de fase `c`:

```
θ = k · (D·xz) − ω·t,        ω = c·k
x += Q·A·D.x·cos θ
z += Q·A·D.z·cos θ
y += A·sin θ
```

O sinal em `θ = k·x − ωt` faz a onda **avançar** no sentido de `D` (com `+ωt` ela andaria para trás).

**Seis ondas (marulho longo → respingo curto):**

| Onda | Amplitude | λ (u.m.) | Velocidade | Nitidez bruta s |
|---|---|---|---|---|
| 1 | 1,10 | 70 | 8,5 | 0,60 |
| 2 | 0,90 | 48 | 7,0 | 0,55 |
| 3 | 0,50 | 26 | 5,5 | 0,50 |
| 4 | 0,28 | 14 | 4,0 | 0,42 |
| 5 | 0,14 | 7 | 3,0 | 0,35 |
| 6 | 0,07 | 4 | 2,2 | 0,28 |

Somar ondas de tamanhos e direções diferentes evita a aparência repetitiva. As 6 direções são fixas e distribuídas pelo círculo.

**Nitidez e a condição de não se auto-cruzar.** Um parâmetro `Q` alto afia a crista; se passar do limite, a superfície forma laços (a crista "dobra sobre si mesma"). O limite clássico é `Σ Q_i·k_i·A_i ≤ 1`. O código define `Q_i = s_i / (k_i·A_i·N)`, com `N = 6`. Assim `Σ Q_i·k_i·A_i = média(s_i) = 0,45 < 1`. Os `Q_i` efetivos valem cerca de 1,01 / 0,78 / 0,69 / 0,56 / 0,46 / 0,42. A nitidez é **decrescente** com a frequência: ondas curtas são mais fáceis de dobrar.

**Normal analítica.** Calculada a partir das derivadas da soma das ondas, não por diferenças finitas: é exata e mais barata.

**Cor** (`water.frag`):
- **Lambert** (difuso) e **Blinn-Phong** (brilho do sol, expoente 90).
- **Fresnel de Schlick:** `F = 0,02 + 0,98·(1 − n·v)^5`. Olhando de raspão a água vira espelho do céu; olhando de cima, deixa ver o fundo.
- **Transparência** (alfa 0,80): dá para ver o terreno submerso por baixo, que é o objetivo do projeto.

**Honestidade sobre a física.** As velocidades de fase foram escolhidas à mão, não derivadas da relação de dispersão da água (`ω² = g·k`). O modelo é visual, não uma simulação oceanográfica. A água também não interage com o terreno (sem espuma nem arrebentação).

**O nível do mar** entra como a altura de base `u_sea_level` do plano; as ondas oscilam em torno dela.

---

## 8. Câmera, projeção e o nível do mar

Arquivo: `src/camera.py`.

- **Câmera livre:** `yaw` (olhar para os lados) e `pitch` (cima e baixo, limitado a ±89° para não "capotar"); o vetor frente sai de `yaw` e `pitch`. Sensibilidade do mouse 0,12°/pixel.
- **Projeção (fonte única):** FOV vertical 60°, plano próximo 0,1, plano distante 2000. As três constantes ficam em `camera.py` e são usadas pela aplicação, pelo benchmark e pelos testes, para que a medição e o uso real enxerguem a mesma cena.
- **Velocidade:** 40 u.m./s (120 com Shift).
- **Nível do mar:** teclas 1 a 4 (0 / +0,5 / +1 / +2 m, os cenários científicos); `,` e `.` ajustam de forma contínua (cerca de 0,8 m/s); 5 a 7 são extremos de demonstração (+5, +10, +20 m).
- **Por que o tempo de render do quadro aparece no painel:** o FPS da tela fica travado pelo V-Sync (cerca de 60) e não mostra a diferença ao ligar ou desligar o LOD (`L`); o tempo de render, medido como no `bench.py`, mostra.

---

## 9. Benchmark: o que foi medido e como

Arquivo: `src/bench.py`.

**Pergunta.** O CDLOD compensa? A partir de que tamanho de malha?

**Método e o porquê:**
- **Sem janela** (contexto OpenGL headless): remove o V-Sync e o sistema de janelas das medições.
- **`ctx.finish()` a cada quadro:** a GPU é assíncrona; sem sincronizar, mediria só o tempo de enfileirar comandos.
- **30 quadros de aquecimento + 150 medidos:** o início tem custos de compilação e cache.
- **4 câmeras** (rasante, encosta, horizonte, aérea): o custo depende da vista.
- **5 resoluções** (256 a 2048): varia o tamanho da malha completa de 131.072 a 8.388.608 triângulos.
- **4 condições:** `sem_lod` (malha completa), `cdlod`, `cdlod_sem_morph`, `cdlod_frustum`.
- **3 execuções independentes**, com média e p95.
- **Memória medida por processo isolado:** cada modo roda em um processo novo, só com a malha que usa. Medir os modos na mesma cena (como na primeira versão) não separava a memória do LOD, porque as duas malhas ficavam residentes juntas.

**Resultados** (RTX 3060, série `bench/v3`):

| Medida | Resultado |
|---|---|
| Tempo do CDLOD | cerca de 1 ms, quase constante com a resolução |
| Tempo da malha completa | cresce com a resolução (0,18 ms em 256 → 2,09 ms em 2048, média) |
| **Ponto de virada** | cerca de 5 M triângulos (4,4 a 5,6 M conforme o critério e a execução) |
| Ponto de virada com culling | cerca de 3 M (2,0 a 3,5 M) |
| Custo do morphing | até 0,06 ms (dentro do ruído) |
| Culling | −22% no tempo de quadro |
| Memória de GPU a 2048² | 19 MB (CDLOD) × 153 MB (malha completa) |
| Pico de RAM a 2048² | 183 MB × 593 MB |

**Como ler o ponto de virada.** Abaixo dele, desenhar a malha completa é mais rápido (não há custo de percorrer a árvore e fazer várias draw calls). Acima, o CDLOD ganha. Nesta GPU a malha completa permaneceu interativa em todas as resoluções, então a hipótese do trabalho foi confirmada quanto à **eficiência** (tempo e memória), mas **não** quanto à perda de interatividade.

**Por que o CDLOD fica em cerca de 1 ms.** É overhead de CPU: percorrer a quadtree e emitir 50 a 200 draw calls em Python. Em C++ esse custo seria menor, e o ponto de virada seria diferente. É a explicação mais provável, mas não foi isolada por medição.

**O que a economia de memória é.** Vem só da malha (vértices e índices). A textura de altura (16,8 MB a 2048²) fica inteira na GPU em todos os modos.

---

## 10. Tabela de decisões

| Decisão | Por quê | Custo ou limite |
|---|---|---|
| Tiles terrarium da AWS | Sem chave de API; PNG simples; cobre terra e batimetria | Dados SRTM de cerca de 30 m; exatidão vertical não validada |
| Exagero vertical 6× | Sem ele a Serra do Mar vira uma lombada (razão 40:1) | Distorce a forma; declarado |
| Mediana 3×3 com limiar de 60 m | Remove spikes sem borrar o relevo real | Limiar escolhido empiricamente |
| Textura R32F + displacement | Uma só grade serve todos os blocos e níveis | Depende de leitura de textura no vertex shader |
| Quadtree de 5 níveis, grade 32×32 | Equilibra número de blocos e de draw calls | Não otimizado por busca de parâmetros |
| Alcance proporcional ao tamanho (×2,2) | Equivale a raios com duplicação, sem tabela | Fator adotado sem estudo de sensibilidade |
| Distância à borda do bloco | Evita não dividir blocos grandes próximos | Difere da distância ao vértice do morphing |
| Morphing com distância horizontal | Mesma métrica da seleção; evita morph total em vista aérea | Faixa simplificada, fenda residual |
| Frustum culling por AABB em NumPy | Imagem idêntica; 0,11 ms contra 7,7 ms em laço Python | Sem oclusão |
| Margem de 2 texels nas caixas | O filtro linear lê texels fora do bloco | Culling levemente menos agressivo |
| Gerstner com 6 ondas | Cristas realistas, direções variadas | Velocidades de fase manuais |
| Q normalizado por N | Garante `ΣQkA < 1` (0,45), sem laços | Cristas menos afiadas |
| Normal analítica na água | Exata e barata | Só vale para a soma de ondas |
| Alfa 0,80 na água | Mostra o terreno submerso | Transparência sem refração |
| Benchmark headless com `finish()` | Mede a GPU de verdade | Não mede V-Sync nem a janela |
| Memória por processo isolado | Separa o ganho do LOD | Mais lento de rodar |
| Projeção em um só lugar | Medição e uso real iguais | Nenhum |

---

## 11. Limitações e perguntas prováveis

### Limitações (todas declaradas no artigo)

1. Uma única GPU (RTX 3060 de computador de mesa); em outras o ponto de virada pode mudar.
2. Sem intervalos de confiança; o ponto de virada variou entre sessões (3,4 a 4,3 M numa série anterior, 4,4 a 5,6 M na atual).
3. Custo do CDLOD limitado por CPU (Python), provavelmente.
4. Exatidão vertical do DEM não validada; as áreas alagadas ilustram o método, não são previsão.
5. Caixa geográfica não quadrada mapeada em terreno quadrado, distorcendo a escala horizontal em cerca de 20%.
6. Verificação das fendas indireta (só fendas verticais, uma cena); popping não medido.
7. Água sem interação com o terreno, sem espuma nem arrebentação.

### Perguntas que podem aparecer

**Por que o CDLOD não ganhou sempre no tempo?** Porque tem custo fixo (percorrer a árvore, várias draw calls). Em malhas pequenas, uma única chamada com a malha completa é mais barata. O ganho aparece em malhas grandes e na memória.

**Por que CDLOD e não clipmaps?** O eixo cita clipmaps (Tanner et al.) como referência obrigatória, e o artigo os cita como base conceitual, mas o algoritmo implementado é o CDLOD (Strugar), que usa quadtree e displacement em textura. A escolha não foi comparada experimentalmente com clipmaps; isso não foi medido.

**O que é o ponto de virada e por que varia?** É o tamanho de malha em que as curvas de tempo se cruzam. Varia com a GPU, a sessão de medição e o critério (média ou p95). Por isso o artigo dá uma faixa.

**Por que o culling não muda a imagem?** Porque é conservador: só descarta blocos cuja caixa está inteira fora do campo de visão, e a caixa inclui margem.

**O que garante que o morphing funciona?** A medição de fendas finas (512 sem, 1 com) e o custo desprezível. Não garante ausência total de fendas nem de popping.

**Os valores de inundação são previsões?** Não. O DEM tem resolução horizontal de cerca de 30 m e exatidão vertical não validada, da ordem dos cenários simulados (+0,5 a +2 m). São demonstração do método.

**Por que 6× de exagero se isso distorce?** Para a Serra do Mar ser visível. O que importa para a inundação (altura do terreno contra altura da água) é multiplicado pelo mesmo fator, então a relação se mantém.

**As ondas são fisicamente corretas?** Não. Usam a forma de Gerstner, mas velocidades e amplitudes foram escolhidas visualmente. O objetivo é a aparência da água, não a simulação do oceano.

---

## Onde olhar no código

| Assunto | Arquivo |
|---|---|
| DEM, spikes, escala | `src/dem.py` |
| Grade unitária | `src/heightmap.py` |
| Quadtree, seleção, culling | `src/lod.py` |
| Morphing e altura | `src/shaders/terrain.vert` |
| Cor do terreno, faixa submersa | `src/shaders/terrain.frag` |
| Ondas de Gerstner | `src/shaders/water.vert`, `water.frag` |
| Montagem e desenho de um quadro | `src/scene.py` |
| Câmera e projeção | `src/camera.py` |
| Benchmark | `src/bench.py`, `src/resumo_bench.py` |
| Fendas | `src/verificar_fendas.py` |
| Área alagada | `src/area_alagada.py` |
| Testes | `tests/` |

Documentos complementares: [`docs/APRESENTACAO.md`](APRESENTACAO.md), [`docs/COMPLEMENTO_TECNICO.md`](COMPLEMENTO_TECNICO.md) (glossário e fórmulas), [`docs/DESENVOLVIMENTO.md`](DESENVOLVIMENTO.md) e [`docs/metodologia_atual.md`](metodologia_atual.md) (parâmetros exatos).
