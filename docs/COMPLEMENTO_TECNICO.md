# Complemento Técnico Detalhado — companheiro do artigo

Este documento **não substitui** o artigo (`docs/artigo_v2.pdf`); ele é um
**material de apoio**, mais longo e mais explicado, para quem vai
apresentar/defender o trabalho. A ideia: nenhum termo técnico usado no
artigo ou no código deve soar como "decoreba" — cada um está explicado
aqui com o **significado**, o **porquê** da escolha, e o **como** funciona
por dentro.

Estrutura: (1) o contexto e a ideia em uma frase; (2) glossário de todo
termo técnico usado, por tema; (3) cada biblioteca — por que ela e como
funciona; (4) como o sistema inteiro é montado e calculado, passo a passo,
com as fórmulas; (5) resultados obtidos até agora; (6) melhorias/trabalhos
futuros.

---

## 1. Contexto e ideia do projeto, em uma frase

**Erosão costeira** e **subida do nível do mar** são fenômenos ambientais
em que o oceano avança sobre a terra — por elevação do nível médio do mar
(derretimento de gelo + expansão térmica da água) e/ou perda de sedimento
da linha de costa. É difícil para uma pessoa leiga (ou um gestor público)
entender a *escala* desse risco só olhando números em metros num relatório.

**Visualização científica** é a área da computação que transforma dado
técnico (aqui, um mapa de altitude) numa imagem que uma pessoa consegue
interpretar rapidamente. A ideia central do projeto: pegar a **elevação
real** de uma costa (a Baixada Santista) e permitir que qualquer pessoa
**veja, em 3D e em tempo real, a água subindo** sobre o relevo verdadeiro
daquele lugar — em vez de olhar uma tabela ou um mapa 2D estático.

O obstáculo técnico que isso escondeu: um mapa de elevação real, bom o
bastante pra parecer "de verdade", tem milhões de pontos. Desenhar tudo
isso, 60 vezes por segundo, é caro demais. A **aplicação** entregue resolve
os dois problemas ao mesmo tempo: ela é a ferramenta de visualização **e**
o experimento que mede quando a simplificação (LOD) deixa de ser opcional.

---

## 2. Glossário — todo termo técnico específico, explicado

### 2.1 Computação gráfica em geral

| Termo | Significado |
|---|---|
| **Heightmap** (mapa de altura) | Uma grade 2D de números: `altura[linha][coluna]`. É a "receita" do relevo — cada célula diz o quanto o terreno sobe naquele ponto. |
| **Displacement mapping** (deslocamento por mapa) | Técnica de pegar uma malha **plana** e empurrar cada vértice para cima, na altura lida de uma textura/heightmap. É como a grade plana "vira" montanha. |
| **Textura** | Uma imagem guardada na memória da GPU, endereçável por coordenadas `uv ∈ [0,1]`. Usamos uma textura de **1 canal, ponto flutuante (R32F)** — cada texel guarda 1 número (a altura), não uma cor RGB. |
| **VBO** (*Vertex Buffer Object*) | Bloco de memória na GPU com os vértices (posições, normais etc.) de uma malha. |
| **VAO** (*Vertex Array Object*) | A "planta baixa" que diz à GPU como ler o VBO — quantos números por vértice, em que ordem, pra qual variável do shader. |
| **EBO / Index buffer** | Lista de índices que agrupam vértices em triângulos, evitando repetir vértice compartilhado entre triângulos vizinhos. |
| **Shader** | Um programinha que roda **na GPU**, em paralelo, para cada vértice (*vertex shader*) ou cada pixel (*fragment shader*). Escrito em **GLSL** (a linguagem de shader do OpenGL). |
| **OpenGL core profile 3.3 / GLSL 330** | A "versão" da API gráfica usada — moderna (sem funções obsoletas), suficiente para tudo que o projeto precisa. |
| **Rasterização** | Etapa **automática** da GPU que transforma um triângulo (3 pontos na tela) nos pixels que ele cobre, interpolando os valores dos 3 vértices ao longo do caminho. |
| **Framebuffer / FBO** | O "quadro" onde a GPU desenha. Pode ser a tela (janela) ou um alvo **fora da tela** (usado no benchmark e para gerar o minimapa). |
| **Draw call** | Um comando "desenhe esta malha agora". Cada um tem um custo fixo de organização no lado da CPU — é por isso que o CDLOD, com ~100 a 184 *draw calls* por quadro, tem um piso de custo que a malha única (1 *draw call*) não tem. |
| **V-Sync** | Trava a troca de quadros no ritmo do monitor (~60 Hz), evitando *tearing* (corte visual). Também **esconde** ganhos de desempenho menores que 1/60 s — por isso medimos o tempo de render manualmente, em vez de confiar só no FPS da tela. |
| **FOV / near / far** | Campo de visão vertical (graus) e os planos de recorte próximo/distante da câmera — juntos definem o **frustum** (o "cone" de visão que vira imagem). |
| ***Bounding box*** | O menor retângulo/caixa que contém uma forma — usada tanto para o recorte geográfico (latitude/longitude) quanto para cada bloco do quadtree. |

### 2.2 LOD e CDLOD

| Termo | Significado |
|---|---|
| **LOD** (*Level of Detail*, nível de detalhe) | Estratégia geral de desenhar com **menos geometria** o que está longe da câmera (imperceptível) e mais perto do observador. |
| **CDLOD** (*Continuous Distance-Dependent LOD*) | O algoritmo específico de Strugar (2009): organiza o terreno numa **quadtree** e escolhe o nível de detalhe de cada bloco por uma função contínua da distância. |
| **Quadtree** | Estrutura em árvore em que cada nó representa um quadrado, e se subdivide em **4 filhos** (quadrantes) até uma profundidade máxima. Aqui: profundidade `L = 5`. |
| **Nó raiz / nó folha** | O nó raiz é o quadrado que cobre o terreno inteiro; um nó folha é o último nível (o mais subdividido, sem filhos). |
| **Geomorphing (morphing)** | Técnica de deslizar suavemente os vértices "ímpares" de uma grade até a posição dos "pares" conforme a distância cresce — faz a borda de um bloco detalhado **coincidir** com a de um bloco grosseiro vizinho. |
| ***Crack*** (fresta) | Buraco visual que aparece quando dois blocos vizinhos, com resolução de vértice diferente, não se encaixam perfeitamente na borda comum. |
| ***Popping*** (salto) | Mudança abrupta e visível na geometria quando um bloco troca de nível de detalhe de um quadro pro outro — o morphing suaviza essa transição. |
| ***Tipping point*** (ponto de virada) | O valor de carga geométrica (aqui, ~5 milhões de triângulos) a partir do qual a técnica com *overhead* fixo (CDLOD) passa a compensar frente à alternativa simples (malha única). |

### 2.3 Água / ondas de Gerstner

| Termo | Significado |
|---|---|
| **Onda trocoidal / onda de Gerstner** | Modelo de onda em que cada partícula da superfície descreve uma **trajetória circular/elíptica** (desloca-se na horizontal *e* na vertical), e não só sobe e desce como um seno simples. Produz cristas afiadas e vales largos, como o mar de verdade. |
| **Amplitude (A)** | Altura da onda (do meio ao topo). |
| **Comprimento de onda (λ)** | Distância entre duas cristas seguidas. |
| **Vetor de onda (k⃗)** | Aponta na direção de propagação da onda; seu tamanho é `2π/λ`. |
| **Frequência angular (ω)** | Velocidade com que a fase da onda muda no tempo — controla a velocidade de propagação visual. |
| ***Steepness* (Q)** | Controla o quão "pontiaguda" fica a crista (0 = seno arredondado; perto de 1 = quase se autointersectando). No projeto, `Q` **decresce** para as ondas de maior frequência, evitando que elas formem laços. |
| **Normal analítica** | A normal da superfície da água é calculada por uma **fórmula fechada** (derivada das equações de onda), em vez de amostrar pontos vizinhos — mais barato e mais preciso. |
| **Blinn-Phong** | Modelo clássico de iluminação: soma um termo **difuso** (Lambert: quanto a superfície encara a luz) com um termo **especular** (o brilho pontual do sol refletido). |
| **Fresnel (aprox. de Schlick)** | Fenômeno físico: qualquer superfície reflete mais luz quando vista de **raspão** (ângulo rasante) do que de frente — é por isso que o mar no horizonte parece um espelho, mas debaixo dos seus pés dá pra ver o fundo. |
| ***Alpha* / transparência** | Um 4º canal de cor (além de R, G, B) que controla o quanto a cor "de trás" aparece através da superfície — aqui, `α = 0,80` para a água. |

### 2.4 Dados geoespaciais

| Termo | Significado |
|---|---|
| **DEM** (*Digital Elevation Model*) | Um mapa de elevação **real**, medido — não inventado. |
| **SRTM** (*Shuttle Radar Topography Mission*) | Missão da NASA (ônibus espacial, 2000) que mediu a altitude de quase toda a superfície terrestre por radar. |
| **Batimetria / GEBCO** | "Batimetria" = a topografia do **fundo do oceano**. GEBCO é o conjunto de dados batimétricos global usado aqui, medido por sonar. |
| **Formato *terrarium*** | Convenção de codificar altura (em metros) diretamente nos 3 canais de cor (R, G, B) de um PNG comum, via `altura = R·256 + G + B/256 − 32768`. Permite guardar elevação numa imagem "normal", sem formato geoespacial especializado. |
| **Tile** | Um "ladrilho" de mapa — o mundo é dividido em imagens pequenas e indexadas por zoom/x/y (o mesmo esquema do Google Maps), pra não precisar baixar o planeta inteiro de uma vez. |
| ***Despiking*** (remoção de picos) | Limpeza de dado de sensoriamento remoto: troca um pixel isoladamente absurdo (um "espinho" de ruído do radar) pela mediana dos vizinhos, sem borrar o relevo real. |
| **Reamostragem bilinear** | Método de encolher/esticar uma grade de números interpolando linearmente entre os 4 vizinhos mais próximos — usado para levar o mosaico de tiles à resolução final (1024×1024). |
| **Exagero vertical** | Multiplicar a altura por um fator (aqui, 6×) para que um relevo real, que é uma fração minúscula da extensão horizontal, fique **visualmente perceptível**. Prática padrão em geovisualização, desde que declarada. |

### 2.5 Avaliação experimental

| Termo | Significado |
|---|---|
| ***Benchmark* headless** | Medição de desempenho **sem abrir janela** — desenha em um framebuffer "invisível", isolando o custo de renderização de qualquer custo de exibição na tela. |
| **Sincronizar a GPU (`ctx.finish()`)** | Forçar o programa a **esperar** a GPU terminar de verdade antes de marcar o tempo — sem isso, a CPU "acha" que terminou antes da hora (a GPU processa em paralelo/atrasado). |
| ***Warm-up* (aquecimento)** | Rodar alguns quadros **antes** de medir, pra deixar caches e *drivers* em regime estável — evita que o primeiro quadro (mais lento por natureza) distorça a média. |
| **Percentil (p50, p95)** | p50 = a mediana (metade dos quadros foi mais rápida que isso); p95 = 95% dos quadros foram mais rápidos que isso — ajuda a enxergar os "piores casos", não só a média. |
| **RAM / VRAM** | RAM = memória principal do computador (usada pelo processo Python); VRAM = memória **da própria placa de vídeo** (onde ficam texturas e buffers). |

---

## 3. Por que cada biblioteca — e como ela funciona por dentro

| Biblioteca | Por que essa e não outra | Como funciona |
|---|---|---|
| **Python 3.11** | Linguagem que o grupo já conhecia; produtividade alta para prototipar. O código "pesado" (por vértice/pixel) não roda em Python — roda nos shaders, na GPU — então a lentidão do Python não é o gargalo. | Interpretada; aqui usada só para "orquestrar": ler arquivos, montar arrays, mandar comandos pra GPU. |
| **ModernGL** | Dá acesso ao OpenGL moderno (*core profile*) com uma API Python de objetos (`Context`, `Buffer`, `Program`, `Texture`), sem o *boilerplate* de C (ponteiros, `glGen*`/`glBind*` manuais). Comparado a `PyOpenGL` (o wrapper "cru"), é muito mais direto de usar. | Por baixo, cada método (`ctx.buffer()`, `ctx.program()`...) chama as funções C do driver da placa de vídeo; o ModernGL só embrulha isso numa interface Pythônica. |
| **GLFW** | Biblioteca padrão da indústria para abrir janela + capturar teclado/mouse "crus", sem depender de um *framework* de jogo inteiro. | Fala diretamente com o sistema operacional (Windows, no nosso caso) para criar a janela e o contexto OpenGL associado a ela, e repassa eventos de input a cada `glfw.poll_events()`. |
| **PyGLM** | Precisamos de vetores (`vec3`) e matrizes (`mat4`) para posição, câmera e projeção — junto com funções prontas (`lookAt`, `perspective`) que já implementam a matemática certa. PyGLM é a portabilidade Python da biblioteca **GLM** (C++), usada em praticamente todo tutorial/motor gráfico em OpenGL — evita reescrever (e errar) essa álgebra na mão. | Cada operação (produto vetorial, normalização, `lookAt`) é implementada em C++ por trás e exposta como objetos Python — rápida e numericamente correta. |
| **NumPy** | Toda a geometria (grades de vértices, índices de triângulo, o próprio heightmap) é construída como **array vetorizado** — uma grade de 1024×1024 processada de uma vez, em vez de 1 milhão de iterações em Python puro (que seria ordens de magnitude mais lento). | Os arrays do NumPy são blocos de memória contígua, no mesmo formato binário que a GPU espera — dá pra mandar `array.tobytes()` direto pra um buffer da GPU. |
| **Pillow (PIL)** | Duas funções bem diferentes: (1) decodificar os tiles PNG do DEM (ler os canais R/G/B — Equação da Seção 4.1); (2) desenhar texto/imagens da interface (HUD), já que o **OpenGL não tem texto nativo**. | Para o DEM: abre o PNG e expõe os pixels como array. Para a HUD: desenha texto/formas numa "tela" (`Image`), que depois sobe pra GPU como textura comum. |
| **opensimplex** | Gera o terreno **procedural** (modo alternativo ao DEM real) com ruído coerente (variação suave, sem serrilhado) — mais moderno e com menos artefatos direcionais que o Perlin noise clássico. | Implementa o algoritmo *OpenSimplex*: para cada ponto `(x, z)`, calcula um valor suave em `[-1, 1]` a partir de uma grade simplicial (triangular) de gradientes pseudo-aleatórios. |
| **matplotlib** | Só usada pelo `bench.py`, pra gerar os gráficos de desempenho (padrão de fato para gráficos científicos em Python). | Recebe os dados já processados (listas de resolução × tempo) e desenha os eixos/curvas/legendas. |
| **psutil** | Lê o consumo de **RAM** do próprio processo Python de forma multiplataforma, sem código específico de sistema operacional. | Consulta o sistema operacional (via chamadas nativas do SO) pelas estatísticas de memória do processo (`memory_info().rss`). |
| **nvidia-smi** | Não é uma biblioteca Python — é um **utilitário de linha de comando** que vem com o driver NVIDIA. Usado (via `subprocess`) pra ler VRAM usada e % de uso da GPU, dado que não existe uma forma portátil/simples de fazer isso de dentro do OpenGL. | Consulta o driver da placa de vídeo diretamente; devolve texto (CSV) que o `bench.py` interpreta. |

---

## 4. Como tudo é montado e calculado — o pipeline completo

### 4.1 Do dado bruto ao heightmap

1. **Escolha da área**: uma *bounding box* de latitude `[-23,70, -24,10]` e
   longitude `[-46,60, -46,05]` — cobre a Serra do Mar, o sistema estuarino
   de Santos/São Vicente e o oceano aberto ao sul.
2. **Download dos tiles**: a *bounding box* é convertida em coordenadas de
   tile (zoom 11, esquema *slippy map* — o mesmo do Google Maps), e cada
   tile é baixado como PNG da AWS (`elevation-tiles-prod`), com cache local.
3. **Decodificação** (formato *terrarium*):
   ```
   altura_metros = R × 256 + G + B / 256 − 32768
   ```
   R, G, B são os valores (0–255) do pixel; o resultado é a elevação real,
   em metros, naquele ponto — positiva em terra, negativa no mar.
4. **Limpeza (*despiking*)**: para cada pixel, calcula-se a **mediana** dos
   8 vizinhos + ele mesmo (janela 3×3); se o valor do pixel se afasta demais
   dessa mediana (mais que um limiar em metros), ele é **substituído** pela
   mediana — isso elimina "espinhos" isolados de ruído do radar, sem
   suavizar as formas reais do relevo. Feito em 2 passadas.
5. **Reamostragem**: o mosaico (tamanho variável, conforme os tiles) é
   redimensionado para exatamente **1024×1024** por interpolação bilinear.
6. **Conversão para unidades de mundo**:
   ```
   y_mundo = (altura_metros / σ) × E
   ```
   onde `σ ≈ 167 m/u.m.` (a escala: um mundo de 300 u.m. de lado cobre
   ~50 km reais) e `E = 6` é o exagero vertical. Sem o `E`, a Serra do Mar
   (~1,2 km de amplitude real) ficaria com menos de 1/40 da largura do
   mundo — visualmente quase plana.

*(Código: `src/dem.py`, função `carregar_heightmap`.)*

### 4.2 Do heightmap à malha na GPU

A matriz de alturas (1024×1024, `float32`) sobe para a GPU como uma
**textura de 1 canal (R32F)** — não vira uma malha de vértices fixa.

Existe, à parte, uma **grade unitária** reusável: `N × N` pontos em
`[0,1]²` (aqui, `N = 33`, ou seja, 32×32 subdivisões = 2048 triângulos). O
vertex shader recebe, por bloco, um **canto** (`u_node_offset`) e um
**tamanho** (`u_node_scale`), e faz:

```
mundo_xz = canto + grade_unitaria_xz × tamanho
altura   = textura(u_heightmap, mundo_xz / tamanho_do_mundo + 0.5)
```

Ou seja: a mesma gradezinha é "esticada e realocada" para cada bloco do
quadtree, amostrando a textura de altura no lugar certo — é o
**displacement mapping** da Seção 2.1.

### 4.3 O quadtree e a seleção de blocos (CDLOD)

1. **Construção** (1 vez, no início): a partir de um nó raiz que cobre o
   mundo inteiro, subdivide-se recursivamente em 4 filhos até profundidade
   `L = 5`. Cada nó guarda seu centro `(cx, cz)` e seu tamanho `τ`.
2. **Seleção** (a cada quadro, em Python, usando a posição atual da câmera):
   percorre a árvore de cima para baixo; para cada nó, calcula a distância
   euclidiana `d` da câmera até a **borda** da caixa do nó (não o centro —
   isso evita que um nó grande e próximo deixe de se subdividir só porque
   o centro dele está longe). Critério:
   ```
   se d < τ × 2,2 :  desce para os 4 filhos (mais detalhe)
   senão          :  desenha este nó (não desce mais)
   ```
   O resultado típico: ~100–184 blocos ativos (52–73 com o frustum culling), contra os 1024 blocos-folha
   que existiriam se a árvore inteira fosse forçada à profundidade máxima.
3. **Morphing**: para cada bloco desenhado, calcula-se uma **faixa de
   transição** (`u_morph_start` a `u_morph_end`), baseada no próprio `τ` do
   bloco. Dentro dela, os vértices de índice ímpar da grade deslizam
   progressivamente para a posição dos pares — eliminando a fresta com o
   bloco vizinho de menor detalhe.

*(Código: `src/lod.py` — construção e seleção; `src/shaders/terrain.vert`
— o *displacement* e o morphing.)*

### 4.4 Cor e iluminação do terreno

No fragment shader, para cada pixel:

1. **Cor base por altitude**: interpola entre 3 cores (restinga → Mata
   Atlântica → rocha) conforme a altura normalizada `t = altura / altura_máx`.
2. **Cor por inclinação**: paredões íngremes (normal quase horizontal)
   recebem mais peso de "rocha exposta", independente da altitude.
3. **Iluminação difusa (Lambert)**: `brilho = max(0, normal · direção_da_luz)`.
4. **Faixa submersa**: se `altura_do_ponto < nível_do_mar`, mistura a cor
   com um tom verde-escuro (mais forte quanto mais fundo) — é o realce que
   mostra a inundação.
5. **Névoa de distância**: mistura com a cor do céu conforme a distância à
   câmera cresce, dando sensação de escala/profundidade.

### 4.5 A água (ondas de Gerstner)

Para cada uma das `m = 6` componentes de onda (índice `i`), com ponto de
referência `(x₀, z₀)` no plano de repouso:

```
x = x₀ + Qᵢ·Aᵢ·D̂ᵢₓ·cos(k⃗ᵢ·(x₀,z₀) − ωᵢt)
z = z₀ + Qᵢ·Aᵢ·D̂ᵢᵤ·cos(k⃗ᵢ·(x₀,z₀) − ωᵢt)
y = Aᵢ·sin(k⃗ᵢ·(x₀,z₀) − ωᵢt)
```

Somando as 6 componentes (amplitudes de 1,10 a 0,07, comprimentos de onda
de 70 a 4 u.m., `Qᵢ` decrescente de 0,60 a 0,28), o resultado tem o aspecto
irregular de um mar de verdade, em vez do padrão repetitivo de uma única
onda. A **normal** é obtida derivando essa mesma soma analiticamente (sem
amostrar vizinhos). A altura de repouso `y₀` (em torno da qual as ondas
oscilam) **é** o nível do mar ajustável.

*(Código: `src/shaders/water.vert`/`.frag`.)*

### 4.6 A câmera

Orientação por dois ângulos de Euler — **yaw** (`ψ`, giro horizontal) e
**pitch** (`θ`, giro vertical, travado em `[-89°, 89°]`):

```
front = (cos ψ · cos θ,  sin θ,  sin ψ · cos θ)
right = normalizar(front × mundo_up)
up    = normalizar(right × front)
```

`front`, `right`, `up` e a posição formam a matriz *view* (`glm.lookAt`). A
**direção de bússola** é obtida do mesmo `front`, projetado no plano
horizontal:

```
rumo_graus = atan2(front.x, −front.z)   (mod 360; 0° = Norte, 90° = Leste)
```

*(Código: `src/camera.py`.)*

### 4.7 O minimapa

Gerado **1 vez**, antes do laço principal: a própria `Cena` é desenhada
de cima (câmera olhando reto para baixo, "para cima" apontando para o Norte
do mundo), o resultado é lido do framebuffer e vira uma imagem estática.
A cada quadro, essa imagem é copiada e um marcador (posição XZ da câmera +
seta na direção do `rumo_graus`) é desenhado por cima, sem recalcular o
mapa inteiro.

### 4.8 A avaliação experimental

`src/bench.py` reconstrói a mesma `Cena` usada pela aplicação interativa
(sem duplicar lógica), variando: resolução do heightmap (256 a 2048),
condição (sem LOD / CDLOD / CDLOD sem morphing) e posição da câmera (4
configurações). Para cada combinação: 30 quadros de aquecimento, 150
quadros medidos com `ctx.finish()` a cada um (tempo real de GPU, não
estimativa), e uma amostra de RAM/VRAM/uso de GPU.

---

## 5. Resultados até o momento

- **Desempenho**: com CDLOD, o tempo de quadro fica **quase constante**
  (~1 ms) em qualquer resolução testada, porque o número de triângulos
  desenhados não passa de ~0,5 milhão. Sem LOD, o tempo cresce
  **linearmente** com a resolução, chegando a ~8,4 milhões de triângulos e
  ~2,4 ms na resolução máxima (2048). As curvas se cruzam por volta de
  **5 milhões de triângulos** — o ponto de virada.
- **Custo do morphing**: dentro do ruído de medição — praticamente grátis.
- **Recursos**: RAM (~110→255 MB) e VRAM (~620→805 MB) crescem com a
  **resolução do dado**, não com o modo de LOD (nesta bateria de testes as
  três condições compartilham a mesma cena — ver `docs/metodologia_atual.md`
  para a ressalva completa).
- **Verificação visual**: o formato do terreno gerado (canais do estuário,
  ilhas, diagonal da Serra do Mar) foi comparado com um mapa real da região
  e confere.
- **Aplicação em si**: interativa e funcional — navegação livre, 4 + 3
  cenários de nível do mar, alternância de LOD/morphing ao vivo.

---

## 6. Melhorias (trabalhos futuros)

**Já identificadas no artigo, ainda pendentes:**

1. ✅ *Frustum culling* — **feito** (tecla `C`; AABB por nó + 6 planos, em NumPy). Falta oclusão (blocos escondidos atrás de montanhas).
2. Rodar o mesmo *benchmark* em outras GPUs (inclusive integradas), para
   verificar como o ponto de virada muda com o hardware.
3. Água interagindo fisicamente com o terreno — espuma e arrebentação
   perto da costa; hoje a água é uma superfície independente.
4. Validação da ferramenta com especialistas em gestão ambiental costeira.

**Feitas depois da última revisão do artigo (ainda não descritas nele):**

5. Interface para leigos: tela de boas-vindas, legenda em 2 níveis, painel
   de status (nível do mar + modo de LOD/morphing + tempo de render real,
   já que o FPS da tela fica mascarado pelo V-Sync), bússola, minimapa e
   tecla de resgate (`R`) para quem se perde navegando.

**Pendências que não são de código:**

6. Relatório da Etapa 1 (revisão bibliográfica).
7. Confirmar com o professor as referências complementares.
8. ✅ Correções do artigo (triângulos a 2048 e título da referência de Welch) — **feitas** na v4.
