# Visual review — `ba43f1f92a4a428eaed9de3318ecdd4a`

- **Figure job:** `ba43f1f92a4a428eaed9de3318ecdd4a`
- **Saved run:** `0cca98bd889e49dd89b3993a6407bff5` (audit/run date 2026-10-18)
- **Bundle generated:** 2026-10-20 20:48 UTC
- **Context:** audited multi-theme G1 retrieval run. This bundle is filtered to 24 themes and 192 queries (4,416 analysis rows); the matching audit covers the larger run (26 themes/201 queries).
- **Review scope:** all 24 PNGs in this completed app-generated bundle; matching PDF/SVG exports are present. PNGs were the primary review view. No figures, data, manifests, or code were changed.

## Overall publication readiness

The set is visually consistent, retains the project's Portuguese terminology, and generally uses appropriate encodings. Paired differences have a zero reference, query distributions show observations and counts, and quality plots identify theme-bootstrap intervals as descriptive. The paired-panel labels, dense formulation heatmaps, and sparse seed plots are materially improved relative to earlier versions.

The bundle is **close to presentation-ready at full-width size but not uniformly ready for thesis column width**. The main remaining concerns are empty space in the composition summary when all counts are constant, long categorical labels in several heatmaps, runtime labels around a tight point cluster, scatter overplotting in graph diagnostics, and repeated denominator text in the theme-difficulty chart. Several plots will need a full-width preset or a compact companion table. All assessments below concern visual design, not correctness of data or calculations.

Severity: **High** blocks reliable reading; **Medium** materially reduces clarity or paper-size legibility; **Low** is a polish improvement.

## Figure findings

### `headline_summary.png`

- **Severity: Low.** The four-card hierarchy is clean, text is legible, and the time panel distinguishes ranking computation from total latency. Broad whitespace inside cards makes the graphic feel more like a dashboard tile than a compact paper figure.
- **Improvement:** Reduce card height or offer a compact summary preset; keep the selected-run and descriptive-uncertainty context.
- **Scope:** General layout refinement.

### `fig01_evaluation_composition.png`

- **Severity: Medium.** With uniform theme/formulation counts and a constant reference-set size, both panels collapse to centered text within large mostly empty plotting areas. The message is understandable, but the figure uses space inefficiently and resembles a failed/empty plot at paper scale.
- **Improvement:** For constant distributions, use a compact annotated summary/table and reduce the panel area; preserve the normal matrix/histogram path when values vary.
- **Scope:** General conditional-layout behavior triggered by uniform data shape.

### `fig02_retrieval_coverage_and_ceiling.png`

- **Severity: Low.** Boxplots plus jittered query points suit the distribution comparison, and per-formulation `n` labels and a shared 0–1 scale aid interpretation. Rotated category labels are somewhat small but readable in the full-width export.
- **Improvement:** Retain the point layer and counts; consider slightly larger tick text or wrapped labels in a column-width preset.
- **Scope:** General sizing issue, with eight categories and long Portuguese labels as the data-shape factor.

### `fig02_theme_formulation_values.png`

- **Severity: Medium.** The 24-by-8 heatmap is a suitable overview and the continuous color scale is clear. Long rotated formulation labels occupy a large bottom margin; exact values rely on color decoding.
- **Improvement:** Offer wrapped/shortened tick labels and a full-width preset; provide a numeric table companion when exact per-cell comparisons matter.
- **Scope:** General heatmap label/layout behavior; the matrix dimensions are specific to this sample.

### `fig03_ranking_quality_leaderboard.png`

- **Severity: Low.** The three aligned dot-and-interval panels have readable labels, a clear dashed-mean explanation, and theme-bootstrap context. Colors/markers are not explained by a separate legend, although each row is directly named.
- **Improvement:** Keep direct labels; add a concise marker/color key only if the method-family colors carry meaning beyond the row labels. Preserve the descriptive-interval note.
- **Scope:** General legend convention.

### `fig03_ranking_quality_full_appendix.png`

- **Severity: Medium.** The full configuration set is distinguished and the 0–1 scales avoid misleading truncation. At 23 rows, text and marks are small at column width; direct row labels are dense, and the dashed mean needs to remain explicitly explained.
- **Improvement:** Reserve for full-width appendix placement, increase row spacing where feasible, and retain the explicit reference-line note. Link to the exact-value table/CSV.
- **Scope:** General scaling with configuration count; the 23-row density is sample-specific.

### `fig04_method_by_formulation.png`

- **Severity: Medium.** Removing dense cell text avoids collisions. The three heatmaps are legible at full size and the distinct colorbar ranges are explicitly identified, but exact cell values are not printed and the tilted labels are small.
- **Improvement:** Retain annotation suppression for dense grids; pair the heatmap with a numeric table or enable values only when the rendered cell dimensions support them. Keep each metric's scale explicit.
- **Scope:** General density-aware heatmap behavior.

### `fig04_method_by_formulation_full_appendix.png`

- **Severity: Medium.** The complete 23-row view is coherent and has no colliding cell annotations. Its long configuration names and rotated formulation labels make it suitable only for a full-width appendix; the three independent scales require careful reading.
- **Improvement:** Use wrapped row labels or split into legible method-family panels; retain a table for exact comparisons and label each metric scale.
- **Scope:** General label/size behavior, amplified by the full configuration list.

### `fig05_paired_deltas_vs_cross_encoder.png`

- **Severity: Low.** The shared figure-level x-axis label resolves panel collisions. Zero references and paired intervals are clear; configurations are directly labelled. Method colors have no separate key, but row labels carry the identity.
- **Improvement:** Keep the shared label; ensure caption wording defines each delta as method minus baseline and intervals as descriptive.
- **Scope:** General paired-comparison caption convention.

### `fig05_paired_deltas_vs_hybrid_max.png`

- **Severity: Low.** The shared label and baseline-in-title hierarchy are clear. Full-width output is comfortable; the x-axis label may still be small in a narrow column.
- **Improvement:** Retain current layout and provide a full-width preset; use the same contrast definition/caption across all paired baselines.
- **Scope:** General export-size consideration.

### `fig05_paired_deltas_vs_rrf.png`

- **Severity: Low.** The three facets, zero lines, and shared difference explanation are visually consistent with the other paired plots. Some rows lie close to zero, so modest point/line weight is important at print size.
- **Improvement:** Preserve the shared axis and slightly strengthen point/error-bar weight in small-size exports if legibility testing warrants it.
- **Scope:** General small-format export tuning.

### `fig06_graph_seed_sensitivity_f1_20.png`

- **Severity: Medium.** The plot now states the paired reference explicitly and uses a compact row-oriented layout. Fifteen long configuration labels remain dense, and the title is nearly edge-to-edge.
- **Improvement:** Use a full-width preset or wrap configuration labels; allow a two-line title/subtitle rather than compressing the metric, contrast, sample, and interval note into one line.
- **Scope:** General title/label layout, with 15 configurations as the density trigger.

### `fig06_graph_seed_sensitivity_mrr_20.png`

- **Severity: Medium.** The zero line and interval bars are distinct, and the reference contrast is explicit. The same long labels and wide title reduce paper-size legibility.
- **Improvement:** Apply the same wrapping and title hierarchy as the F1@20 seed plot; retain markers/line weight for grayscale.
- **Scope:** General, shared across the seed-sensitivity family.

### `fig06_graph_seed_sensitivity_ndcg_20.png`

- **Severity: Medium.** The compact point-and-interval form works, but label and title density persists. Color/marker families are visible but not separately keyed; direct labels help identify each configuration.
- **Improvement:** Wrap long row labels and move sample/uncertainty details to a subtitle or caption; avoid adding a legend unless the marker/color coding is intended to encode a separate grouping.
- **Scope:** General, shared across the seed-sensitivity family.

### `fig08_retrieval_cutoff_profiles.png`

- **Severity: Medium.** The three metric facets use appropriate cutoffs, distinct markers/line styles, and theme-level uncertainty. The muted gray series remain close and their translucent bands overlap, so visual separation is weaker in grayscale/small exports.
- **Improvement:** Strengthen line/marker contrast or use distinct dash patterns consistently; keep uncertainty fills light and the legend compact.
- **Scope:** General multi-series styling; close series make the limitation especially visible here.

### `fig09_map_ndcg_cutoff_profiles.png`

- **Severity: Medium.** Three baseline curves and error bars are readable, but several intervals overlap at the same cutoffs and cross/converge, making exact distinctions difficult. The legend and 24-theme context are clear.
- **Improvement:** Keep point estimates primary, slightly reduce cap/line weight where intervals overlap, and avoid implying separation from visually overlapping intervals.
- **Scope:** General interval-overlap styling.

### `supp_graph_map_ndcg_cutoff_profiles.png`

- **Severity: Medium.** The graph-method curves use clear marker/line distinctions and a readable legend. Vertical intervals at only three cutoffs overlap substantially, especially at the first cutoff; legend text is long.
- **Improvement:** Retain marker shapes, reduce interval cap clutter, and consider splitting MAP/NDCG legends or abbreviating labels in the supplementary layout.
- **Scope:** General for sparse-cutoff, multi-series interval plots.

### `supp_graph_method_cutoff_profiles.png`

- **Severity: Low.** The metric facets, method key, and cutoff points are distinguishable. Confidence ribbons are lighter than earlier versions but still blend where several graph methods overlap.
- **Improvement:** Preserve the series-count-aware opacity and use the ranking line styles/markers in grayscale exports; consider interval bars if more graph configurations are included.
- **Scope:** General uncertainty-band styling; overlap increases with series count.

### `fig10_low_score_cdf.png`

- **Severity: Low.** The empirical step curves are a good fit for lower-tail comparison. Threshold lines now have direct labels, the axes are explicit, and the legend distinguishes the selected methods.
- **Improvement:** Keep the threshold labels; check that the vertical annotations remain readable when reduced to column width.
- **Scope:** General size validation.

### `fig11_theme_heterogeneity.png`

- **Severity: Medium.** The theme-by-configuration heatmap is coherent and includes per-theme sample counts. Long rotated configuration labels consume a large bottom margin and may be too small at column width; cell values are encoded only by color.
- **Improvement:** Use a full-width preset or small multiples with wrapped labels; preserve the color scale and provide exact values in the table/CSV.
- **Scope:** General heatmap label layout; configuration count and name length drive the severity.

### `fig12_runtime_quality.png`

- **Severity: Medium.** The log runtime axis is labelled in seconds, category legend is clear, and the Pareto frontier is identified. Text annotations and leader lines cluster around the group of fast, high-quality points, making those labels compete for space.
- **Improvement:** Use label repulsion or label fewer points with a stated selection rule; retain unlabelled points and provide their names/values in a companion table.
- **Scope:** General point-label collision handling; the tight cluster is sample-specific.

### `fig13_graph_diagnostics.png`

- **Severity: Medium.** The count heatmap now explicitly states that blank cells are zero and annotates frequencies. The left scatter still contains visible overlap at repeated integer coordinates, obscuring multiplicity; the F1 colorbar is clear.
- **Improvement:** Use count-sized/transparent points or a frequency-aware strip treatment while preserving integer count positions; keep the zero-cell note.
- **Scope:** General handling of discrete-count scatter overplotting.

### `fig14_ranking_overlap.png`

- **Severity: Medium.** The square overlap heatmap is appropriate, with a clear 0–1 Jaccard scale and readable labels at full size. Long rotated configuration names and whitespace around the matrix make it difficult to use at column width.
- **Improvement:** Offer a full-width layout, wrap/shorten labels, or order/group configurations by method family; maintain the numeric colorbar.
- **Scope:** General heatmap label/size behavior, amplified by long configuration names.

### `fig15_theme_difficulty.png`

- **Severity: Medium.** The sorted horizontal bars suit the prevalence comparison and the percentage axis is explicit. Every bar repeats the same eligible-article denominator in its text annotation, producing a visually noisy column of labels; several long theme names also constrain compact sizing.
- **Improvement:** Put the common denominator once in the subtitle/caption, annotate bars with numerator or percentage only, and preserve exact counts in the CSV/table.
- **Scope:** General annotation design when a denominator is shared; long themes are a data-shape factor.

## Overall recommendation

Retain the current core chart families. Before thesis submission, prioritize a compact constant-data treatment for `fig01`, label handling for the runtime scatter and long heatmaps, a less repetitive annotation strategy for `fig15`, and print-size validation of the cutoff uncertainty plots. Use full-width layouts for the dense configuration/theme views. The remaining items are reusable layout/annotation improvements; no run-specific output tuning is recommended.
