# Simplificação do código — o que mudou

Os arquivos desta pasta substituem os de mesmo nome em `src\`. Nada foi mudado em
`dem.py`, `water.py`, `area_alagada.py`, `shaders\` e `tests\`.

**Para aplicar:** faça uma cópia de segurança de `src\` (ou use `git`), copie estes 7
arquivos para dentro de `src\` e rode `python -m unittest discover -s tests -v`.

## O que mudou, por arquivo

| Arquivo | Mudança | Por quê |
|---|---|---|
| `main.py` | O laço principal ficou menor. As teclas de liga/desliga viraram a classe `Interruptor`; o detector de "acabou de apertar" virou `Tecla`; o movimento virou uma tabela (`MOVIMENTOS`); o estado virou a classe `Estado`; a abertura da janela virou `criar_janela_e_contexto()`. | Antes eram um dicionário com 20 chaves (`"l_antes"`, `"k_antes"`...) e seis `if` repetidos para andar. |
| `scene.py` | O construtor foi dividido em passos com nome (`_carregar_alturas`, `_criar_textura_altura`, `_criar_terreno`, `_criar_quadtree`, `_criar_agua`). `desenhar` foi dividido em `_desenhar_terreno` e `_desenhar_agua`. | Uma função de 100 linhas virou várias de ~20. |
| `lod.py` | Removidas `_numerar` (fazia o trabalho de `listar_nos`) e a variável `tem_filhos`; `select` ficou com 6 linhas. | Menos funções para ler, mesma regra. |
| `heightmap.py` | Removida a função `build_mesh`, que ninguém chamava (a malha agora vem de `build_unit_grid` e o shader desloca a altura). Docstring e autoteste atualizados. | Código morto confunde quem está aprendendo. |
| `hud.py` | O posicionamento dos painéis (`posicionar`) tinha 5 blocos quase iguais; virou uma regra única "vertical-horizontal". `atualizar_viewport` virou um laço. | Menos repetição. |
| `bench.py` | O desenho de um quadro (usado no aquecimento, na medição e na memória) virou `_desenhar_quadro`; a linha do CSV virou `_linha_resultado`; os 5 gráficos repetiam o mesmo código e agora usam `_plotar_series`, `_plotar_barras_por_camera` e `_salvar_figura`. | Menos copiar-e-colar. |
| `camera.py` | `process_keyboard` usa um dicionário de direções em vez de seis `elif`. | Mais curto e mais claro. |

## Como a equivalência foi conferida (no ambiente de testes, sem GPU)

Com renderização por software (llvmpipe), antes e depois:
- os **38 testes** do projeto passam;
- **82 imagens renderizadas** (4 câmeras × 5 modos × 2 níveis de mar × terreno real e procedural) têm o mesmo hash;
- o **`main.py` rodando de verdade** (janela, teclado e mouse simulados, 44 quadros com W, D, Shift, Espaço, 3, 7, L, K, M, C, H, P, Z, I, `,`, R) gera quadros idênticos e a mesma saída no terminal;
- os **10 gráficos** do benchmark saem byte a byte iguais;
- as colunas que não dependem de tempo do `resultados.csv` e da medição de memória são iguais.

**Não foi possível testar:** a medição de tempo em GPU real (as imagens e as contagens não mudam,
mas o desempenho exato só se confirma rodando `python src/bench.py` na sua máquina) e a interação
com o mouse e o teclado reais. Rodem o `main.py` uma vez antes de apagar a cópia de segurança.

## Observação sobre o tamanho

A contagem de linhas não caiu em todos os arquivos (`main.py` e `scene.py` têm mais linhas, porque
cada passo agora é uma função com nome e comentário). O objetivo foi facilitar a leitura, e não
encurtar o arquivo.

## Atualização: `dem.py`
`_mosaico_metros` fazia três coisas juntas; agora usa `_juntar_tiles` (colar os tiles) e
`_rgb_para_metros` (decodificar a elevação). As duas chamadas iguais a `_remover_spikes` viraram um laço de 2 passadas.
Conferido: o heightmap (512²) é idêntico bit a bit ao original, a saída de `area_alagada.py` é idêntica e os testes passam.

`water.py`, `area_alagada.py` e os 4 shaders (`.vert`/`.frag`) foram lidos e **não alterados**: têm 40–90 linhas,
já são comentados passo a passo e uma mudança neles só traria risco (os shaders não dá para validar em GPU real aqui).
