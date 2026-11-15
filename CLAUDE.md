# CLAUDE.md — Projeto de Computação Gráfica (Visualização de Elevação Costeira)

Lido automaticamente pelo Claude Code ao iniciar nesta pasta. Mantenha atualizado e curto.

> **Se você (Claude) está lendo isto numa sessão nova de outro integrante do grupo:**
> o estado técnico real está em [docs/metodologia_atual.md](docs/metodologia_atual.md)
> (valores de cada parâmetro, extraídos do código) e em
> [docs/TEORIA_DE_PONTA_A_PONTA.md](docs/TEORIA_DE_PONTA_A_PONTA.md) (como funciona cada
> parte e por que). Antes de assumir parâmetros, estrutura ou o que já foi
> implementado, leia esses dois arquivos. Este CLAUDE.md é só um resumo.

## Visão geral

Trabalho final de Computação Gráfica (Engenharia de Computação, 10.º semestre,
FHO/Uniararas), Eixo 6 (Topografia), adaptado para erosão costeira e subida do
nível do mar. O sistema roda apenas em computador (Windows, Python, OpenGL 3.3 core).

**Objetivo técnico:** renderizar terreno costeiro real com nível de detalhe adaptativo
(CDLOD) e uma superfície oceânica (ondas de Gerstner) de nível ajustável, para ver
quais áreas ficam submersas em 0 / +0,5 / +1 / +2 m.

**Grupo:**
- Guilherme Augusto Scaglia — RA 111598 — scaglia@alunos.fho.edu.br
- João Pedro Denardo — RA 113036 — denardo749@alunos.fho.edu.br
- Pedro Henrique Oliveira de Souza — RA 113364 — pedro1204@alunos.fho.edu.br

## Stack (o que está em uso)

Python 3.11 (`.venv`) · ModernGL 5.11 (OpenGL 3.3 core / GLSL 330) · GLFW 2.7 ·
PyGLM 2.7 · NumPy · Pillow · opensimplex · matplotlib · psutil. Sem `rasterio`/GDAL
(instalação instável no Windows). O DEM vem de tiles PNG da AWS.

## Dados de elevação

- **Fonte:** AWS Terrain Tiles (`registry.opendata.aws/terrain-tiles`), formato
  *terrarium*, sem chave de API; dados primários NASA SRTM (terra) e GEBCO (batimetria).
- **Região:** Baixada Santista (Santos, São Vicente, Guarujá). Caixa: lat −23,70 a
  −24,10, lon −46,60 a −46,05 (inclui a escarpa da Serra do Mar e o estuário).
- **Tratamento** (`src/dem.py`): cache dos tiles, remoção de *spikes* (mediana 3×3,
  2 passadas, limiar 60 m), reamostragem para 1024×1024 e exagero vertical de 6×
  (declarado: a região tem razão relevo:largura de cerca de 40:1).

## Estrutura do projeto

A árvore completa está na seção "Estrutura do projeto" do [README.md](README.md).
Resumo: `src/` (engine e shaders), `tests/` (unittest), `exemplos/` (fundamentos),
`bench/v3/` (dados do artigo) e `bench/v2/` (série anterior citada no artigo),
`docs/` (guias, metodologia, especificação do professor e `docs/artigo_final/`).

## Status

1. ✅ Terreno (DEM real e procedural), câmera livre, textura de altura.
2. ✅ CDLOD: quadtree, seleção por distância, morphing anti-*crack* (distância horizontal).
3. ✅ Água: 6 ondas de Gerstner, Fresnel, Blinn-Phong, nível ajustável.
4. ✅ Frustum culling vetorizado (a imagem é idêntica com e sem culling) e memória medida por modo, em processo isolado.
5. ✅ Benchmark headless numa RTX 3060: ponto de virada em cerca de 5 M de triângulos (4,4 a 5,6 M); com culling, cerca de 3 M. Culling: −22% no tempo de quadro. Memória a 2048²: 19 MB (CDLOD) × 153 MB (malha completa). Morphing: 512 fendas finas sem ele, 1 com ele (`src/verificar_fendas.py`).
6. ✅ UX (`src/hud.py`, `src/main.py`): boas-vindas, legenda em 2 níveis, painel de status com o tempo de render do quadro, bússola, minimapa, tecla `R`.
7. ✅ Artigo: `docs/artigo_final/artigo_final_v5_abnt.tex` (ABNT em duas colunas sobre o template IEEE do Overleaf; 8 páginas). Pacote para o Overleaf: `artigo_final_v5_overleaf.zip`. O PDF tem o título do artigo como nome. A etiqueta `artigo-v5` é citada no artigo.
8. ⬜ Compilar o artigo no Overleaf e confirmar as 8 páginas (hoje só compilado localmente, com MiKTeX).
9. ⬜ Confirmar com o professor: referências complementares podem ser citadas junto às obrigatórias? Limite de páginas (8 ou 10)? Reportar que, na especificação, "GPU Clipmaps and Ocean Simulation" (Welch) não corresponde a nenhuma fonte localizável (o trabalho real é "Real-time ocean simulation", 2019) e que "Terrain Rendering using Spherical Clipmaps" é de Clasen e Hege (2006), não de Tanner, Migdal e Jones.
10. ⬜ Rodar o benchmark em outras GPUs (inclusive integradas). Bloqueado por hardware: esta máquina só tem a RTX 3060.
11. ⬜ Relatório da Etapa 1 (revisão bibliográfica): não escrito.

Limitações declaradas no artigo: uma única GPU, sem intervalos de confiança, ponto de
virada variável entre sessões (v2: 3,4 a 4,3 M; v3: 4,4 a 5,6 M), custo do CDLOD
provavelmente de CPU, exatidão vertical do DEM não validada, popping não medido.

## Testes

`python -m unittest discover -s tests -v` — 51 testes, só biblioteca padrão (sem pytest).
Parte deles cria contexto OpenGL sem janela; sem GPU eles são pulados. O mais importante é
`test_imagem_identica_*`: o culling NÃO pode mudar a imagem. Lição registrada:
`np.array(glm.mat4)` já vem como `[linha][coluna]` (não transpor).

## Parâmetros principais (valores do código; lista completa em `docs/metodologia_atual.md`)

| Parâmetro | Valor |
|---|---|
| Profundidade da quadtree | 5 níveis (1365 nós) |
| Subdivisões por bloco | 32×32 (33×33 vértices) |
| Critério de seleção | distância à borda do bloco < tamanho × 2,2 |
| Ondas de Gerstner | 6 |
| Projeção | FOV 60°, planos 0,1 e 2000 (`camera.py`, fonte única) |
| Velocidade da câmera | 40 u.m./s (120 com Shift) |
| Cenários de nível do mar | 0 / +0,5 / +1 / +2 m |
| Exagero vertical do DEM | 6× |

## Convenções

- Comentários pedagógicos (o aluno está aprendendo): explique o "porquê". Comentários e nomes em português.
- Passos incrementais, que rodam e mostram algo visível.
- Valide sempre com render headless (`moderngl.create_standalone_context()` + framebuffer),
  em vários quadros em laço, não só um (um bug real só aparecia a partir do 2.º quadro).
- Não sobrescreva dados do artigo: grave medições novas com `python src/bench.py --saida <pasta>`.

## Referências do projeto

Fonte oficial: [`docs/especificacao_eixo6.pdf`](docs/especificacao_eixo6.pdf) (documento do
professor; define as etapas e a estrutura do artigo; o grupo informou que o limite real é
de até 10 páginas, enquanto o PDF diz 4 a 8).

- Tanner, Migdal e Jones (1998) — *The Clipmap: A Virtual Mipmap* (obrigatória; p. 151-158)
- Welch (2019) — *Real-time ocean simulation* (obrigatória; projeto final de BSc, página web)
- Clasen e Hege (2006) — *Terrain rendering using spherical clipmaps* (complementar)
- Strugar (2009) — *Continuous distance-dependent level of detail for rendering heightmaps* (complementar; é o algoritmo implementado; p. 57-74)
- Fournier e Reeves (1986) — ondas de Gerstner (complementar)
- Brown et al. (2006) — erosão costeira (complementar)
- DiPaola, Bhardwaj e Sam (2023) — subida do nível do mar (complementar)

As páginas de Strugar e de Tanner foram confirmadas por busca em fontes secundárias,
não nas páginas das editoras.
