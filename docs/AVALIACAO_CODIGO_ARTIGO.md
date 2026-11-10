# Reavaliação do código frente ao artigo (v5)

Data: 2026-11-07. Método: li `lod.py`, `scene.py`, `camera.py`, `dem.py`, `area_alagada.py`, os quatro shaders e as constantes de `bench.py`, e conferi cada afirmação técnica do artigo contra eles. Também medi o custo do culling. **Não reexecutei o benchmark completo**: os CSVs vêm do commit `3f30ace` (o que o artigo cita), e a branch atual tem o código simplificado.

## 1. O que o código confirma (artigo = código)

| Afirmação do artigo | Onde está no código | Situação |
|---|---|---|
| Critério de subdivisão `d < τ · 2,2`, d no plano horizontal até a borda do bloco | `lod.py:107-117,142`, `scene.py:62` | ✔ |
| Quadtree com L = 5, 1365 nós, 4⁵ = 1024 folhas, grade 33×33 (2048 triângulos/bloco) | `lod.py:73-104`, `scene.py` | ✔ (1365 nós conferido) |
| Geomorphing: início a 55% entre `r` e `2r`, fim em `2r`, vértice ímpar → par | `scene.py:266-268`, `terrain.vert:49-52` | ✔ |
| Culling: AABB com faixa vertical do heightmap + margem de texels, Gribb–Hartmann, teste conservador | `lod.py:152-239` | ✔ |
| NumPy: ~0,1 ms vs ~9 ms em laço Python para 1365 nós | medido agora: **0,11 ms** vs **7,7 ms** | ✔ (mesma ordem; "cerca de 8 ms" seria mais exato) |
| Cor por altitude (limiares 0,04 e 0,55), mistura de rocha por inclinação (×2,2, até 55%) | `terrain.frag:35-45` | ✔ |
| Lambert com ambiente: `0,25 + 0,85·max(n·l, 0)` | `terrain.frag:51` | ✔ |
| Terreno submerso: mistura de 65% com tom azul-esverdeado | `terrain.frag:57-61` | ✔ |
| Névoa: começa a 120 u.m. e chega a 75% em 315 u.m. | `terrain.frag:83` (120 + 260·0,75 = 315) | ✔ |
| Normal por diferenças finitas a 2,5 texels | `terrain.vert:72-79` | ✔ |
| 6 ondas, amplitudes {1,10; 0,90; 0,50; 0,28; 0,14; 0,07}, λ {70; 48; 26; 14; 7; 4} | `water.vert:35-36` | ✔ |
| Normal analítica da água, Fresnel–Schlick, Blinn–Phong, α = 0,80 | `water.vert:64-67`, `water.frag` | ✔ |
| FOV 60°, planos 0,1/2000, 40/120 u.m./s, pitch ±89°, mar contínuo a 0,8 m/s | `camera.py`, `main.py:311,362` | ✔ |
| σ = 167 m/u.m., E = 6, piso de −40 m, mediana 3×3 em duas passadas | `dem.py` (recalculei σ ≈ 167) | ✔ |
| Benchmark: 30 quadros de aquecimento, 150 medidos, `ctx.finish()`, 5 resoluções, 4 câmeras, modos em processos separados | `bench.py:67-73,165-174` | ✔ |
| "Testes automatizados confirmam imagem idêntica com e sem descarte" | `tests/test_frustum.py` | ✔ (rodei: 51 testes OK) |

## 2. Divergências entre código e artigo (ordenadas por importância)

1. **Nitidez Q das ondas.** O artigo (Tabela 2 e Seção 3.5) diz que Q decresce de 0,60 a 0,28 e entra direto na Equação (8). No código, 0,60–0,28 são os valores *brutos* (`STEEP`), e o Q efetivo é `Q = STEEP / (ω_i·A_i·6)` (`water.vert:53`). Calculei o Q efetivo por onda: **1,01 / 0,78 / 0,69 / 0,56 / 0,46 / 0,42**. Ou seja, o Q real vai de ≈ 1,0 a 0,42, e a primeira onda está no limite superior do intervalo [0, 1] que o artigo declara. A garantia de que não há laços é outra: Σ Q_i·ω_i·A_i = média dos `STEEP` ≈ 0,45 < 1. Correção sugerida no artigo: definir a nitidez bruta s_i e escrever Q_i = s_i / (ω_i A_i m), citando a condição Σ Q_i ω_i A_i < 1.
2. **Projeção diferente no benchmark.** O programa usa near/far = 0,1/2000 (`camera.py:130`, é o que a Tabela 2 informa), mas `bench.py:210,373` e `tests/_base.py` usam **0,05/3000**. O artigo diz que o benchmark reutiliza a lógica da cena, o que vale, mas não que a projeção é outra. O efeito no tempo de quadro e no culling é provavelmente desprezível, mas deve ser igualado (constante única) ou citado.
3. **Distância usada na seleção ≠ distância usada no morph.** A seleção usa distância horizontal (`lod.py`), e o vertex shader do morph usa distância 3D até o vértice (`terrain.vert:58`, inclui a altura da câmera). O artigo descreve os dois trechos separadamente, sem notar a diferença. Consequência: com a câmera alta (vista aérea), um bloco escolhido pelo critério horizontal pode já estar com morph = 1, isto é, desenhado com a geometria do bloco-pai; gasta-se triângulos sem ganho visual. Não gera fendas (morph = 1 coincide com o vizinho mais grosso), então é ineficiência, não bug. Vale uma frase em limitações ou unificar o critério.
4. **A água é custo fixo e maior que o terreno.** `water.py` gera uma grade de 256×256 vértices (**130 050 triângulos**, constantes em todos os modos) numa área de **450 u.m.** contra 300 do terreno. O artigo diz que os triângulos "incluem a água", mas não que ela vale ~0,13 M em todas as colunas (≈ 30% da carga do CDLOD, 1,5% a 2048²) nem que o plano é maior que o terreno. Em triângulos só de terreno, o CDLOD desenha ≈ 0,30 M e o eixo x da Figura 3 deslocaria ≈ 0,13 M. A conclusão não muda; vale uma frase.
5. **Sentido da onda.** O artigo usa `k·x₀ − ωt` (Eqs. 8–10), enquanto o shader usa `+ φ·t` (`water.vert:55`), isto é, as ondas viajam em direção oposta à D. É só convenção, mas o texto e o código divergem.
6. **Limiar do filtro de spikes.** `dem._remover_spikes` tem padrão de 80 m, mas é chamada com **60 m** (`dem.py:136`). O artigo não informa o limiar; deve citar 60 m. O padrão de 80 m é código morto e confunde.
7. **Escala da cor submersa.** O escurecimento com a profundidade satura em 10 u.m. (`terrain.frag:58`), o que equivale a ≈ 280 m reais (u.m./m ≈ 0,036), e não em metros. O artigo diz só "escurece com a profundidade"; é informativo, sem erro.
8. **Ano de Strugar nos comentários.** `lod.py:5` e `terrain.vert:12` ainda dizem "Strugar, 2010", enquanto o artigo e o CLAUDE.md corrigiram para **2009** (DOI). Comentário apenas, mas é inconsistência em material que será lido na apresentação.

## 3. Lacuna de verificação

O artigo cita a versão `3f30ace` e os CSVs vêm dela. O código da branch atual (simplificado) passa nos 51 testes, mas **não repeti o benchmark**; portanto, não há evidência de que os números se reproduzam no código que está na `main`/branch atual. O README já avisa; para fechar a lacuna, basta rodar `python src/bench.py --saida bench/v3` na branch atual e comparar com `bench/v2` via `src/resumo_bench.py`.

## 4. Nota

| Critério | Nota |
|---|---|
| Fidelidade do artigo ao código (valores, equações, parâmetros) | 9/10 — nenhuma afirmação numérica errada; erros só na descrição de Q e em omissões |
| Coerência interna do código (constantes, comentários) | 8/10 — projeção do benchmark, limiar morto, ano dos comentários |
| Rastreabilidade (testes, CSVs, scripts) | 9/10 |

## 5. Correções sugeridas (todas pequenas)

1. Artigo: reescrever a definição de Q (item 1), citar o limiar de 60 m (item 6), a água fixa de 0,13 M (item 4) e a diferença de projeção (item 2).
2. Código: constante única de near/far (item 2); remover o padrão de 80 m em `_remover_spikes` (item 6); trocar "2010" por "2009" nos comentários (item 8).
3. Opcional: usar a mesma distância na seleção e no morph (item 3), com teste de imagem, e rodar o benchmark na branch atual (seção 3).

## 6. Status das correções (aplicadas)

| Item | Correção | Onde |
|---|---|---|
| 1. Q das ondas | Artigo define `s_i` (bruto) e `Q_i = s_i/(k_i A_i m)` (1,01 a 0,42), com `ΣQ_i k_i A_i ≈ 0,45 < 1`; código comenta o mesmo | `artigo_final_v5_abnt.tex` (§3.5, Tabela 2), `water.vert` |
| 2. Projeção | Constantes únicas `FOV_GRAUS`, `PLANO_PERTO`, `PLANO_LONGE` em `camera.py`, usadas pelo programa, benchmark e testes | `camera.py`, `bench.py`, `tests/_base.py` |
| 3. Distância do morph | Shader usa a distância horizontal, a mesma métrica da seleção (e uma amostragem de textura a menos) | `terrain.vert`, artigo §3.2.3 |
| 4. Água | Artigo informa o plano fixo de 130 050 triângulos e 450 u.m. de lado | nota da Tabela 4 |
| 5. Sentido da onda | Shader passa a usar `k·x − ωt`, igual às Eqs. 8–10 | `water.vert` |
| 6. Spikes | Padrão de `_remover_spikes` = 60 m (valor realmente usado); artigo cita o limiar | `dem.py`, artigo §3.1.1 |
| 7. Escala da cor submersa | Mantida (informativo) | — |
| 8. Ano de Strugar | 2010 → 2009 nos comentários | `lod.py`, `terrain.vert` |
| Lacuna: benchmark no código atual | Reexecutado: `bench/v3/` (3 execuções + memória). Tabela 4, Figura 3 e todos os números do artigo, README e CLAUDE.md passaram a vir dessa série | `bench/v3/`, `src/figura_artigo.py` |

Resultado da reexecução (código atual): ponto de virada ≈ 5 M de triângulos (4,4–5,6 M) sem culling e ≈ 3 M (2,0–3,5 M) com culling; culling −22% (1,12 → 0,88 ms); memória a 2048²: 19 MB × 153 MB. A série anterior (`3f30ace`, outra sessão) deu 3,4–4,3 M; a diferença está declarada como limitação do artigo.

Verificação: 51 testes passando (inclui imagem idêntica com e sem culling); artigo compila em 8 páginas.
