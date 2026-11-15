# Como o projeto está sendo feito — relato do desenvolvimento

Diferente de [metodologia_atual.md](metodologia_atual.md) (o *retrato* atual,
com valores exatos) e de [APRESENTACAO.md](APRESENTACAO.md) (o guia
conceitual), este documento conta **a história de como chegamos até aqui**:
em que ordem as coisas foram construídas, as decisões tomadas em cada etapa
e por quê. Serve de base para a seção de Metodologia/Desenvolvimento do
relatório e do artigo.

---

## Fase 1 — Fundamentação (revisão bibliográfica)

Levantamento dos artigos do Eixo 6 (Tanner, Migdal & Jones — clipmap esférico; Welch
— simulação de oceano) e de 4 complementares (Strugar/CDLOD; Fournier &
Reeves/ondas de Gerstner; Brown et al./erosão costeira via DEM; um estudo de
geovisualização de subida do mar em Vancouver). Definição do cenário próprio
(o enunciado proíbe reproduzir o cenário original dos artigos): **Baixada
Santista**, por ter ao mesmo tempo relevo forte (Serra do Mar — bom para
testar LOD) e uma costa real onde inundação faz sentido.

*Pendente:* o relatório escrito desta fase; confirmação com o professor de
que as 4 referências complementares podem ser citadas.

## Fase 2 — Arquitetura da engine (do zero, incremental)

O desenvolvedor nunca tinha usado Python nem OpenGL. Em vez de entregar o
motor pronto, construímos em degraus, cada um rodando e sendo entendido
antes do próximo:

1. **Janela vazia** (`exemplos/janela.py`) — GLFW cria janela + contexto
   OpenGL; ModernGL embrulha o contexto; um *render loop* mínimo.
2. **Triângulo colorido** (`exemplos/triangulo.py`) — introduz VBO, VAO,
   vertex/fragment shader, e a interpolação automática (rasterização).
3. **Terreno + câmera livre** — heightmap procedural (ruído Simplex, *fBm*)
   vira malha; câmera com yaw/pitch e matrizes view/projection.

## Fase 3 — Algoritmo core (nesta ordem, cada entrega testada antes da próxima)

A fase mais longa. Feita em incrementos pequenos, cada um validado com
**render headless real** (`moderngl.create_standalone_context()` + captura
de framebuffer) nesta própria máquina, que tem GPU NVIDIA — não só checagem
de sintaxe.

1. **Ondas de Gerstner + nível do mar ajustável** — primeiro incremento,
   porque dava o "gancho" visual do tema (água + inundação) rápido. Plano de
   água (`water.py`) + shader com 4 ondas somadas (depois ampliado para 6).
   Terreno ganhou o realce da faixa submersa.
2. **CDLOD parte 2a — quadtree + seleção por distância** — heightmap virou
   textura (R32F) amostrada no vertex shader; malha unitária reusável por
   bloco; `lod.py` monta a quadtree e escolhe blocos por distância a cada
   frame. Entregue **com as *cracks* propositalmente visíveis**, pra depois
   mostrar o problema que o morphing resolve.
3. **DEM real da Baixada Santista** — troca do terreno procedural pelo dado
   real. Decisão técnica no meio do caminho: `rasterio`/GDAL foi descartado
   (frágil de instalar no Windows fora do conda — o mesmo tipo de problema
   que já tínhamos visto com o NumPy travando por falta de compilador C);
   optamos por **AWS Terrain Tiles** (PNG *terrarium*, sem chave de API),
   com *despike* e reamostragem em `dem.py`.
4. **CDLOD parte 2b — morphing** — resolve as *cracks* da etapa 2, deslizando
   vértices entre níveis de detalhe. Verificado comparando renders com o
   morphing ligado/desligado (a diferença de frestas ficou visível na
   imagem, e depois medida no benchmark).
5. **Ajuste do exagero vertical e da paleta de cores** — o primeiro render
   do DEM saiu "liso" (sem montanha visível): a Baixada Santista tem razão
   relevo:largura de ~40:1, então sem exagero a Serra do Mar não aparece.
   Subimos de 2,5× para 6× e trocamos a paleta (era genérica com "neve" no
   topo, sem sentido pra uma serra tropical; virou restinga → Mata
   Atlântica → rocha exposta nas encostas íngremes).
6. **HUD (legenda de comandos + foto de referência)** — texto renderizado
   via Pillow como textura; foto real da Baía de Santos (Wikimedia Commons,
   CC BY 2.0, com crédito salvo em `data/referencia_santos_CREDITO.txt`).
   **Bug encontrado e corrigido nesse meio-tempo:** a HUD e o terreno
   disputavam a mesma unidade de textura da GPU — o terreno só ficava
   "chapado" a partir do 2º frame, então só apareceu num teste com o loop
   completo (cena → HUD → cena → HUD), não num frame isolado. Lição
   registrada no `CLAUDE.md`: sempre testar em múltiplos frames.

## Fase 4 — Avaliação experimental (em andamento)

1. **Refatoração para medir** — antes de medir, o desenho da cena foi
   extraído de `main.py` para uma classe (`scene.py`, `Cena`), pra que a
   janela interativa e o benchmark rodem **exatamente o mesmo código**.
2. **`bench.py`** — mede tempo de frame sem janela (contexto *standalone* +
   framebuffer), variando resolução do heightmap, LOD ligado/desligado, e
   morphing ligado/desligado, em 4 posições de câmera. Resultado: o "ponto
   de virada" em ~5 milhões de triângulos (RTX 3060) — abaixo disso a
   malha ingênua é mais rápida (o CDLOD tem overhead fixo de organizar os
   blocos); acima, o CDLOD compensa.
3. **Documentos de apoio** — depois de fechar o código, foram gerados
   [APRESENTACAO.md](APRESENTACAO.md) e [TEORIA_DE_PONTA_A_PONTA.md](TEORIA_DE_PONTA_A_PONTA.md)
   (guias de estudo) e [metodologia_atual.md](metodologia_atual.md) (parâmetros exatos, para
   alinhar com o material de outro integrante do grupo, que tinha um plano com parâmetros
   diferentes — reconciliado e registrado no `CLAUDE.md`).

*Pendente:* rodar o benchmark em outra GPU; escrever o artigo IEEE com estes resultados.

---

## Decisões técnicas que valem a pena explicar na banca

| Decisão | Alternativa considerada | Por que escolhemos o que escolhemos |
|---|---|---|
| DEM via AWS Terrain Tiles | `rasterio`/GDAL + OpenTopography | Sem chave de API, sem dependência C frágil no Windows; mesma linhagem de dados (SRTM+GEBCO) |
| Alcance do LOD proporcional ao tamanho do bloco | Tabela de raios fixos por nível (r₀, 2r₀, 4r₀...) | Mesma regra matemática (o tamanho do bloco já dobra a cada nível), mas se auto-ajusta a qualquer profundidade de árvore |
| Profundidade da quadtree = 5 | 6 ou mais | Com textura de 1024 px, o bloco-folha no nível 5 já tem resolução igual à da própria textura — ir além disso não mostra detalhe novo |
| Nitidez (Q) das ondas de Gerstner decrescente por onda | Q fixo para todas as ondas | Evita que as ondas de frequência mais alta se autointerceptem (formem laço) |
| Exagero vertical 6× | Sem exagero / exagero menor | Necessário para a Serra do Mar aparecer; é prática padrão em geovisualização e é **declarado** no artigo |
| Cenários de mar em 0/+0,5/+1/+2 m | 0/+1/+2/+5 m (dramático demais) | Alinhado ao objetivo científico declarado do projeto (faixas usuais de projeção de subida do mar) |

## Como cada entrega foi validada

Toda funcionalidade nova foi testada com **render headless real** nesta
máquina (que tem GPU NVIDIA) antes de ser considerada pronta — nunca só por
checagem de sintaxe. Quando fazia sentido, o teste comparava duas condições
(LOD on/off, morph on/off, exagero antes/depois) lado a lado numa imagem,
pra confirmar visualmente a diferença esperada.
