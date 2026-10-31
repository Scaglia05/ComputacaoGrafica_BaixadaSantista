# Visualização de Elevação Costeira — Computação Gráfica

[![Abrir o artigo (PDF)](https://img.shields.io/badge/%F0%9F%93%84%20Abrir%20o%20artigo-PDF-b31b1b?style=for-the-badge)](docs/artigo_final/artigo_final_v3_previa.pdf)

> 📄 Se o botão acima não aparecer, [clique aqui para abrir o artigo (PDF)](docs/artigo_final/artigo_final_v3_previa.pdf).

Visualizador 3D interativo do relevo real da **Baixada Santista (Santos/SP)**
com uma superfície de água animada cuja altura o usuário ajusta em tempo real
(0, +0,5, +1 e +2 m, além de cenários extremos de demonstração), para ver quais
áreas ficariam submersas a cada cenário de subida do nível do mar.

O projeto também responde a uma pergunta de desempenho: **a partir de quantos
triângulos o LOD adaptativo (CDLOD) deixa de ser um refinamento e passa a ser
necessário?** A resposta medida está no artigo: cerca de 4 milhões de triângulos
numa RTX 3060, ou cerca de 2,3 milhões com *frustum culling*.

- **Disciplina:** Computação Gráfica (FHO/Uniararas) — **Eixo 6**, Topografia e Sistemas Mobile
- **Stack:** Python 3.11 · ModernGL · GLFW · PyGLM · NumPy · Pillow · opensimplex · matplotlib · psutil
- **Terreno:** DEM real da Baixada Santista (AWS Terrain Tiles) ou ruído procedural
- **LOD:** CDLOD (quadtree + seleção por distância + *morphing* de vértices) e *frustum culling*
- **Água:** ondas de Gerstner no *vertex shader*
- **Para começar:** veja [Instalação](#instalação) e [Como rodar](#como-rodar) (`python src/main.py`)

## Instalação

O projeto usa o ambiente virtual `.venv` (**Python 3.11.9**), que já vem com
tudo instalado. No VS Code, selecione esse interpretador:
`Ctrl+Shift+P` → **Python: Select Interpreter** → `.venv (Python 3.11.9)`.

Para recriar do zero (use Python 3.11 ou 3.12 — em 3.13 algumas libs tentam
compilar do fonte e falham sem o Visual C++ Build Tools):

```bash
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Estrutura

```
ComputacaoGrafica/
├── requirements.txt
├── README.md
├── CLAUDE.md                 # contexto do projeto p/ sessões de IA (estado, parâmetros, pendências)
├── docs/
│   ├── especificacao_eixo6.pdf # especificação oficial do professor (Eixo 6, etapas, referências obrigatórias)
│   ├── APRESENTACAO.md       # guia de ponta a ponta (tema, libs, código, o que é novo)
│   ├── DESENVOLVIMENTO.md    # relato de como o projeto foi construído, fase a fase
│   ├── metodologia_atual.md/.pdf  # valores exatos de cada parâmetro (fonte da verdade)
│   ├── COMPLEMENTO_TECNICO.md # companheiro do artigo: glossário + fórmulas + por que cada lib
│   ├── resumo_projeto.pdf    # resumo de 3 páginas
│   ├── artigo_final/         # ARTIGO FINAL (ABNT em duas colunas, template IEEE do Overleaf, até 8 páginas)
│   │   ├── artigo_final_v3_abnt.tex       # fonte LaTeX (versão atual)
│   │   ├── artigo_final_v3_overleaf.zip   # pacote pronto para subir no Overleaf (.tex + figuras)
│   │   └── artigo_final_v3_previa.pdf     # prévia em PDF (botão no topo deste README)
│   ├── ArtigoCompGrafica_ElevacaoCosteira.pdf  # versão anterior do artigo (IEEE) — histórico
│   ├── artigo_v4.tex         # fonte LaTeX da versão anterior — histórico
│   └── figuras/              # capturas do sistema e gráfico de custo × carga usados no artigo
├── exemplos/                 # estudos isolados (fundamentos do pipeline)
│   ├── janela.py             # janela + contexto OpenGL + render loop
│   └── triangulo.py          # VBO, shaders, VAO, rasterização/interpolação
├── bench/                   # saídas do benchmark (CSV + gráficos); bench/v2/ = medições novas
├── tests/                   # testes automatizados (unittest): culling, memória isolada, benchmark
└── src/                      # a engine
    ├── dem.py                # baixa o DEM real da Baixada Santista (tiles AWS terrarium)
    ├── heightmap.py          # ruído procedural -> textura de altura + grade unitária reusável
    ├── lod.py                # quadtree do terreno + seleção de blocos por distância (CDLOD)
    ├── water.py              # plano de água (grade plana; ondas ficam no shader)
    ├── camera.py             # câmera livre (yaw/pitch, matrizes view/projection)
    ├── scene.py              # classe Cena: todo o setup de GPU + desenhar() (usada por main e bench)
    ├── hud.py                # sobreposições 2D: legenda de comandos + foto de referência
    ├── area_alagada.py       # área emersa alagada em cada cenário de nível do mar (tabela do artigo)
    ├── main.py               # janela + input + laço
    ├── bench.py              # mede tempo de frame com/sem LOD -> bench/*.csv e *.png
    ├── data/referencia_santos.jpg      # foto da Baía de Santos (CC BY 2.0 — ver _CREDITO.txt)
    ├── data/tiles/           # cache dos tiles de DEM (gerado, fora do git)
    └── shaders/
        ├── terrain.vert/.frag  # heightmap por bloco + morphing; cor por altitude, faixa submersa
        └── water.vert/.frag    # ondas de Gerstner; Blinn-Phong + Fresnel + transparência
```

### Fonte do terreno

Em `src/main.py`, `FONTE_TERRENO = "dem"` usa o DEM real; `"procedural"` usa ruído.

O DEM vem dos **AWS Terrain Tiles** (formato *terrarium*, sem chave de API),
derivados de SRTM + batimetria GEBCO. `src/dem.py` baixa e faz cache dos tiles
na 1ª execução (~1 MB), remove *spikes*, reamostra para 1024² e aplica
**exagero vertical de 6×** — a Baixada Santista tem ~50 km de largura para
~1,2 km de relevo (≈40:1), então sem exagero a Serra do Mar some. 6× é o
suficiente para a escarpa aparecer como uma parede de montanhas; é prática
padrão em geovisualização e **deve ser declarado no artigo** (ajustável em
`carregar_heightmap(exagero_vertical=...)`).
Com o DEM, os cenários de nível do mar (`1`–`4`) são metros reais.

## Como rodar

```bash
python exemplos/janela.py       # janela vazia (ESC fecha)
python exemplos/triangulo.py    # triângulo colorido
python src/heightmap.py         # testa geração da malha sem abrir janela
python src/dem.py               # baixa/prepara o DEM da Baixada Santista
python src/lod.py               # testa a seleção de blocos do quadtree
python src/main.py              # cena completa: terreno + LOD + água
python src/bench.py             # benchmark (--rapido para subconjunto)
python src/bench.py --saida bench/v2             # idem, em outra pasta (sem sobrescrever os dados do artigo)
python src/bench.py --memoria --saida bench/v2   # RAM/VRAM de cada modo, cada um em processo separado
python -m unittest discover -s tests -v          # testes automatizados (parte deles precisa de GPU)
python src/area_alagada.py      # área emersa alagada em cada cenário de nível do mar
```

### Benchmark (Etapa 4)

`python src/bench.py` roda sem janela e varre `{sem LOD, CDLOD, CDLOD sem morph}
× {256..2048} × {4 câmeras}`, sincronizando a GPU a cada frame. Também tira uma
amostra de **RAM (processo, via `psutil`) e VRAM/uso de GPU (via `nvidia-smi`,
quando disponível)** por combinação. Gera `bench/resultados.csv` e 5 gráficos.
Resultado numa RTX 3060:

- o CDLOD segura o tempo de frame ~constante (~1 ms) em qualquer resolução,
  porque desenha sempre ~0,4 M triângulos;
- a malha ingênua cresce linear com a resolução e **ultrapassa o CDLOD em cerca
  de 4 M de triângulos (2,7 a 4,3 M, conforme o critério — média ou p95 — e a
  execução)** — esse é o "ponto de virada";
- o custo do *morphing* é desprezível (dentro do ruído de medição);
- o ~1 ms fixo do CDLOD é overhead de CPU (percorrer o quadtree + 100–184
  *draw calls* em Python) — a hipótese é que numa GPU fraca / mobile o ponto de
  virada chegue antes, mas isso **não foi medido** (falta hardware);
- nesta varredura a RAM e a VRAM medidas (com as 3 condições na mesma cena de
  teste) refletem a **resolução do DEM**, não o modo de LOD; a diferença entre
  os modos aparece na medição isolada abaixo.

#### Extensões: frustum culling e memória isolada por modo

Medidas novas, gravadas em `bench/v2/` (os dados do artigo em `bench/` não foram
alterados). RTX 3060, 3 execuções independentes.

- **Frustum culling** (`C` no app; condição `cdlod_frustum` no benchmark): poda os
  blocos da quadtree fora do campo de visão. A imagem é **idêntica pixel a pixel**
  (testada em 4 + 40 câmeras). O ganho depende de para onde a câmera olha:

  | Câmera | Blocos | Tempo de quadro |
  |---|---|---|
  | rasante | 178 → 57 | −33% |
  | encosta | 184 → 52 | −38% |
  | horizonte | 124 → 73 | −7% |
  | aérea | 100 → 67 | ≈ 0% (dentro do ruído) |

  Média geral: 1,04 → 0,81 ms (−22%). **O ponto de virada, ao se comparar com a
  malha sem LOD, cai de ~4,0 M para ~2,3 M de triângulos.** O culling é medido
  como condição *a mais*; a malha sem LOD não tem culling.
- **Memória isolada** (`--memoria`): cada modo em um processo novo, só com a malha
  que usa. A 2048², o CDLOD aloca **19 MB** na GPU contra **153 MB** da malha
  completa (−88%), e o pico de RAM é 191 MB contra 595 MB. Morphing e culling não
  mudam a memória. A economia vem só da malha (vértices + índices): a textura de
  altura (16,8 MB a 2048²) fica inteira na GPU em todos os modos.

### Controles (`src/main.py`)

| Tecla            | Ação                                         |
|------------------|----------------------------------------------|
| `W` `A` `S` `D`  | mover na horizontal                          |
| `Espaço` / `Ctrl`| subir / descer                               |
| `Shift`          | mover mais rápido                            |
| Mouse            | olhar ao redor                               |
| `R`              | volta pro ponto de partida (se você se perder) |
| `Tab`            | solta / prende o mouse (solto: dá para usar o outro monitor) |
| `F11`            | tela cheia ↔ janela (no monitor onde a janela está) |
| `,` / `.`        | baixar / subir o nível do mar (contínuo)     |
| `1` `2` `3` `4`  | cenários de nível do mar (0 / +0,5 / +1 / +2 m) — os científicos |
| `5` `6` `7`      | cenários extremos p/ demonstração (+5 / +10 / +20 m) |
| `L`              | liga/desliga o LOD (CDLOD × malha ingênua)   |
| `M`              | liga/desliga o morphing (OFF → cracks)       |
| `C`              | liga/desliga o frustum culling (não desenha o que está fora da tela) |
| `K`              | debug: cor por profundidade de bloco         |
| `Z`              | alterna wireframe (ver malha)                |
| `H`              | legenda: nenhuma → básica → completa → nenhuma |
| `P`              | alterna o canto inferior-direito: minimapa ↔ foto real |
| `I`              | mostra de novo a tela de boas-vindas          |
| `ESC`            | sair                                         |

Ao abrir, uma **tela de boas-vindas** explica o objetivo em linguagem
simples (some ao começar a andar; `I` traz de volta). A legenda (`H`) tem
2 níveis — a básica só com o essencial pra explorar a inundação, a completa
acrescenta LOD/morphing explicados em 1 linha cada.

O **nível do mar, o modo atual (LOD/morphing) e o tempo de render do
quadro** ficam sempre visíveis (canto superior-direito) — o nível tem um
selo colorido (azul = nível atual, amarelo = risco de alagamento, vermelho
= alagamento); o tempo de render é medido do mesmo jeito que o `bench.py`
e é o número que **muda de verdade** ao apertar `L` (o FPS da tela, com
V-Sync, fica travado em ~60 e não mostra a diferença). Uma **bússola**
(canto inferior-esquerdo) mostra pra onde você está olhando, e um
**minimapa** com a posição da câmera (canto inferior-direito, alterna com
a foto real via `P`) ajuda a não se perder no terreno.

## Versões do código

| Onde | Conteúdo |
|---|---|
| branch `main` | código **simplificado para leitura**, com frustum culling, memória isolada, testes e as teclas `Tab` e `F11` |
| commit `3f30ace` (branch `feat/frustum-culling-memoria-isolada`, antes da simplificação) | código **original**, mesma funcionalidade, sem `Tab`/`F11` — gerou os números do artigo |

A simplificação não muda a funcionalidade. Para ver a versão original:
`git switch --detach 3f30ace`. Os 38 testes passam na versão original; rode
`python -m unittest discover -s tests -v` também na `main` antes de usá-la.

## Artigo

O artigo final fica em `docs/artigo_final/` (ABNT, duas colunas, template IEEE do
Overleaf, até 8 páginas). A prévia em PDF foi gerada fora do Overleaf; **a versão
oficial deve ser compilada no Overleaf** a partir do `.zip`. Para trocar o PDF do
botão, substitua `artigo_final_v3_previa.pdf` pelo PDF compilado, com o mesmo nome.

## Roteiro do projeto

| Fase | Conteúdo | Status |
|---|---|---|
| 1 | Fundamentação e revisão bibliográfica | referências levantadas |
| 2 | Arquitetura da engine + estruturas de dados base | **concluída** (`exemplos/` + `src/`) |
| 3 | Algoritmo core | **concluída** — ondas de Gerstner + nível do mar ✅ · DEM real ✅ · CDLOD (quadtree + seleção + morphing) ✅ |
| 4 | Avaliação experimental + artigo | **concluída, exceto um item** — benchmark + gráficos ✅ · RAM/VRAM isolada por modo ✅ · frustum culling ✅ · artigo ✅ (falta só compilar no Overleaf e conferir o limite de 8 páginas) · **trabalho futuro:** repetir o benchmark em GPU integrada / celular |

## Referências

**Obrigatórias do eixo**

1. Tanner, C. C.; Migdal, C. J.; Jones, M. T. (1998). *The Clipmap: A Virtual Mipmap.*
2. Welch, R. (2019). *Real-time ocean simulation* (TCC de B.Sc.). Disponível em:
   ryanwelch.co.uk/project/ocean-simulation.

**Complementares** (uso a confirmar com o professor)

3. Clasen, M.; Hege, H.-C. (2006). *Terrain Rendering using Spherical Clipmaps.*
4. Strugar, F. (2009). *Continuous Distance-Dependent Level of Detail for Rendering Heightmaps* (CDLOD).
5. Fournier, A.; Reeves, W. T. (1986). *A Simple Model of Ocean Waves.*
6. DiPaola, F.; Bhardwaj, A.; Sam, L. (2023). *Generating an interactive online map of future sea level rise along the North Shore of Vancouver* (arXiv:2304.07469).
7. Brown, I.; Jude, S. et al. (2006). *Dynamic Simulation and Visualisation of Coastal Erosion.*

Título, autoria e ano das referências foram conferidos contra a fonte original
— ver o item 8 de `CLAUDE.md` para o histórico das 2 correções encontradas
(título/ano de Strugar; título de Welch, que na especificação oficial do
eixo aparece erroneamente como "GPU Clipmaps and Ocean Simulation").
**Ainda não confirmados:** o intervalo de páginas de Strugar e de Tanner et al.
(omitido do artigo por isso) e o tipo/ano do trabalho de Welch (o artigo o cita
como página web, sem data).

**Dados e mídia**

- AWS Terrain Tiles (`registry.opendata.aws/terrain-tiles`) — DEM, formato terrarium.
- Fontes primárias do DEM: NASA SRTM (terra) e GEBCO (batimetria).
- Foto de referência: "Baía de Santos, vista da Ponta da Praia", Emilio Pechini,
  Wikimedia Commons, CC BY 2.0 — ver `src/data/referencia_santos_CREDITO.txt`.

## Integrantes

| Nome | RA | E-mail |
|---|---|---|
| Guilherme Augusto Scaglia | 111598 | scaglia@alunos.fho.edu.br |
| João Pedro Denardo | 113036 | denardo749@alunos.fho.edu.br |
| Pedro Henrique Oliveira de Souza | 113364 | pedro1204@alunos.fho.edu.br |

## Agradecimentos

Ao professor **Renato Luciano Cagnin**, pela orientação na disciplina de
Computação Gráfica.

---

Projeto acadêmico — uso educacional.
