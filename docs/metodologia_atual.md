# Metodologia implementada (estado atual) — para comparação

Documento de referência técnica: descreve **exatamente o que está implementado
e testado** no código, com valores exatos de parâmetros, para comparar
lado a lado com outra versão/planejamento (ex.: um rascunho de artigo escrito
por outro integrante do grupo). Data de referência: código em `src/`, testado
com render headless numa GPU real (NVIDIA RTX 3060).

## 1. Objetivo

Visualizador 3D interativo que renderiza um terreno costeiro real com nível
de detalhe adaptativo (CDLOD) e uma superfície oceânica com ondas de Gerstner,
com nível do mar ajustável, para visualizar quais áreas ficam submersas em
cenários de subida do mar de **0 / +0,5 / +1 / +2 m** (ajuste contínuo permite
ir além disso na demonstração).

## 2. Área de estudo e fonte de dados

| | Valor |
|---|---|
| Local | Baixada Santista (Santos, São Vicente, Guarujá — SP) |
| Bounding box | lat **-23,70 a -24,10** · lon **-46,60 a -46,05** |
| Fonte do DEM | **AWS Terrain Tiles** (`registry.opendata.aws/terrain-tiles`), formato *terrarium* (PNG; altura = R·256+G+B/256−32768), **sem chave de API** |
| Dados primários | NASA SRTM (terra, ~30 m) + GEBCO (batimetria) |
| Zoom / resolução de origem | zoom 11 |
| Pós-processamento | remoção de *spikes* por mediana 3×3 (2 passadas, limiar 60 m); reamostragem bilinear para 1024×1024; piso em -40 m |
| Exagero vertical | **6×** (a região tem ~50 km de largura para ~1,2 km de relevo real, razão ≈ 40:1 — sem exagero a Serra do Mar não aparece) |
| Modo alternativo | terreno procedural: ruído Simplex, 5 oitavas, persistência 0,5, frequência base 2,0 |

## 3. Representação do terreno na GPU

- A matriz de alturas (1024×1024 float32) sobe como **textura de 1 canal (R32F)**, filtro bilinear.
- **Não** existe uma malha de vértices fixa correspondendo 1:1 ao heightmap. Existe uma **grade unitária reusável**, e o vertex shader amostra a altura na textura para cada instância dessa grade (*displacement mapping*).

## 4. LOD — CDLOD (Strugar, 2010), implementação simplificada

| Parâmetro | Valor implementado |
|---|---|
| Estrutura | quadtree |
| Profundidade máxima | **5 níveis** (raiz + 5 subdivisões, até 4⁵ = 1024 folhas no limite teórico) |
| Subdivisões por bloco | **32×32** (= 33×33 vértices, 2048 triângulos por bloco) |
| Critério de seleção | um nó desce para os filhos se `distância_câmera_à_borda < tamanho_do_nó × 2,2`; senão desenha o próprio nó |
| Alcance do LOD | **proporcional ao tamanho de cada bloco** (não uma tabela de raios fixos por nível — mas equivalente: como o tamanho do bloco dobra a cada nível, o alcance também dobra, exatamente como um esquema de raio-base com duplicação) |
| Morphing anti-*crack* | sim — vértices de índice ímpar da grade deslizam para a posição dos pares conforme a distância cresce dentro da faixa de transição de cada bloco (`morph_start = borda_interna + 0,55·faixa`, `morph_end = borda_interna×2`) |
| Blocos ativos (medido) | ~200–230 no uso típico (câmera a média altura sobre a costa) |
| Malha "ingênua" de comparação | 1 única grade na resolução total (1024×1024 → ~2,1 M triângulos), usada só para o experimento de custo/benefício |

## 5. Água — ondas de Gerstner (Fournier & Reeves, 1986)

| Parâmetro | Valor implementado |
|---|---|
| Nº de componentes de onda | **6** (marulho longo → respingo curto) |
| Amplitudes | 1,10 / 0,90 / 0,50 / 0,28 / 0,14 / 0,07 |
| Comprimentos de onda (λ) | 70 / 48 / 26 / 14 / 7 / 4 (unidades de mundo) |
| Velocidades de fase | 8,5 / 7,0 / 5,5 / 4,0 / 3,0 / 2,2 |
| Nitidez (*steepness* Q) | 0,60 / 0,55 / 0,50 / 0,42 / 0,35 / 0,28 — **decrescente com a frequência**, não fixa, para evitar auto-interseção das ondas mais curtas |
| Normalização de Q | `Q_i = steepness_i / (frequência_i · amplitude_i · nº_de_ondas)` |
| Direções | 6 direções fixas, distribuídas ao redor do círculo |
| Normal | calculada analiticamente (derivada da soma das ondas), não por diferenças finitas |
| Shading | difuso de Lambert + especular Blinn-Phong (expoente 90) + Fresnel de Schlick + transparência (α = 0,80) |
| Malha da água | plano de 256×256 subdivisões, 1,6× maior que o terreno (alcança o horizonte) |

## 6. Terreno — cor e iluminação

- Cor por altitude normalizada (0 = nível do mar, 1 = ponto mais alto): restinga → Mata Atlântica → encosta densa → rocha exposta.
- Inclinação (`1 − normal.y`) força rocha exposta nas escarpas íngremes, independente da altitude.
- Faixa abaixo do `u_sea_level` recebe um tingimento verde-escuro (mais forte quanto mais fundo) — o realce de "área submersa".
- Iluminação difusa de Lambert + névoa de distância (mistura com a cor do céu).
- Modo de depuração (`u_debug_lod`): colore cada bloco pela profundidade no quadtree.

## 7. Câmera e cenários interativos

| Parâmetro | Valor |
|---|---|
| FOV vertical | 60° |
| Near / far | 0,1 / 2000 unidades |
| Velocidade normal / turbo | 40 / 120 unidades de mundo por segundo |
| Sensibilidade do mouse | 0,12°/pixel |
| Cenários de nível do mar (teclas 1-4) | **0 / +0,5 / +1 / +2 m** |
| Ajuste contínuo (`,`/`.`) | ±0,8 m/s |
| 1 unidade de mundo ≈ | 167 m reais (mundo de 300 u.m. ≈ 50 km de extensão real) |

## 8. Avaliação experimental (já executada)

- **Método:** benchmark headless (sem janela), sincronizando a GPU a cada frame (`ctx.finish()`), 30 frames de aquecimento + 150 medidos, por combinação.
- **Variáveis:** `{sem LOD, CDLOD, CDLOD sem morphing}` × resolução do heightmap `{256, 512, 1024, 1536, 2048}` × 4 posições de câmera.
- **GPU de teste:** NVIDIA RTX 3060.
- **Métricas coletadas por combinação:** tempo de frame (média/p50/p95, ms) e FPS; **RAM do processo** (RSS, via `psutil`); **VRAM usada e utilização de GPU** (via `nvidia-smi`, quando disponível — placas não-NVIDIA ficam sem esses dois campos, sem quebrar o benchmark).
- **Resultado (desempenho):** com CDLOD, tempo de frame ~constante (~1 ms) em qualquer resolução (~0,4 M triângulos sempre desenhados). Sem LOD, o tempo cresce linearmente com a resolução. As curvas se cruzam por volta de **5 milhões de triângulos** — o "ponto de virada" a partir do qual o CDLOD compensa nessa GPU (em outra GPU esse ponto pode ser diferente). Custo do morphing: dentro do ruído de medição (~gratuito).
- **Resultado (recursos):** RAM do processo cresce de ~110 MB (heightmap 256²) a ~255 MB (2048²) — reflete o tamanho da textura de altura e dos buffers de vértice/índice, não o modo de LOD. VRAM cresce de ~740 MB a ~910 MB pelo mesmo motivo. **Importante:** neste benchmark as 3 condições compartilham a mesma cena (o VAO do CDLOD e o da malha ingênua ficam residentes juntos), então RAM/VRAM não isolam o ganho de memória do LOD — só mostram o crescimento com a resolução do DEM. Isolar isso exigiria montar cenas separadas por condição (melhoria futura).
- **Saídas:** `bench/resultados.csv` + 5 gráficos (`bench/*.png`, incluindo `recursos_vs_resolucao.png`).

## 9. Stack tecnológica

Python 3.11 · ModernGL 5.11 (OpenGL 3.3 core / GLSL 330) · GLFW 2.7 · PyGLM 2.7
· NumPy · Pillow · opensimplex (modo procedural) · matplotlib (gráficos do
benchmark). **Sem** rasterio/GDAL — o DEM é lido via tiles PNG (ver seção 2).

## 10. Estrutura de arquivos atual

```
ComputacaoGrafica/
├── requirements.txt
├── README.md
├── docs/                    (este arquivo + guia de apresentação + PDF-resumo)
├── bench/                   (resultados.csv + gráficos)
├── exemplos/
│   ├── janela.py            (fundamentos: janela + contexto OpenGL)
│   └── triangulo.py         (fundamentos: VBO/VAO/shaders)
└── src/
    ├── dem.py                (DEM real — seção 2)
    ├── heightmap.py          (procedural + grade unitária do CDLOD)
    ├── lod.py                (quadtree + seleção — seção 4)
    ├── water.py               (geometria do plano de água)
    ├── shaders/terrain.*      (seções 4 e 6)
    ├── shaders/water.*        (seção 5)
    ├── camera.py              (seção 7)
    ├── scene.py               (classe Cena: monta tudo na GPU + desenha 1 frame)
    ├── hud.py                 (legenda de comandos + foto de referência)
    ├── main.py                (janela + input + laço)
    └── bench.py               (seção 8)
```

## 11. O que ainda falta (não é código)

- Relatório da Etapa 1 (revisão bibliográfica).
- Redação do artigo IEEE (metodologia, resultados, conclusão) usando os
  valores e resultados **deste documento** como fonte da verdade.
- Confirmar com o professor se as referências complementares (Strugar,
  Fournier & Reeves, Brown et al., estudo de Vancouver) podem ser citadas
  junto às duas obrigatórias do eixo (Tanner/Migdal/Jones, Welch).
- Ideal: rodar o benchmark também em outras GPUs (inclusive integradas).
