---
description: Turn visual-review findings into reusable improvements to the shared figure-generation pipeline.
agent: thesis-viz
---

Analyze a completed visual-review report and improve the shared figure
generation pipeline where findings justify general changes. `$ARGUMENTS` may be
a figure-job ID, review-report path, or `latest`. Communicate in English unless
the user explicitly requests another language.

## Identify the review and evidence

If a report is specified, read it. Otherwise discover reports under
`<repo-root>/docs/viz/reviews/`, order them by the matching audit/run recency
(newest first), and use OpenCode's interactive question menu to ask which report
to act on. Include report/job ID and run context; wait for the user's selection
even if only one report exists. `latest` explicitly selects the newest eligible
report. Do not silently use `docs/viz/data_audit.md` as a substitute for a visual
review report.

Read the selected review report, its matching run audit, the relevant generator
code, app figure-job integration, and focused tests. Treat the review's selected
figure set as evidence for a possible defect, not as a specification to imitate
or optimize against. Verify each proposed fix against the shared pipeline and
identify which findings plausibly affect other runs.

## Implement general improvements only

Change the existing `scripts/generate_evaluation_figures.py` pipeline (and
reusable helpers it uses) only for issues that can be addressed generically.
Do not add conditions keyed to the reviewed run ID, dataset/theme, query,
observed values, or generated artifact. Do not tune data-dependent settings to
make the reviewed output look better at the expense of other valid runs. If a
finding is genuinely run-specific or evidence is insufficient to generalize,
document that conclusion instead of adding a special case.

Preserve the app invocation/output contract, run isolation, read-only database
behavior, complete-group defaults, manifests, and CSV outputs. Add focused tests
that exercise the reusable behavior, not snapshots tied to the reviewed result.
Use a distinct output directory for any rendering; never overwrite existing
artifacts or start/modify an evaluation. Run
`uv run pytest tests/test_generate_evaluation_figures.py`.

Summarize which findings were addressed, the generic behavior changed, tests and
validation performed, and which findings were intentionally left as
run-specific or unsupported. If implementation would require changing source
data, evaluation logic, or the scope of this command, stop and use OpenCode's
interactive question menu to ask before proceeding.
