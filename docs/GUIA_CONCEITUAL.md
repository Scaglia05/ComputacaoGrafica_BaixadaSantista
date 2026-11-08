# Guia conceitual — como o nosso projeto funciona (sem código)

Objetivo: entender e saber explicar **o que fazemos, como e por quê**, com palavras simples.

---

## 1. O projeto em 30 segundos

Pegamos **dados reais de altura** da Baixada Santista (Santos, São Vicente, Guarujá), montamos o
relevo em **3D** no computador e colocamos por cima uma **água animada** cujo nível o usuário pode
subir (+0,5 m, +1 m, +2 m). O terreno que fica abaixo da água muda de cor, e assim se **vê o que
alagaria**.

O desafio técnico: o terreno é enorme e o computador não consegue desenhar tudo com detalhe ao
mesmo tempo. Resolvemos desenhando **muito detalhe perto da câmera e pouco detalhe longe**, e
medimos até que ponto isso compensa.

---

## 2. Glossário (cada termo em uma ou duas frases)

| Termo | Em português simples |
|---|---|
| **Triângulo / malha** | Todo objeto 3D é feito de triângulos pequenos colados. Um terreno é uma "rede" de triângulos. Quanto mais triângulos, mais detalhe, mais trabalho para o computador. |
| **GPU** | A placa de vídeo. É ela que desenha milhões de triângulos por segundo. |
| **Shader** | Um mini-programa que roda **dentro da placa de vídeo**. Dizemos a ela como posicionar e pintar. |
| **Vertex shader** | O shader que trata **cada ponto (vértice)** dos triângulos: decide onde ele fica no espaço. É onde a onda se move e onde o terreno ganha altura. |
| **Fragment shader** | O shader que trata **cada pixel**: decide a cor final. É onde entram luz, cor do terreno e cor da água. |
| **Heightmap (mapa de altura)** | Uma imagem em que cada ponto guarda **uma altura em vez de uma cor**. Como um mapa topográfico em forma de tabela de números. |
| **1024 × 1024** | O tamanho dessa tabela: 1024 colunas por 1024 linhas = **cerca de 1 milhão de pontos de altura**. |
| **DEM** | "Modelo Digital de Elevação": o dado real de altura do planeta, medido por satélite (NASA). É a fonte do nosso heightmap. |
| **LOD (nível de detalhe)** | Ideia de usar **muitos triângulos perto e poucos longe**, porque de longe o olho não percebe a diferença. É como o Google Earth: de perto vê a rua, de longe só o bairro. |
| **Quadtree** | Uma forma de organizar o terreno: pega um quadrado, divide em **4 quadrados menores**, e repete isso várias vezes. Gera blocos grandes e blocos pequenos. |
| **CDLOD** | O nome do **método de LOD que usamos** (Strugar, 2009): usa a quadtree e escolhe, a cada quadro, **quais blocos desenhar conforme a distância da câmera**. "Contínuo" = a troca de detalhe é suave. |
| **Morphing** | A troca suave entre um bloco detalhado e um mais simples. Sem ela o terreno **"pula"** e aparecem **frestas** entre blocos vizinhos. Com ela, os pontos **deslizam** devagar até a nova posição. |
| **Frustum culling** | O "frustum" é a **pirâmide do campo de visão** da câmera. Culling = **não desenhar o que está fora dela** (atrás de você, ou dos lados). Economiza trabalho sem mudar a imagem. |
| **Draw call** | Cada vez que o programa manda a placa desenhar algo. Muitas chamadas pequenas deixam o programa lento (principalmente em Python). |
| **FPS** | Quadros por segundo; o que o usuário sente como fluidez. |

---

## 3. Como o mapa (terreno) é criado

Pense em montar uma **maquete**:

1. **Dado real.** Baixamos de um serviço aberto da Amazon (AWS Terrain Tiles) imagens que cobrem a
   região. Nessas imagens **a cor codifica a altura** (um número escondido na cor). Origem: satélite
   da NASA (SRTM) para a terra e GEBCO para o fundo do mar.
2. **Tradução.** O Python lê essas imagens e converte cada cor de volta em **metros de altura**.
3. **Limpeza.** Alguns pontos vêm com erro (picos falsos). Removemos esses "espinhos" com um filtro
   de mediana, que troca cada ponto pela mediana dos vizinhos.
4. **Tamanho padrão.** Reduzimos tudo para a tabela de **1024 × 1024** alturas.
5. **Exagero vertical (6×).** A região é muito larga (~50 km) e o relevo é baixo (~1 km). Sem exagero,
   a Serra do Mar ficaria quase achatada. Esticamos a altura 6× e **declaramos isso no artigo**.
6. **Montagem do relevo.** Começamos com um **plano chato feito de triângulos** e, para cada ponto,
   **levantamos** a altura lida da tabela. O plano vira montanha, planície e litoral. (A técnica
   se chama *displacement mapping*; a placa de vídeo faz isso.)
7. **Pintura.** Cada pixel é colorido conforme a **altitude** (areia na beira do mar, mata, mata
   densa, rocha nos cumes) e a **inclinação** (parede íngreme mostra rocha).
8. **Luz.** Calculamos a direção "para onde cada pedacinho está virado" (a **normal**) e comparamos com
   a direção do sol. Quem está virado para o sol fica claro; quem está de costas, escuro. É isso que
   dá **sensação de relevo**.
9. **Névoa.** Longe da câmera, as cores se misturam com a cor do céu, o que dá **noção de distância**.

**Por que não desenhar tudo com detalhe máximo?** O terreno completo teria milhões de triângulos e
travaria um computador comum. Daí vem o LOD (próxima seção).

---

## 4. Como o LOD funciona (a ideia por trás da quadtree)

- Imagine o terreno como **um quadrado grande**.
- Se a câmera está **longe** dele, desenhamos esse quadrado grande e simples.
- Se a câmera está **perto**, trocamos por **4 quadrados menores**, cada um com o mesmo número de
  triângulos, ou seja, **mais detalhe por metro**. Repetimos isso até 5 níveis.
- Resultado: blocos pequenos perto de você, blocos enormes no horizonte. A quantidade total de
  triângulos fica **quase constante**, não importa o tamanho do mapa.
- O **morphing** esconde a troca de nível. O **frustum culling** descarta os blocos que a câmera
  nem enxerga.

**Por que quadtree e não "clipmap" (o método dos artigos obrigatórios)?** O clipmap esférico foi
feito para planetas inteiros. O nosso recorte é local (~50 km) e praticamente plano, então a quadtree
é mais simples e atende. Mantemos a **ideia** do clipmap (detalhe concentrado perto de quem olha).

---

## 5. Como a onda funciona

### 5.1 A ideia física
Numa onda real, uma gota de água **não vai só para cima e para baixo**: ela **anda em círculo** (ou
numa elipse). Quando passa a crista, ela sobe **e é empurrada para a frente**; quando passa o vale,
ela desce **e volta um pouco**.

Esse é o **modelo de Gerstner** (Fournier & Reeves, 1986). O efeito prático:
- numa onda só de "sobe e desce" (seno), a crista é redonda e o mar parece de borracha;
- no modelo de Gerstner, a **crista fica mais pontuda e o vale mais largo**, como o mar de verdade.

Resumindo o que você disse, corrigido: **cada ponto da água é movido em círculo, empurrado para a
frente e para cima, e isso forma a onda.**

### 5.2 Como viramos isso em imagem
1. A água é só **um plano liso de triângulos** (uma "folha" azul), criado uma vez.
2. A cada quadro, o **vertex shader** (na placa de vídeo) pega **cada ponto desse plano** e aplica o
   movimento circular: um pouco **para a frente** e um pouco **para cima/baixo**, dependendo de
   *onde* o ponto está e de *quanto tempo* passou. O tempo é o que faz a onda **andar**.
3. Em vez de uma onda só, **somamos 6 ondas** de tamanhos e direções diferentes (uma grande e
   lenta, outras pequenas e rápidas). Assim o mar não parece repetitivo.
4. O próprio cálculo informa **para onde cada pedaço da superfície está inclinado**, e isso permite
   iluminar a água de forma realista.

### 5.3 De onde vem a cor da água (atenção a este ponto)
A cor **da onda em si não vem da profundidade**. Ela vem de três efeitos de luz:
- **Luz do sol:** onde a superfície está virada para o sol fica azul mais claro; no resto, azul escuro.
- **Reflexo do céu (efeito Fresnel):** olhando a água **de raspão**, ela vira espelho e reflete o céu;
  olhando **de cima**, você vê através dela. É um fenômeno real.
- **Brilho do sol (especular):** o pontinho branco de reflexo do sol nas cristas.

E ela é **80% opaca (20% transparente)**, por isso dá para enxergar o terreno por baixo.

### 5.4 Onde entra a profundidade
A profundidade entra **no terreno, não na água**. Cada ponto do terreno é comparado com o
**nível do mar atual**: se está **abaixo**, ele recebe um tom **verde-escuro**, e **quanto mais fundo,
mais escuro**. É isso que mostra visualmente **o que está alagado**.

### 5.5 O nível do mar é só um número
Subir o mar de 0 para +1 m é **somar um valor** na altura do plano de água e na linha de corte da
coloração do terreno. Por isso dá para alterar em tempo real, sem recalcular nada pesado.

---

## 6. Quem faz o quê (as bibliotecas)

> "Modelado em **Python**, desenhado na placa de vídeo via **OpenGL**, usando as bibliotecas…"

| Biblioteca | Em uma frase |
|---|---|
| **Python 3.11** | Linguagem em que o programa é escrito e que organiza tudo. |
| **ModernGL** | Ponte entre o Python e a placa de vídeo (OpenGL): envia os dados, carrega os shaders e manda desenhar. |
| **GLFW** | Cria a **janela** e lê **teclado e mouse**. |
| **PyGLM** | Faz as **contas de câmera e perspectiva** (matrizes): para onde a câmera olha e como o 3D vira 2D na tela. |
| **NumPy** | Guarda e calcula **grandes tabelas de números** (alturas, vértices) com rapidez; faz também a decisão do culling. |
| **Pillow** | Lê as **imagens do DEM** e **desenha os textos** da interface (a placa não escreve texto). |
| **opensimplex** | Gera **terreno inventado** (ruído) para testes, sem depender de internet. |
| **matplotlib** | Faz os **gráficos** do benchmark que vão no artigo. |
| **psutil** | Mede **memória RAM** usada. |

**Dados:** AWS Terrain Tiles (NASA SRTM + GEBCO), **sem precisar de chave de API**.

---

## 7. Como os artigos citados se relacionam com o nosso

| Artigo | Ideia dele | O que usamos |
|---|---|---|
| **Tanner, Migdal & Jones (1998)** — Clipmap | Guardar detalhe só perto do observador | A **ideia** de detalhe perto/pouco longe |
| **Clasen & Hege (2006)** — clipmap esférico | Mesma ideia para planetas | Referência; **não** usamos esfera |
| **Strugar (2009)** — CDLOD | Quadtree + distância + morphing | **É o que implementamos** |
| **Fournier & Reeves (1986)** | Ondas de Gerstner | **A matemática da onda** |
| **Welch (2019)** | Oceano em tempo real na GPU | Mostra que **é viável em tempo real**; ele usa nível fixo, **nós deixamos o nível ajustável** |
| **Brown et al. (2006)** | Visualizar erosão costeira com DEM | **Motivação** e escolha do cenário |
| **DiPaola et al. (2023)** | Mapas 2D de subida do mar | **Motivação**; o deles é mapa 2D, o nosso é 3D com água animada |

**Nossa contribuição:** não inventamos técnica nova; **juntamos** terreno com LOD + água procedural
num cenário ambiental real, com **nível do mar ajustável**, e **medimos** quando o LOD passa a valer a pena.

---

## 8. O que medimos e o que isso significa

- Sem LOD, o custo cresce **proporcionalmente** ao tamanho do terreno.
- Com LOD, o custo fica **quase constante** (~1 ms por quadro).
- **Ponto de virada:** a partir de **~4 milhões de triângulos** (2,7 a 4,3 M conforme o critério) o
  LOD passa a ser mais rápido que desenhar tudo. Com culling cai para ~2,3 M.
- **Frustum culling:** reduz **22%** do tempo de quadro em média, sem mudar a imagem.
- **Memória:** a 2048², o LOD usa **19 MB** contra **153 MB** da malha completa.
- Testado em **uma** placa (RTX 3060). Em outras GPUs: **não medido** (trabalho futuro).

---

## 9. Limitações para falar com honestidade

1. Medimos em uma só placa de vídeo, com poucas repetições.
2. A altura do DEM (satélite) não tem precisão de centímetros; em cenários de +0,5 m a +2 m a área
   alagada é uma **demonstração visual, não uma previsão**.
3. As ondas são **visuais**: não interagem com a costa (sem quebra, sem espuma).
4. As ondas são grandes se comparadas com 0,5 a 2 m de mar; quem mostra o alagamento é a **cor do
   terreno submerso**, não a altura da onda.
5. O exagero vertical de 6× é declarado: o relevo parece mais íngreme do que é.
6. O recorte retangular da região é encaixado num mundo quadrado, com leve distorção de proporção.

---

## 10. Roteiro curto para explicar em voz alta

> "Pegamos dados reais de elevação do satélite da NASA e transformamos num mapa de alturas de
> 1024 por 1024 pontos. Esse mapa levanta um plano de triângulos e forma o relevo em 3D, pintado por
> altitude e inclinação. Como o terreno é grande demais para desenhar com detalhe máximo, usamos
> LOD: uma árvore que divide o terreno em blocos, com blocos pequenos perto da câmera e grandes
> longe, e um efeito de morphing para a troca ser suave. Por cima, uma água que se mexe com ondas
> de Gerstner: cada ponto da água se move em círculo, para frente e para cima, e somamos seis ondas
> para parecer natural. O nível do mar é só um número ajustável; o terreno abaixo dele escurece
> conforme a profundidade, e é isso que mostra o que alagaria. Por fim, medimos o desempenho e
> achamos que, a partir de cerca de 4 milhões de triângulos, o LOD compensa."
