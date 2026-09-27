# CLAUDE.md — Projeto de Computação Gráfica (Visualização de Elevação Costeira)

Lido automaticamente pelo Claude Code ao iniciar nesta pasta. Mantenha atualizado.

> **Se você (Claude) está lendo isto numa sessão nova de outro integrante do
> grupo:** o estado técnico real do projeto está em
> [docs/metodologia_atual.md](docs/metodologia_atual.md) (valores exatos de
> cada parâmetro, extraídos do código) e [docs/APRESENTACAO.md](docs/APRESENTACAO.md)
> (guia de ponta a ponta). Antes de assumir qualquer coisa sobre parâmetros,
> estrutura de pastas ou o que já foi implementado, **leia esses dois arquivos
> primeiro** — este CLAUDE.md é só um resumo de orientação.

## Visão geral do projeto

Trabalho final da disciplina de Computação Gráfica (Engenharia de Computação,
10º semestre, FHO/Uniararas). Eixo 6 (Topografia), adaptado para o cenário de
**erosão costeira / subida do nível do mar**.

**Objetivo técnico:** renderizar um terreno costeiro real com nível de
detalhe adaptativo (CDLOD) e simular uma superfície oceânica (ondas de
Gerstner) com nível ajustável, para visualizar quais áreas ficam submersas
em cenários de subida do mar (0 / +0,5 m / +1 m / +2 m).

**Grupo:**
- Guilherme Augusto Scaglia — RA 111598 — scaglia@alunos.fho.edu.br
- João Pedro Denardo — RA 113036 — denardo749@alunos.fho.edu.br
- Pedro Henrique Oliveira de Souza — RA 113364 — pedro1204@alunos.fho.edu.br

## Stack tecnológica (o que está REALMENTE em uso)

- Python 3.11 (ambiente em `.venv`)
- ModernGL 5.11 (OpenGL 3.3 core / GLSL 330)
- GLFW 2.7 (janela e input)
- PyGLM 2.7 (álgebra linear: vetores, matrizes, view/projection)
- NumPy, Pillow, opensimplex (ruído procedural), matplotlib (gráficos do benchmark)
- **Não usamos** `rasterio`/GDAL — descartado por instabilidade de instalação
  no Windows fora do conda. O DEM real é lido via tiles PNG da AWS (ver abaixo).

## Fonte de dados de elevação (implementado e testado)

- **Fonte:** AWS Terrain Tiles (`registry.opendata.aws/terrain-tiles`),
  formato *terrarium*, **sem chave de API**. Dados primários: NASA SRTM
  (terra) + GEBCO (batimetria).
- **Local:** Baixada Santista — Santos, São Vicente, Guarujá (SP).
- **Bounding box real usada:** lat -23,70 a -24,10 · lon -46,60 a -46,05
  (mais larga que um recorte só de Cubatão: inclui a escarpa da Serra do
  Mar **e** o estuário/oceano, necessários para a inundação fazer sentido).
- **Implementado em** `src/dem.py`: baixa e cacheia tiles, remove *spikes*
  (mediana 3×3, 2 passadas), reamostra para 1024×1024, aplica exagero
  vertical 6× (declarado — necessário porque a região real tem razão
  relevo:largura de ~40:1).

## Estrutura de arquivos ATUAL

```
ComputacaoGrafica\
├── CLAUDE.md                   (este arquivo)
├── README.md
├── requirements.txt
├── docs\
│   ├── metodologia_atual.md/.pdf   (fonte da verdade sobre parâmetros — leia primeiro)
│   ├── DESENVOLVIMENTO.md          (relato de como o projeto foi construído, fase a fase)
│   ├── APRESENTACAO.md             (guia de ponta a ponta / estudo pra apresentação)
│   ├── COMPLEMENTO_TECNICO.md      (companheiro do artigo: glossário de todo termo técnico,
│   │                                por que cada lib, como tudo é calculado, com fórmulas)
│   ├── resumo_projeto.pdf          (resumo de 3 páginas)
│   └── artigo_v2.pdf               (rascunho do artigo científico, IEEE)
├── bench\                        (resultados.csv + gráficos do benchmark)
├── exemplos\
│   ├── janela.py                  (concluído — fundamentos: janela + contexto OpenGL)
│   └── triangulo.py               (concluído — fundamentos: VBO/VAO/shaders)
└── src\
    ├── dem.py                     (DEM real da Baixada Santista)
    ├── heightmap.py               (terreno procedural + grade unitária do CDLOD)
    ├── lod.py                     (quadtree + seleção de blocos por distância)
    ├── water.py                   (geometria do plano de água)
    ├── shaders\terrain.*          (heightmap por bloco, morphing, cor, faixa submersa)
    ├── shaders\water.*            (ondas de Gerstner, Fresnel, Blinn-Phong)
    ├── camera.py                  (câmera livre)
    ├── scene.py                   (classe Cena: monta tudo na GPU + desenha 1 frame)
    ├── hud.py                     (legenda de comandos + foto de referência)
    ├── main.py                    (janela + input + laço)
    └── bench.py                   (mede FPS com/sem LOD -> CSV + gráficos)
```

Não existem mais `passo1_janela/`, `passo2_triangulo/` nem `heightmap.py`
na raiz — foram renomeados/reorganizados para `exemplos/` e `src/`.

## Status atual / o que falta

1. ✅ Terreno (DEM real + procedural), câmera livre, textura de altura.
2. ✅ CDLOD: quadtree, seleção por distância, morphing anti-*crack*.
3. ✅ Água: 6 ondas de Gerstner, Fresnel, Blinn-Phong, nível ajustável.
4. ✅ Avaliação de desempenho: benchmark headless achou o "ponto de virada"
   (~5 M triângulos numa RTX 3060) + perfilamento de RAM/VRAM/GPU (`psutil` +
   `nvidia-smi`) — ver `docs/metodologia_atual.md` §8.
5. ✅ UX para leigos (`src/hud.py` + `src/main.py`): tela de boas-vindas
   (`I`), legenda em 2 níveis (`H`: nenhuma→básica→completa), painel de
   status sempre visível (nível do mar + selo colorido + modo LOD/morphing
   + **tempo de render do quadro** — o número que muda de verdade ao
   apertar `L`, já que o FPS da tela fica travado pelo V-Sync), bússola
   (inferior-esquerda), minimapa com marcador de posição (inferior-direita,
   alterna com a foto via `P`), e tecla `R` pra resetar a câmera
   (`Camera.resetar`/`Camera.bearing_graus` em `camera.py`).
7. ⬜ Relatório da Etapa 1 (revisão bibliográfica) — não escrito.
8. ✅ Artigo IEEE — **versão final em `docs/artigo_v3.tex`** (reescrita
   completa a partir do `docs/artigo_v2.pdf` do colega, seguindo o
   "IEEE Conference Template" oficial, com rigor de linguagem/parágrafo em
   português formal). Correções aplicadas em relação ao artigo_v2: (a)
   III-F/Seção IV corrigida — o valor certo é ~8,4 milhões de triângulos
   na resolução máxima testada (2048), não 2,1 milhões (esse é o valor de
   1024); (b) Seção IV ("Resultados e Avaliação de Desempenho") separada
   como seção própria, como a especificação pede; (c) **todas as 7
   referências validadas via busca web em 2026-09** — 2 correções: Strugar
   tinha título/ano errados ("Height Maps"/2010 → correto é "Heightmaps"
   [uma palavra]/2009, conforme o DOI); e a referência [5] (Welch) estava
   citada com o título "GPU Clipmaps and Ocean Simulation" (copiado da
   especificação oficial do eixo), que **não corresponde a nenhuma fonte
   real localizável** — o título verificado e real é "Real-time ocean
   simulation", o TCC (B.Sc.) de 2019 de Ryan Welch, disponível em
   https://ryanwelch.co.uk/project/ocean-simulation/. Esse é o mesmo tipo
   de erro já identificado no item 9 (mixup Tanner/Clasen na especificação
   do professor) — vale reportar ao professor.
9. ⬜ Confirmar com o professor se as referências complementares podem ser
   citadas junto às duas obrigatórias do eixo (o artigo já cita Tanner,
   Migdal & Jones [1998, "The Clipmap"] E Clasen & Hege [2006, "spherical
   clipmaps"] como referências distintas e corretas — mais rigoroso do que
   uma correção anterior deste arquivo, que tinha fundido as duas).
10. ⬜ Ideal: rodar o benchmark também numa GPU mais fraca / mobile.

## Parâmetros principais (valores REAIS do código — ver `docs/metodologia_atual.md` para a lista completa)

| Parâmetro | Valor |
|---|---|
| Oitavas de ruído (modo procedural) | 5 |
| Profundidade da quadtree (CDLOD) | 5 níveis |
| Subdivisões por bloco | 32×32 (33×33 vértices) |
| Fator de seleção do LOD | distância < tamanho_do_bloco × 2,2 |
| Componentes de onda de Gerstner | 6 |
| FOV da câmera | 60° |
| Velocidade de translação | 40 u.m./s (120 turbo) |
| Cenários de nível do mar | 0 / +0,5 / +1 / +2 m |
| Exagero vertical do DEM | 6× |

## Convenções de código

- **Comentários pedagógicos**: o aluno está aprendendo do zero. Todo código
  novo deve explicar o "porquê", não só o "o quê".
- **Passos incrementais**: entregar funcionalidade em pequenos incrementos
  que rodam e mostram algo visível.
- Comentários e nomes de variáveis em português.
- **Sempre validar com render headless** (`moderngl.create_standalone_context()`
  + framebuffer) antes de dizer que algo funciona — esta máquina tem GPU
  NVIDIA de verdade, então dá pra testar shaders/render, não só sintaxe.
  Testar em **múltiplos frames em loop**, não só 1 — um bug real (HUD
  roubando a unidade de textura do heightmap) só aparecia a partir do 2º frame.

## Referências usadas no projeto

**IMPORTANTE — citação corrigida em 2026-09:** a especificação oficial do
professor (Eixo 6) lista o artigo *"Terrain Rendering using Spherical
Clipmaps"* com autoria **C. C. Tanner, C. J. Migdal, M. T. Jones** — NÃO
Clasen & Hege como estava registrado antes aqui. Usar a especificação oficial
como fonte da verdade para a citação no artigo (decisão do usuário: seguir
as ideias apresentadas nesses artigos, sem precisar confirmar com o professor).

- Tanner, Migdal & Jones (1998) — *The Clipmap: A Virtual Mipmap* (obrigatório do eixo, conforme especificação oficial)
- Clasen & Hege (2006) — *Terrain rendering using spherical clipmaps* (complementar; a técnica de clipmap esférico propriamente dita)
- Welch (2019) — *Real-time ocean simulation* (TCC de B.Sc., obrigatório do eixo; título real
  validado via web — a especificação oficial do professor usa o título
  "GPU Clipmaps and Ocean Simulation", que não corresponde a nenhuma fonte
  real encontrada — ver item 8 do checklist acima)
- Strugar (2009) — *Continuous distance-dependent level of detail for rendering heightmaps* (complementar; é o algoritmo realmente implementado — título/ano corrigidos via DOI, ver item 8)
- Fournier & Reeves (1986) — ondas de Gerstner (complementar; é a base matemática real)
- Brown et al. (2006) — visualização dinâmica de erosão costeira (complementar)
- DiPaola, Bhardwaj & Sam (2023) — geovisualização de subida do nível do mar (complementar)

**Pendência:** confirmar com o professor se as referências complementares
podem ser citadas junto às duas obrigatórias do eixo, e reportar a ele o
possível erro de título na referência [5] (Welch) da especificação oficial.
