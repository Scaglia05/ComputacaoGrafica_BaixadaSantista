# Ajustes para o artigo v5 (texto pronto para colar)

Todos os valores vêm de `python src/resumo_bench.py bench/v2/run1 bench/v2/run2 bench/v2/run3`.
A figura nova está em `custo_vs_carga_v5.png` (gerada por `src/figura_artigo.py`; média das 3 execuções, barras = ± 1 desvio entre execuções, com a curva do CDLOD + culling).

## 1. Tabela 4 (substitui a atual, que usa a execução original)

```latex
\begin{table}[htbp]
\caption{Tempo de quadro por resolução do \textit{heightmap} (média das três execuções)}
\label{tab:desempenho}
\centering
\small
\begin{tabular}{rrrrr}
\hline
Resolução & Triângulos sem LOD (M) & Sem LOD & CDLOD & CDLOD + descarte \\
 & & média / p95 (ms) & média / p95 (ms) & média / p95 (ms) \\
\hline
256  & 0,26 & 0,20 / 0,22 & 1,05 / 1,18 & 0,84 / 0,95 \\
512  & 0,65 & 0,52 / 0,55 & 1,07 / 1,20 & 0,85 / 0,98 \\
1024 & 2,23 & 0,79 / 0,87 & 1,02 / 1,10 & 0,80 / 0,89 \\
1536 & 4,85 & 1,13 / 1,18 & 1,01 / 1,06 & 0,78 / 0,84 \\
2048 & 8,52 & 1,93 / 1,98 & 1,02 / 1,07 & 0,79 / 0,83 \\
\hline
\end{tabular}
\par\small Fonte: Elaborado pelos autores (2026), com dados do teste de desempenho.
Os triângulos incluem a água. O CDLOD desenha cerca de 0,43 milhão de triângulos por quadro (0,26 milhão com descarte).
\end{table}
```

## 2. Hipótese (Introdução) — trocar a frase "acima de certa carga geométrica, a malha completa deixa de ser interativa"

> A hipótese é que, acima de certa carga geométrica, a malha completa passa a custar mais tempo e memória do que o CDLOD, que mantém custo aproximadamente constante.

Objetivo geral: trocar "determinar experimentalmente a partir de qual carga geométrica o LOD adaptativo se torna necessário" por "... se torna mais eficiente".

## 3. Resumo / Abstract — trocar a conclusão

> Os resultados indicam que o CDLOD passa a ser mais rápido do que a malha completa a partir de cerca de 4 milhões de triângulos (3,4 a 4,3 milhões, conforme o critério e a execução) e, com o descarte de blocos fora do campo de visão, a partir de cerca de 2,3 milhões. Nessa GPU, porém, a malha completa permaneceu interativa em todas as resoluções (cerca de 2 ms por quadro a 8,5 milhões de triângulos); o ganho mais robusto do CDLOD foi de memória, cerca de oito vezes menor. O descarte reduziu o tempo de quadro em 22\%. Conclui-se que o nível de detalhe adaptativo reduz o custo de tempo e de memória da visualização de inundação costeira; sua necessidade para manter a interatividade em dispositivos mais fracos permanece como hipótese não testada.

(Replicar a mesma ideia no *Abstract* em inglês: "more efficient", "the full mesh remained interactive on this GPU", "necessity on weaker devices is untested".)

## 4. Seção 4 — trocar o parágrafo do ponto de virada e a figura

Figura 3: usar `custo_vs_carga_v5.png`; legenda: "Tempo de quadro em função do número de triângulos da malha completa, média de três execuções (barras: ± 1 desvio entre execuções). As linhas pontilhadas marcam os cruzamentos estimados por interpolação linear."

Texto:

> Em cada execução, o ponto de virada fica entre as resoluções 1024 e 1536, isto é, entre 2,2 e 4,9 milhões de triângulos. Por interpolação linear, o CDLOD passa a ser mais rápido em 3,6 a 4,2 milhões de triângulos pela média e em 3,4 a 4,3 milhões pelo p95 (média das execuções: cerca de 4,0 e 3,9 milhões). Com o descarte por campo de visão, o cruzamento ocorre em 2,0 a 2,6 milhões (média) e 1,9 a 2,8 milhões (p95), cerca de 2,3 milhões. Abaixo desses valores, a malha completa é mais rápida, pois o CDLOD tem uma sobrecarga fixa, a de percorrer a \textit{quadtree} e emitir até 185 chamadas de desenho por quadro. Convém notar que o ponto de virada indica onde o CDLOD fica mais eficiente, e não onde a malha completa deixa de ser interativa: mesmo com 8,5 milhões de triângulos, a malha completa leva cerca de 2 ms por quadro, bem abaixo dos 16,7 ms necessários para 60 quadros por segundo.

## 5. Conclusão — trocar o 1.º e o 2.º parágrafos

> O principal resultado vem do teste de desempenho. Com o CDLOD, o tempo para desenhar um quadro da cena completa (terreno e água) fica próximo de 1 ms em todas as resoluções testadas, enquanto sem LOD esse tempo cresce com a malha. As curvas se cruzam em cerca de 4 milhões de triângulos (3,4 a 4,3 milhões, conforme o critério e a execução) e, com o descarte por campo de visão, em cerca de 2,3 milhões. O descarte reduziu o tempo de quadro em 22\%, e o CDLOD usou cerca de oito vezes menos memória de malha na resolução 2048. Entretanto, nessa GPU de computador de mesa, a malha completa permaneceu interativa em todas as resoluções; portanto, a hipótese inicial foi confirmada quanto à eficiência (tempo e memória), mas não quanto à perda de interatividade, que só poderia ocorrer em hardware menos capaz, hipótese não testada.

## 6. Limitações — acrescentar

> Sexto, o custo de cerca de 1 ms do CDLOD é provavelmente limitado pela CPU (percurso da \textit{quadtree} em Python e até 185 chamadas de desenho por quadro); em uma implementação em outra linguagem ou com seleção na GPU, o ponto de virada tende a se deslocar. Sétimo, a caixa geográfica (aproximadamente 44 × 56 km) é mapeada em um terreno quadrado, o que distorce a escala horizontal em cerca de 20\%; a célula de 49 m é a média dos dois lados.

E trocar na Limitação 5 "série principal" / "2,7 a 4,3 milhões" por "3,4 a 4,3 milhões".
Na Seção 4, remover a frase "o valor de 2,7 milhões da série principal reflete uma cauda de quadros lentos..." (a série principal agora é a média das três execuções).
