---
description: Audit a completed PostgreSQL evaluation run before plotting.
agent: thesis-viz
---

Audit a completed dashboard evaluation run. `$ARGUMENTS` is optional: it may be a
run ID, a readable dataset/theme description, or `latest`.

Communicate in English unless the user explicitly requests another language.
Keep Portuguese figure labels separate from user-facing language.

Treat PostgreSQL as the source of truth. Discover saved runs from the database
using the existing `--list-runs` command or dashboard run listing, and inspect
the selected run and its result payloads read-only. Do not use legacy result
files under `resultados/` as run data, and do not launch an evaluation.

If the user supplied no target, use OpenCode's interactive question tool to
offer completed runs with readable date, dataset/theme, status, and query/result
counts where available. Wait for the user's menu selection, even if there is
only one suitable run. `latest` explicitly selects the newest completed run.
Do not silently choose a target or make the user look up an ID. If a supplied
description resolves ambiguously, use the interactive menu to clarify.

Write or update `<repo-root>/docs/viz/data_audit.md` in English, identifying the exact run ID and
protocol. Include:

1. Available result schema: metrics, ranking methods, seed methods, themes,
   query formulations, presets/quorums, retrieval stages, timing and diagnostic
   fields, and completeness/missingness.
2. Useful descriptive statistics (count, mean, SD, min, max, and skewness where
   meaningful) at the correct analysis unit. Distinguish query observations,
   configurations, and themes; do not count repeated rows as independent
   observations.
3. Parameters that actually vary in this run. Explicitly note when there is no
   alpha/RRF sweep, iteration trace, or graph-topology export.
4. Main observed trade-offs and the specific figure encodings they support.
   Report paired comparisons only for matched observations and characterize
   uncertainty over a small number of themes as descriptive, not inferential.

Do not write or change the plotting pipeline in this step. Use a temporary
diagnostic script under `/tmp/opencode/` if needed; keep all database operations
read-only and do not include credentials in the report.
