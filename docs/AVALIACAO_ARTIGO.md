> **Histórico:** avaliação feita antes das correções finais; os números e problemas aqui citados foram superados. Ver `docs/AVALIACAO_CODIGO_ARTIGO.md` (seção 6).

# Reavaliação das métricas a partir do artigo (v4, prévia em PDF)

Data: 2026-11-07. Base: `artigo_final_v4_previa.pdf` (8 páginas) conferido contra os CSVs de `bench/` e `bench/v2/` (3 execuções). Esta avaliação complementa `AVALIACAO_PROJETO.md`.

## 1. Os números do artigo batem com os dados?

Sim, todos os que conferi. Nenhum valor parece inventado ou copiado errado.

| Afirmação do artigo | Recalculado dos CSVs | Situação |
|---|---|---|
| Tabela 4: CDLOD 1,06–1,21 ms; sem LOD 0,17→2,05 ms (2048²) | `bench/resultados.csv` (execução original) idêntico | ✔ |
| ~0,43 M triângulos do CDLOD, 100–184 blocos | média das 4 câmeras = 430 082; blocos 100/124/178/184 | ✔ |
| Culling: 52–73 blocos | 52/57/70/73 | ✔ |
| Culling −22% (1,04→0,81 ms) | 1,03→0,81 ms (−21,5%) | ✔ |
| Por câmera: −33% rasante, −38% encosta, −7% horizonte, −1% aérea | −33 / −38 / −7 / −1 | ✔ |
| Ponto de virada (média), 3 execuções: 3,6–4,2 M | 3,58 / 4,14 / 4,19 M | ✔ |
| Ponto de virada (p95), 3 execuções: 3,4–4,3 M | 3,41 / 4,18 / 4,31 M | ✔ |
| Virada com culling ≈ 2,3 M (média e p95) | média 2,05–2,55 M; p95 1,93–2,75 M | ✔ (faixa mais larga que o texto sugere) |
| Memória 2048²: 153 × 19 MB (≈8×); RAM 276 × 139; pico 595 × 191; VRAM +159 × +28 | idênticos em `memoria.csv` | ✔ |
| Tabela 3 (área alagada) | somas e percentuais internamente coerentes (14,8 + 104,6 = 119,4; 119,4/1927 = 6,2% etc.) | ✔ |

## 2. Métricas que sustentam bem a tese

- **CDLOD tem custo ~constante**: 1,01–1,02 ms em todas as resoluções nas 3 execuções; variação entre execuções ≤ 0,01 ms. É o resultado mais forte do artigo.
- **Malha completa cresce com a geometria**: 1,92–1,94 ms a 2048² nas 3 execuções (variação de 0,02 ms). A reprodutibilidade da média é excelente.
- **Culling**: 0,78–0,80 ms nas 3 execuções, e o efeito depende da câmera como esperado fisicamente (ganha quando parte do terreno sai do campo de visão).
- **Memória isolada por processo**: a melhor decisão metodológica do trabalho (evita que a malha completa "contamine" a medição do CDLOD).
- **Honestidade das limitações**: a Seção 5 declara hardware único, interpolação linear entre dois pontos, ausência de IC e p95 instável.

## 3. Problemas encontrados (do mais ao menos grave)

1. **A conclusão "CDLOD torna-se indispensável" não é sustentada pelos próprios dados.** O ponto de virada mede onde o CDLOD fica *mais rápido*, não onde a malha completa *deixa de ser interativa*. A pior medição da malha completa (8,5 M triângulos) leva ~2 ms por quadro, ou seja, ~490 FPS e 8× abaixo do orçamento de 16,7 ms de 60 FPS. A hipótese do artigo ("acima de certa carga a malha completa deixa de ser interativa") foi, nos dados, **refutada** nesta GPU, e a Introdução, o resumo e a Conclusão dizem o contrário. Sugestão: reformular para "o CDLOD passa a ser mais eficiente (tempo e memória) a partir de ~4 M triângulos; a interatividade só seria comprometida em hardware menos capaz, hipótese não testada". O ganho real e bem comprovado é memória (8×), e o texto poderia dar mais peso a isso.
2. **O custo de ~1 ms do CDLOD é provavelmente limitado pela CPU** (percurso da quadtree em Python e até 185 draw calls), não pela GPU. O artigo menciona a sobrecarga fixa, mas não diz que o ponto de virada depende da CPU e do Python, de modo que o resultado não se transfere para uma implementação em C++/GPU-driven. Vale uma frase nas limitações.
3. **Mistura de séries nos números principais.** A Tabela 4 e a Figura 3 usam a execução original (virada p95 2,7 M), enquanto o texto e o resumo citam as 3 execuções (3,4–4,3 M). A própria execução original é a de cauda mais ruidosa. Recomendo que a Tabela 4 e a Figura 3 usem a média das 3 execuções v2 (o p95 da malha completa a 2048² é 1,98 ms, não 2,75), com barras de erro. O gráfico passaria a mostrar viradas ~4,0 M em ambos os critérios, mais simples de comunicar.
4. **Uma única "interpolação linear" entre 1024² e 1536²** define a virada, com apenas 5 pontos. Intervalos de confiança não resolvem isso; mais resoluções entre 1024 e 1536 (ex.: 1152, 1280, 1408) resolveriam, e custam uma rodada de benchmark.
5. **Resultados do culling e da memória só aparecem em texto.** Não há tabela ou figura para as duas contribuições centrais da v2. Se houver espaço (o artigo já está em 8 páginas), uma tabela curta substituiria parte do parágrafo.
6. **Tabela 3 (área alagada)** é demonstração, e o artigo diz isso. Duas ressalvas a mencionar: (a) a caixa de 0,40° × 0,55° não é quadrada (≈ 44 × 56 km) mas é mapeada num terreno quadrado, o que distorce a escala horizontal em ~20% (a "célula de 49 m" é a média); (b) o limiar de +10 m inclui 400 km² de células a 0 m tratadas como mar, o que já está declarado.
7. **Escopo do argumento mobile.** O resumo e a introdução motivam o trabalho com dispositivos móveis, mas nenhuma medição foi feita neles, e o código (Python + OpenGL 3.3 core) nem roda lá. A limitação 2 declara isso; talvez o resumo devesse ser mais cauteloso ("determinar a carga na GPU de desktop; extrapolação para móveis é trabalho futuro").
8. **Estilo/forma:** o rodapé "Fonte: Elaborado pelos autores" está em todos os elementos; a nota "código na versão 3f30ace" fica correta, mas a `main` atual tem código simplificado que não reproduz exatamente o benchmark (o README já avisa). Convém deixar essa diferença explícita no repositório.

## 4. Nota revisada

| Critério | Nota | Variação vs. avaliação anterior |
|---|---|---|
| Fidelidade dos números às fontes | 9,5/10 | novo, tudo confere |
| Rigor da metodologia de medição | 7,5/10 | subiu: execuções repetidas são muito estáveis na média (variação ≤ 0,02 ms) |
| Solidez das conclusões | 6/10 | **desce**: "indispensável" não é sustentado |
| Clareza e organização do artigo | 8/10 | estrutura completa, 8 páginas dentro do limite |
| Transparência de limitações | 9/10 | seção 5 muito honesta |

**Resumo:** a medição está correta e bem reproduzível; o que falta é alinhar a *narrativa* com o que os dados provam (eficiência e memória, não necessidade de interatividade) e alinhar tabela/figura com as 3 execuções.

## 5. Ações sugeridas, em ordem de custo-benefício

1. Reescrever a frase da hipótese/conclusão (item 1). Custo: minutos, ganho: grande.
2. Atualizar Tabela 4 e Figura 3 com a média das 3 execuções v2 (item 3). Custo: baixo, o dado já existe.
3. Adicionar uma frase sobre CPU-bound/Python (item 2) e sobre a distorção de aspecto (item 6a).
4. Rodar 3 resoluções intermediárias entre 1024 e 1536 (item 4), se houver tempo.
5. Cautela no resumo sobre móveis (item 7).
