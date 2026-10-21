---
description: Render approved figure families for a user-selected sample of a saved run.
agent: thesis-viz
---

Render a user-approved subset of figures from one completed saved evaluation
run. Speak to the user in English throughout unless they explicitly request
another language. Figure labels should retain the project's Brazilian
Portuguese terminology.

## Select the run

`$ARGUMENTS` may identify a saved run ID or `latest`, and may specify desired
figure families or a proposed sample. If no run is identified, list completed
runs using the existing `--list-runs` interface or dashboard listing, then use
OpenCode's interactive question tool to offer run choices. Include readable
date, dataset/theme, status, and query/result counts where available. Wait for
the user's menu selection even if there is only one run. Never silently infer a
run from a review/audit or choose one automatically. `latest` explicitly opts
into the newest completed run.

## Confirm the render scope before doing work

Inspect the selected run read-only and determine which figure families and
existing generator filters are supported. Use `<repo-root>/docs/viz/data_audit.md`
or `<repo-root>/docs/viz/reviews/` only when the recorded run/job matches the
selected run. Then use OpenCode's interactive question tool to propose the
figure families and sample definition (for example themes, formulations,
presets, quorums, or evaluation IDs). State what is excluded and whether this
subset is exploratory or supports headline claims. Wait for explicit approval
or an adjusted selection before rendering. Every request for clarification or
approval must use the interactive question tool; do not replace it with a
plain-text question or printed list.

Prefer supported filters in `scripts/generate_evaluation_figures.py`; do not
invent random sampling or add sampling behavior without approval. If the
requested scope cannot be expressed by existing options, explain the blocker
and ask via the interactive menu whether to stop or route to `/viz-pipeline`.

## Render and report

After approval, invoke
`<repo-root>/scripts/generate_evaluation_figures.py` for the selected run with
the confirmed filters. The app's actual output root is
`<repo-root>/resultados/figuras/`; use a new unique directory such as
`<repo-root>/resultados/figuras/manual-<unique-id>/figures/` as `--output-dir`.
The generator creates a run-ID subdirectory beneath that output directory.
Never overwrite existing job artifacts, modify evaluation data, or launch an
evaluation. Inspect the generated figures and report in English the selected
run, exact filters/sample, output path, visual findings, and limitations. Do
not change generator code or tests in this command; ask via the interactive
menu before routing implementation work to `/viz-pipeline`.
