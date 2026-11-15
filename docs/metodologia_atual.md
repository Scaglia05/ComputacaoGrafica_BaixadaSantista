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

## 4. LOD — CDLOD (Strugar, 2009), implementação simplificada

| Parâmetro | Valor implementado |
|---|---|
| Estrutura | quadtree |
| Profundidade máxima | **5 níveis** (raiz + 5 subdivisões, até 4⁵ = 1024 folhas no limite teórico) |
| Subdivisões por bloco | **32×32** (= 33×33 vértices, 2048 triângulos por bloco) |
| Critério de seleção | um nó desce para os filhos se `distância_câmera_à_borda < tamanho_do_nó × 2,2`; senão desenha o próprio nó |
| Alcance do LOD | **proporcional ao tamanho de cada bloco** (não uma tabela de raios fixos por nível — mas equivalente: como o tamanho do bloco dobra a cada nível, o alcance também dobra, exatamente como um esquema de raio-base com duplicação) |
| Morphing anti-*crack* | sim, com a distância **horizontal** do vértice à câmera (mesma métrica da seleção) — vértices de índice ímpar da grade deslizam para a posição dos pares conforme a distância cresce dentro da faixa de transição de cada bloco (`morph_start = borda_interna + 0,55·faixa`, `morph_end = borda_interna×2`) |
| Blocos ativos (medido) | 100 a 184 por quadro nas 4 câmeras do benchmark; 52 a 74 com frustum culling |
| Frustum culling | opcional (tecla `C`): caixa (AABB) por nó contra os 6 planos do frustum (Gribb-Hartmann), vetorizado em NumPy; margem de 2 texels; a imagem é idêntica com e sem culling |
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
| Malha da água | plano de 256×256 vértices (130.050 triângulos), 480 u.m. de lado (1,6× o terreno, alcança o horizonte) |

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
- **Variáveis:** `{sem LOD, CDLOD, CDLOD sem morphing, CDLOD com frustum culling}` × resolução do heightmap `{256, 512, 1024, 1536, 2048}` × 4 posições de câmera, em 3 execuções independentes.
- **GPU de teste:** NVIDIA RTX 3060 (única).
- **Dados usados no artigo:** `bench/v3/` (`run1` a `run3` e `memoria.csv`). A série `bench/v2/` (versão `3f30ace`, outra sessão) é citada na limitação 5 do artigo. Resumo estatístico: `python src/resumo_bench.py bench/v3/run1 bench/v3/run2 bench/v3/run3`.
- **Desempenho:** com CDLOD o tempo de quadro fica em cerca de 1 ms em qualquer resolução. Sem LOD, cresce com a malha (0,18 ms a 256² e 2,09 ms a 2048², média). As curvas se cruzam em cerca de **5 milhões de triângulos** (4,4 a 5,6 M conforme o critério e a execução); com culling, em cerca de 3 M. O custo do morphing é de no máximo 0,06 ms (dentro do ruído). O culling reduz o tempo de quadro em 22% em média (−37% nas câmeras rasante e de encosta).
- **Memória (cada modo em processo isolado):** a 2048², 19 MB (CDLOD) contra 153 MB (malha completa) de buffers; VRAM 24 contra 154 MB; pico de RAM 183 contra 593 MB. Morphing e culling não alteram a memória.
- **Fendas (`python src/verificar_fendas.py`):** em 40 câmeras aleatórias, 512 fendas finas sem morphing e 1 com morphing.
- **Limites:** uma única GPU; sem intervalos de confiança; o ponto de virada variou entre sessões; o custo fixo de cerca de 1 ms do CDLOD é provavelmente de CPU (Python); o popping não foi medido.

## 9. Stack tecnológica

Python 3.11 · ModernGL 5.11 (OpenGL 3.3 core / GLSL 330) · GLFW 2.7 · PyGLM 2.7
· NumPy · Pillow · opensimplex (modo procedural) · matplotlib e psutil (benchmark).
**Sem** rasterio/GDAL — o DEM é lido via tiles PNG (ver seção 2).

## 10. Estrutura de arquivos

Ver a seção "Estrutura do projeto" do `README.md`.

## 11. O que ainda falta (não é código)

- Relatório da Etapa 1 (revisão bibliográfica).
- Confirmar com o professor se as referências complementares (Strugar, Fournier & Reeves, Brown et al., estudo de Vancouver) podem ser citadas junto às duas obrigatórias do eixo (Tanner/Migdal/Jones, Welch), e reportar o título divergente de Welch na especificação.
- Compilar o artigo no Overleaf e conferir as 8 páginas.
- Rodar o benchmark também em outras GPUs (inclusive integradas).
