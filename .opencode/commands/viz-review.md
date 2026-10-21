---
description: Critique a generated figure set against academic visualization standards and write a findings report.
agent: thesis-viz
---

Review the visual design and execution of an existing app-generated figure set.
Communicate in English throughout unless the user explicitly requests another
language. Portuguese figure labels are intentional and do not change the chat or
report language.

## Select a figure set

`$ARGUMENTS` may be a figure-job ID, `latest`, or a local path. Resolve relative
paths from the repository root. The app's `FigureJobManager` output root is
`<repo-root>/resultados/figuras/`; each job has `<job-id>/figures/` and
`<job-id>/figures.zip`.

Build candidates from run audits, not from every directory in the output root.
Read `<repo-root>/docs/viz/data_audit.md` and any run-specific audit records in
`<repo-root>/docs/viz/audits/`. Match audited run IDs to completed figure jobs
using per-run manifests. A candidate must have a matching audit, its archive,
and rendered outputs. Exclude unaudited jobs. Order by audit/run timestamp,
newest first, using job `generated_at` to break ties.

If no target is supplied, use OpenCode's interactive question menu to offer only
those audited, completed figure sets. Include job ID, audit/run date, generated
time, and dataset/theme context; wait for selection even if there is one choice.
`latest` explicitly selects the newest eligible set. Verify supplied IDs/paths
against the same eligibility rules; if ineligible or ambiguous, explain briefly
and use the menu to offer eligible choices. Do not use a menu for per-figure
decisions: the review should run through the full set without pausing for
approval after each figure.

## Critique the visualization

Inspect every figure in the selected set visually, using PNGs as the primary
view and checking PDF/SVG, manifest, or CSV only as needed to understand intended
visual encoding. Treat the underlying data and calculations as correct. Do not
spend review time auditing statistical correctness or reanalyzing results; flag
a data concern only if an evident visual issue makes interpretation impossible.

Assess each figure against academic-paper standards, including:

- whether the chart type and encoding suit the comparison or relationship;
- visual glitches, clipping, overlap, alignment, whitespace, and export quality;
- legibility at likely paper size, typography, line/marker weight, and hierarchy;
- color contrast, color-vision accessibility, grayscale distinction, and
  consistency across the figure set;
- axes, scales, ticks, units, labels, legends, annotations, and captions;
- whether uncertainty and sample counts are presented clearly when present;
- whether the design is concise, interpretable, and publication-ready.

Focus on visualization fundamentals, not whether a particular result is
desirable. Do not ask the user what to do after each figure. Present a concise
overall summary in English after the full review.

## Export findings

Write an English report to
`<repo-root>/docs/viz/reviews/<figure-job-id>.md` (create the directory if
needed). For each finding, include the figure/file reference, observed visual
problem, severity, concrete improvement, and whether it appears to be a general
pipeline issue or a one-off rendering/data-shape issue. Prioritize actionable
changes to the shared visualization pipeline; do not propose special cases for
the reviewed run. Include a short overall publication-readiness assessment.

This command is diagnostic only: do not edit code, tests, manifests, or figures;
do not rerender and never start or modify an evaluation. Summarize the report
path and highest-priority findings in English. `/viz-pipeline` is the separate
step for analyzing the report and implementing reusable pipeline improvements.
