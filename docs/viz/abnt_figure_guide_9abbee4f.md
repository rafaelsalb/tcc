# ABNT figure captions and review — evaluation bundle `9abbee4f58fd4b14a9cb8f0e3d3032e8`

This guide covers every visual in:

`resultados/figuras/9abbee4f58fd4b14a9cb8f0e3d3032e8/figures/0cca98bd889e49dd89b3993a6407bff5/`

It contains 22 numbered plots and the unnumbered `headline_summary.png` (23 visuals total). The captions below are Portuguese-ready text for the thesis; editorial observations are retained in English for continuity with the visual review.

## Applying ABNT in the thesis

Use ABNT NBR 14724:2025 and the institution's current manual. In the thesis, cite each illustration in the prose and place it close to the relevant discussion. Put the designating term and sequential number followed by the title above the visual; put the source below it. Align identification, title, source, legends, and notes with the illustration's margins. The standard governs presentation, not the choice of chart type or palette.

The numbers below are **provisional sequence numbers for this bundle**, not a requirement to use every visual. Renumber the visuals that actually appear in the thesis according to their order of first mention. If both highlighted and full-appendix variants are used, give each a distinct number (or use the institution's appendix numbering). The generated file sequence has gaps; do not preserve those gaps in the thesis numbering unless the figures preceding them are also included.

Suggested source line for these author-generated plots:

> Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

Replace this with the exact dataset/source wording required by the institution. Add a list of illustrations if required by the institution's template. The captions and notes here are external to the image; the current plot titles can remain as panel/graphic headings, but avoid duplicating a long title in both the image and the thesis caption.

## Figure-by-figure captions, notes, and observations

### Provisional Gráfico 1 — `fig01_evaluation_composition`

**Caption:** Gráfico 1 – Composição do conjunto de avaliação por tema e formulação de consulta

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada combinação de tema e formulação contém uma consulta; o conjunto reúne 25 temas, oito formulações e 200 consultas. Cada consulta possui 20 artigos de referência.

**Existing observation:** The original 25 × 8 heatmap showed only the value 1 in every cell, so its color encoding conveyed no variation. The companion panel reports 200 queries and 20 reference articles per query.

**Action taken:** Replaced the uniform all-ones heatmap with a direct text summary of the design. This is more informative and avoids a redundant color scale. The exported PNG, PDF, and SVG for this plot have been regenerated in the supplied bundle.

### Provisional Gráfico 2 — `fig02_retrieval_coverage_and_ceiling`

**Caption:** Gráfico 2 – Distribuição da cobertura das referências e do teto de F1@20 por formulação

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** A caixa representa a distribuição por formulação; os pontos são observações individuais e `n` indica o número de consultas. A cobertura mede a fração de artigos de referência recuperada. O teto de F1@20 considera somente os artigos presentes no conjunto recuperado; não representa o desempenho de um método de ordenação.

**Existing observation:** Boxplots and overlaid points make category distributions clearer, with `n` shown for each formulation. The one-query-per-formulation case should be read as a single observation, not as a stable distribution.

**ABNT/layout action:** Keep at full text width so the rotated formulation labels and sample counts remain legible. Define F1 in the methodology or note if it has not already been introduced.

### Provisional Gráfico 3 — `fig02_theme_formulation_values`

**Caption:** Gráfico 3 – Cobertura das referências e teto de F1@20 por tema e formulação

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada célula apresenta o valor observado para a combinação tema–formulação. Células sem preenchimento indicam ausência de consulta para aquela combinação, não valor zero. As escalas de cor variam de 0 a 1.

**Existing observation:** This heatmap provides the theme-to-value mapping that the category distributions alone cannot show. The 25 theme rows and long formulation labels make it a full-width or appendix figure.

**ABNT/layout action:** Place at full width or on a landscape appendix page; do not shrink it to column width.

### Provisional Gráfico 4 — `fig03_ranking_quality_leaderboard`

**Caption:** Gráfico 4 – Desempenho das configurações de recuperação selecionadas

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Os pontos representam a média macro por tema; as barras representam intervalos bootstrap descritivos de 95% reamostrados por tema. A linha tracejada indica a média das configurações exibidas. A escala horizontal é ampliada e começa em zero.

**Existing observation:** The three aligned metric panels are suitable for comparison and the rows are directly labeled. The dashed reference and theme-bootstrap intervals need to be explained for readers unfamiliar with them.

**ABNT/layout action:** Use full text width. Preserve the explicit interval and reference-line note in the caption or an adjacent legend note.

### Provisional Gráfico 5 — `fig03_ranking_quality_full_appendix`

**Caption:** Gráfico 5 – Desempenho de todas as configurações de recuperação

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Apresenta a lista completa de configurações em escala de 0 a 1; intervalos são bootstrap descritivos de 95% por tema. A linha tracejada indica a média das configurações exibidas.

**Existing observation:** This is the complete appendix view, unlike the highlighted main-text view. The full list makes it substantially denser.

**ABNT/layout action:** Keep in the appendix and use a landscape/full-page layout. If labels are too small after placement, split the metrics or provide the complete table as an appendix table instead of shrinking the graphic. If both versions are included, number and cite them separately.

### Provisional Gráfico 6 — `fig04_method_by_formulation`

**Caption:** Gráfico 6 – Desempenho das configurações selecionadas por formulação de consulta

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada célula mostra a média macro por tema para F1@20, MRR@20 ou NDCG@20, conforme o painel. Cada barra de cores possui escala própria, indicada ao lado do respectivo painel; as escalas não devem ser comparadas entre métricas.

**Existing observation:** The three heatmaps support comparison by formulation, but long configuration/formulation labels and cell annotations can become crowded when reduced to page width.

**ABNT/layout action:** Use full-width placement. Keep any cell values and color bars legible; if they are not legible at final print size, remove annotations from the main figure and cite the accompanying data table.

### Provisional Gráfico 7 — `fig04_method_by_formulation_full_appendix`

**Caption:** Gráfico 7 – Desempenho de todas as configurações por formulação de consulta

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Apresenta a lista completa de configurações. Os valores são médias macro por tema; cada métrica possui sua própria escala de cor.

**Existing observation:** The full configuration list is useful for auditability but dense; long row labels and three metric panels challenge legibility at ordinary page width.

**ABNT/layout action:** Use a landscape appendix page or split by metric/configuration family. Do not scale this wide graphic down to portrait text width. Assign a distinct number if both Gráficos 6 and 7 are used.

### Provisional Gráfico 8 — `fig05_paired_deltas_vs_cross_encoder`

**Caption:** Gráfico 8 – Diferenças pareadas das configurações em relação ao Cross-encoder

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Valores positivos favorecem a configuração comparada; valores negativos favorecem o Cross-encoder. A linha vertical em zero representa ausência de diferença. Barras indicam intervalos bootstrap descritivos de 95% por tema. A tabela complementar contém as contagens de vitórias, empates e derrotas.

**Existing observation:** The common x-axis explanation and zero reference are appropriate. Three metric panels and long configuration names need a full-width placement.

**ABNT/layout action:** Use full text width. Do not rely on the CSV for interpreting the plotted estimate or interval; retain the definitions in the caption.

### Provisional Gráfico 9 — `fig05_paired_deltas_vs_hybrid_max`

**Caption:** Gráfico 9 – Diferenças pareadas das configurações em relação ao método híbrido por máximo por artigo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Valores positivos favorecem a configuração comparada; valores negativos favorecem o método de referência. Zero indica ausência de diferença. Barras indicam intervalos bootstrap descritivos de 95% por tema.

**Existing observation:** This uses the same paired-difference design as the other Gráfico 5 exports; consistency in caption and placement is important.

**ABNT/layout action:** Use full text width and keep the reference method explicit in the title/caption.

### Provisional Gráfico 10 — `fig05_paired_deltas_vs_rrf`

**Caption:** Gráfico 10 – Diferenças pareadas das configurações em relação à fusão RRF

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Valores positivos favorecem a configuração comparada; valores negativos favorecem a fusão RRF. Zero indica ausência de diferença. Barras indicam intervalos bootstrap descritivos de 95% por tema.

**Existing observation:** This repeats the paired-difference design and should be presented consistently with Gráficos 8 and 9.

**ABNT/layout action:** Use full text width. State the reference method explicitly and do not interpret an interval crossing zero as proof of equivalence.

### Provisional Gráfico 11 — `fig06_graph_seed_sensitivity_f1_20`

**Caption:** Gráfico 11 – Sensibilidade de F1@20 ao método de inicialização do grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada ponto e intervalo representa a diferença pareada em relação à inicialização por entidades da consulta. Valores positivos indicam aumento de F1@20; negativos indicam redução. Intervalos bootstrap de 95% são descritivos e reamostrados por tema.

**Existing observation:** The paired reference is central to interpretation; it should be stated in the caption, not left implicit in the plot title.

**ABNT/layout action:** Use full text width or appendix placement so configuration labels and intervals remain legible.

### Provisional Gráfico 12 — `fig06_graph_seed_sensitivity_mrr_20`

**Caption:** Gráfico 12 – Sensibilidade de MRR@20 ao método de inicialização do grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada ponto e intervalo representa a diferença pareada em relação à inicialização por entidades da consulta. Valores positivos indicam aumento de MRR@20; negativos indicam redução. Intervalos bootstrap de 95% são descritivos e reamostrados por tema.

**Existing observation:** As with F1@20, make the paired baseline explicit and preserve the zero reference.

**ABNT/layout action:** Use the same sizing and caption structure as Gráficos 11 and 13.

### Provisional Gráfico 13 — `fig06_graph_seed_sensitivity_ndcg_20`

**Caption:** Gráfico 13 – Sensibilidade de NDCG@20 ao método de inicialização do grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada ponto e intervalo representa a diferença pareada em relação à inicialização por entidades da consulta. Valores positivos indicam aumento de NDCG@20; negativos indicam redução. Intervalos bootstrap de 95% são descritivos e reamostrados por tema.

**Existing observation:** Keep the seed reference and zero line clear; the three metric-specific seed plots should be sized consistently.

**ABNT/layout action:** Use the same sizing and caption structure as Gráficos 11 and 12.

### Provisional Gráfico 14 — `fig08_retrieval_cutoff_profiles`

**Caption:** Gráfico 14 – Precisão, revocação e F1 por tamanho do conjunto de resultados

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** O eixo horizontal representa o corte `k`. Linhas representam configurações; áreas sombreadas representam intervalos bootstrap descritivos de 95% reamostrados por tema. As escalas verticais são ampliadas, mas incluem zero.

**Existing observation:** Three metric panels, distinct method colors/markers, and uncertainty bands are present. The bands still overlap, so the legend and interval explanation matter.

**ABNT/layout action:** Use full width. Preserve method/marker distinctions and ensure the legend remains readable at the final size.

### Provisional Gráfico 15 — `fig09_map_ndcg_cutoff_profiles`

**Caption:** Gráfico 15 – MAP e NDCG por corte para as configurações de referência

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Os intervalos bootstrap descritivos de 95% são mostrados em `k=5` e `k=20`; as linhas mostram as estimativas nos cortes avaliados. A escala vertical é ampliada e começa em zero.

**Existing observation:** The baseline-only split reduces clutter compared with combining all methods. Intervals are shown only at selected cutoffs, which should be explicit to avoid implying uncertainty coverage at every point.

**ABNT/layout action:** Keep full width and retain the selected-cutoff interval note.

### Provisional Gráfico 16 — `supp_graph_map_ndcg_cutoff_profiles`

**Caption:** Gráfico 16 – MAP e NDCG por corte para métodos de grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Inclui métodos de grafo com inicialização por entidades da consulta. Intervalos bootstrap descritivos de 95% são mostrados em `k=5` e `k=20`; a escala vertical é ampliada e começa em zero.

**Existing observation:** The graph-method split is more readable than pooling all series; several methods remain close, making the marker and line-style key important.

**ABNT/layout action:** Place in the appendix at full width and keep its scale identical to Gráfico 15 for direct comparison.

### Provisional Gráfico 17 — `supp_graph_method_cutoff_profiles`

**Caption:** Gráfico 17 – Precisão, revocação e F1 por corte para métodos de grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Inclui métodos de grafo com inicialização por entidades da consulta. Áreas sombreadas representam intervalos bootstrap descritivos de 95% reamostrados por tema; escalas verticais são ampliadas e incluem zero.

**Existing observation:** This supplementary profile is useful, but multiple uncertainty bands can overlap and the legend may become small at page scale.

**ABNT/layout action:** Use a landscape/full-width appendix placement. If the legend is not legible, split the metrics or move a concise method key to the caption/note.

### Provisional Gráfico 18 — `fig10_low_score_cdf`

**Caption:** Gráfico 18 – Proporção acumulada de consultas com F1@20 até determinado valor

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada curva mostra a proporção de consultas com F1@20 igual ou inferior ao valor do eixo horizontal. As linhas verticais pontilhadas marcam os limiares 0,10 e 0,20; a linha tracejada em zero marca F1@20 igual a zero. São exibidas as configurações em destaque.

**Existing observation:** The empirical step curves and distinct line styles are suitable. The threshold lines were not initially labeled.

**Action taken:** Added direct labels for the 0.10 and 0.20 reference thresholds in the regenerated PNG, PDF, and SVG.

### Provisional Gráfico 19 — `fig11_theme_heterogeneity`

**Caption:** Gráfico 19 – Heterogeneidade de F1@20 entre temas e configurações

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada célula representa a média de F1@20 da configuração no tema indicado. `n` indica o número de consultas do tema. A escala de cor vai de zero ao limite indicado na barra.

**Existing observation:** The heatmap supports theme-level comparison and shows per-theme sample counts, but long configuration labels and lack of cell values make exact reading difficult.

**ABNT/layout action:** Place at full width or landscape in the appendix. Use the companion CSV/table for exact comparisons rather than shrinking the plot or adding colliding cell annotations.

### Provisional Gráfico 20 — `fig12_runtime_quality`

**Caption:** Gráfico 20 – Relação entre tempo de computação do ranking e F1@20

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** O eixo horizontal representa o tempo de computação do ranking, em segundos, em escala logarítmica; não representa a latência total da consulta. A fronteira de Pareto reúne configurações para as quais não há outra simultaneamente mais rápida e com F1@20 igual ou maior. Pontos dominados têm pelo menos uma alternativa melhor nesse sentido. O F1@20 é a média macro por tema.

**Existing observation:** The plot highlights the Pareto frontier and labels its configurations. The terms “dominada” and “não dominada” are optimization terminology and should be defined for readers unfamiliar with it.

**ABNT/layout action:** Keep the definitions in the note/caption. Review label collisions after placing at final page size; if needed, label the frontier points with numbers and list names in a small adjacent table.

### Provisional Gráfico 21 — `fig13_graph_diagnostics`

**Caption:** Gráfico 21 – Relação entre entidades extraídas da consulta e entidades correspondidas no grafo

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada ponto representa uma observação método–consulta; a cor indica F1@20. O painel da direita conta observações por combinação de entidades extraídas e correspondidas; células vazias representam frequência zero. A figura informa quantas observações não possuem contagem de correspondência.

**Existing observation:** The scatter and frequency heatmap now use the same x/y meanings. Discrete values overlap in the scatter, so point multiplicity is not fully visible; missing matched-count observations are reported.

**ABNT/layout action:** Keep the unit of observation and missing-count caveat in the note. Preserve full width so both color bars and integer axes remain legible.

### Provisional Gráfico 22 — `fig14_ranking_overlap`

**Caption:** Gráfico 22 – Sobreposição média dos artigos nos 20 primeiros resultados

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** Cada célula apresenta a média, entre consultas pareadas, do índice de Jaccard entre dois métodos: 1 indica o mesmo conjunto de artigos e 0 indica nenhum artigo em comum. A ordem dos artigos não é considerada. A diagonal compara cada configuração consigo mesma e, por isso, vale 1.

**Existing observation:** The previous title “diversidade das listas ranqueadas” did not clearly state what was compared. The measure compares membership in the top 20, not the rank order.

**Action taken:** Renamed the chart title, axis labels, and color-bar label in the regenerated PNG, PDF, and SVG. Use full width/landscape because configuration labels are long.

### Provisional Figura 23 — `headline_summary`

**Caption:** Figura 23 – Síntese descritiva dos resultados da rodada de avaliação

**Source:** Fonte: Elaborado pelo autor (2026), com base nos dados da avaliação experimental.

**Note:** As médias atribuem o mesmo peso a cada tema. O tempo informado corresponde ao cálculo do ranking, não à latência total. O método gráfico destacado é o de maior média neste conjunto e não implica superioridade estatística.

**Existing observation:** The four-card summary is visually clean and combines study design, retrieval ceiling, ranking result, and ranking computation time. The cost card is less informative when time data are unavailable.

**ABNT/layout action:** Treat this as an illustration/infographic if included in the thesis and provide the formal caption/source outside the image. If a metric is unavailable, prefer a compact unavailable-data message over a mostly empty card.

## Non-normative visual/layout checks before submission

- Check each selected illustration at the actual page size, not only at screen zoom. Long labels in Gráficos 3, 5–7, 11–13, 16–17, 19, 21, and 22 may require full-width, landscape, or appendix placement.
- Do not rely on color alone to identify methods; retain markers, line styles, direct labels, or a clear legend.
- Keep the notes needed to interpret zero lines, thresholds, axes, color scales, confidence intervals, and specialized terms with the relevant chart.
- Prefer vector PDF when embedding preserves text and line quality. Confirm the institution's accepted export/embedding format and typographic requirements.
- ABNT does not mandate changing a plot into a different chart type. The design changes made for this bundle address the uninformative uniform composition heatmap, the unlabeled fig10 thresholds, and fig14's unclear terminology; other suggested size/layout adjustments depend on final thesis placement.
