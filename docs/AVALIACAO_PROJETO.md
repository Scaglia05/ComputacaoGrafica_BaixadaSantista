> **Histórico:** avaliação feita antes das correções finais; os números e problemas aqui citados foram superados. Ver `docs/AVALIACAO_CODIGO_ARTIGO.md` (seção 6).

# Avaliação do projeto — estrutura e métricas

Data: 2026-11-07 · Base: branch `main` (commit `314475b`), código, `bench/` e testes executados nesta avaliação.

## 1. Veredito geral

Projeto sólido para uma disciplina de graduação. O que se destaca: o algoritmo (CDLOD + morphing + frustum culling) é de fato implementado, há testes automatizados que protegem o ponto mais delicado (culling não pode mudar a imagem), existe benchmark reprodutível com CSVs versionados e a documentação é abundante. Os pontos fracos estão menos no código e mais na **robustez estatística das métricas** e em alguns **resíduos de organização**.

| Aspecto | Nota | Comentário curto |
|---|---|---|
| Arquitetura do código | 8/10 | Módulos pequenos, uma responsabilidade cada |
| Testes | 8/10 | 38 testes, todos passam (rodados em 19 s); culling e memória cobertos |
| Rigor das métricas | 6,5/10 | Boa instrumentação, amostra pequena, sem IC, ponto de virada instável |
| Documentação | 8/10 (excesso) | Completa, mas redundante e com versões velhas misturadas |
| Higiene do repositório | 6/10 | Vários `.tex` de versões antigas, `__pycache__` presente |

## 2. Estrutura

### 2.1 Código (`src/`, ~2 300 linhas Python + 286 de GLSL)

| Arquivo | Linhas | Papel |
|---|---|---|
| `main.py` | 423 | janela, input, laço principal |
| `bench.py` | 522 | benchmark headless (maior arquivo) |
| `hud.py` | 441 | legenda, status, bússola, minimapa |
| `scene.py` | 280 | monta tudo na GPU e desenha o quadro |
| `lod.py` | 250 | quadtree, seleção por distância, culling vetorizado |
| `dem.py` | 166 | download/cache dos tiles AWS, limpeza de spikes |
| `camera.py` / `heightmap.py` / `water.py` / `area_alagada.py` | 130 / 125 / 54 / 51 | câmera, malha unitária, água, área submersa |
| `shaders/` | 286 | terrain (heightmap por bloco, morph) e water (Gerstner) |

Pontos positivos:
- **Separação clara** entre dados (`dem`, `heightmap`), algoritmo (`lod`), render (`scene`, shaders) e interface (`hud`, `main`). `lod.py` não depende de OpenGL, o que o torna testável sem GPU.
- A malha unitária reutilizada por todos os blocos (33×33 vértices) é a decisão que dá a economia de memória: o buffer de malha fica em ~0,03 MB contra 134 MB da malha completa a 2048².
- Comentários pedagógicos explicam o porquê (alinhado ao objetivo do aluno).
- Os testes de imagem idêntica com e sem culling e a lição do teste de mutação (registrada no CLAUDE.md) indicam cuidado real com corretude.

Pontos de atenção:
- `bench.py` (522 linhas) e `hud.py` (441) são grandes; `bench.py` mistura medição, perfilamento de memória, CSV e gráficos. Separar medição de plotagem facilitaria reuso.
- Sem pacote/`__init__` nem `pyproject`; a execução depende de rodar a partir de `src/`. Funciona, mas é frágil para outros integrantes.
- `tests/` só roda com a `.venv` ativada (sem ela falha por falta do `glm`). Vale um aviso no README.
- Não há teste para `dem.py` (download, filtro de spikes) nem para `water.py`/`area_alagada.py`.
- `src/__pycache__` aparece no diretório; confirmar que está no `.gitignore` (não está listado entre os arquivos versionados, então provavelmente está).

### 2.2 Documentação e repositório

- 5 documentos técnicos em `docs/` (metodologia, desenvolvimento, apresentação, complemento, resumo) + artigo em 3 versões `.tex` (`artigo_final_abnt`, `_v2_`, `_v4_`) + `artigo_v4.tex` legado. Há **sobreposição considerável** entre `APRESENTACAO`, `DESENVOLVIMENTO` e `COMPLEMENTO_TECNICO`; manter três textos sincronizados é custo recorrente e risco de divergência numérica.
- Recomendação: mover versões antigas do artigo para `docs/historico/` e manter só a v4 na raiz de `artigo_final`.
- 34 commits, com PRs mesclados para as duas features principais — bom histórico.

## 3. Métricas

Hardware: RTX 3060, i5-10400F. Médias abaixo calculadas dos CSVs (4 câmeras por execução; `bench/` original = 1 execução, `bench/v2` = 3 execuções).

### 3.1 Tempo de quadro (ms, média) — benchmark v2, 3 execuções

| Resolução | Malha completa | CDLOD | CDLOD + frustum | Triângulos malha completa | Triângulos CDLOD (média) |
|---|---|---|---|---|---|
| 256² | 0,20 | 1,05 | 0,84 | 261 k | 430 k |
| 512² | 0,52 | 1,07 | 0,85 | 654 k | 430 k |
| 1024² | 0,79 | 1,02 | 0,80 | 2,23 M | 430 k |
| 1536² | 1,13 | 1,01 | 0,78 | 4,85 M | 430 k |
| 2048² | **1,93** | **1,02** | **0,79** | 8,52 M | 430 k |

Leituras:
- O CDLOD tem **custo praticamente constante** (~1,0 ms) independentemente da resolução: confirma a propriedade central da técnica.
- Em baixa resolução o CDLOD é **mais lento** (1,05 ms contra 0,20 ms a 256²), por ter ~178 draw calls e processamento da quadtree em CPU. O ponto de cruzamento fica entre 1024² e 1536² (sem culling) e em torno de 1024² com culling.
- Ganho a 2048²: CDLOD sem culling ≈ 47% mais rápido que a malha completa; com culling ≈ 59%.
- O culling reduz o tempo em ~20–22% (0,84 vs 1,05 ms) e os triângulos em ~40%, coerente com o −22% do README do v2.
- O custo do morphing é desprezível (1,02–1,19 vs 1,05–1,07 ms; dentro do ruído).

### 3.2 Memória

- Buffers alocados a 2048²: **19,2 MB** (CDLOD) × **153,4 MB** (malha completa), 8× menos. Desses, 16,8 MB são a textura de altura, comum aos dois; a malha vai de 134 MB para 0,03 MB.
- RSS do processo a 2048²: ~138 MB (CDLOD) × ~277 MB (completa); pico 191 MB × 595 MB.
- VRAM por `nvidia-smi` (+ ~0 a +160 MB entre antes/depois) é ruidosa porque inclui outros processos do sistema; o valor "alocado" calculado pela aplicação é a métrica confiável.
- A medição **isolada por processo** (um processo por modo/repetição, 3 repetições, desvio muito baixo) é a parte metodologicamente mais forte do conjunto.

### 3.3 Ponto de virada e estabilidade

- Média: CDLOD passa a vencer a malha completa entre ~2,2 M e ~4,8 M triângulos (nos dados acima, entre 1024² e 1536²).
- O README e o CLAUDE.md já reconhecem que o ponto de virada **pelo p95** não reproduziu (2,7 M no artigo × ~4,3 M nas novas execuções). Mesmo o p95 da malha completa a 2048² variou de 2,75 ms para 1,98 ms entre a execução original e as novas. Isso confirma a limitação declarada: a execução original tem cauda mais ruidosa.

## 4. Fragilidades metodológicas (por ordem de importância)

1. **Pouca amostra / sem intervalo de confiança.** 3 execuções × 4 câmeras. Reportar média ± desvio (ou IC bootstrap) e usar as 3 execuções v2 como principal; tratar a original como histórica.
2. **Hardware único.** Só RTX 3060; conclusões sobre "ponto de virada" não generalizam. Já é item 10 do checklist.
3. **Tempo de quadro com baixa resolução de timer.** Valores de 0,14–0,3 ms são difíceis de medir via CPU; confirmar se o benchmark usa `glFinish`/query de GPU. Se for tempo de CPU, a comparação em baixas resoluções é sensível ao overhead de driver.
4. **Colunas de GPU e VRAM de `nvidia-smi`** variam muito entre linhas (ex.: `gpu_util_pct` de 5 a 92) e parecem misturar amostras de outros processos. Não usar como evidência principal.
5. **Número de triângulos do CDLOD é constante** (430 082 de média) porque a câmera de benchmark seleciona a mesma configuração; a cena não testa movimento contínuo nem cenários com muito mais blocos.
6. **Sem teste de qualidade visual** além da imagem idêntica com/sem culling (ex.: erro de altura vs. LOD máximo; presença de cracks medida automaticamente).
7. Atenção a números divergentes entre documentos: o README/CLAUDE.md cita ponto de virada ~2,7 M (p95) / ~4,2 M (média); o v2 dá ~2,3 M com culling. Convém uma tabela única citada em todos os lugares.

## 5. Recomendações (priorizadas)

1. Fechar o artigo com a tabela da seção 3.1 (3 execuções) e escrever as limitações 1–3 acima explicitamente.
2. Adicionar média ± desvio nos gráficos de `bench/v2` e um script único `bench/resumo.py` que gere a tabela, para os números do texto virem do CSV e não de cópia manual.
3. Arrumar `docs/`: `historico/` para artigos antigos; um único documento de números (`metodologia_atual.md`) e os outros apontando para ele.
4. Testes: cobrir `dem.py` (spike removal em array sintético) e `area_alagada.py`.
5. README: instruir a ativar a `.venv` antes de `python -m unittest ...`.
6. Se houver acesso a um notebook com GPU integrada, rodar o benchmark nele — é o dado que mais agregaria ao artigo.
