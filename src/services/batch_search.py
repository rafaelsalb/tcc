"""Request-local evaluation reuse; the interactive search contract is unchanged."""

from copy import deepcopy
from math import isclose
from time import perf_counter

from services.search_pipeline import (ENSEMBLE_COMPONENT_RANKINGS, ENSEMBLE_RANKINGS,
                                      RANKINGS as SEARCH_RANKINGS, SEARCH_VERSION,
                                      SEED_METHODS, run_pipeline, search_request)

RANKINGS = tuple(dict.fromkeys(("ppr", *SEARCH_RANKINGS)))


def _validate(body):
    if not isinstance(body, dict) or not isinstance(body.get("search"), dict):
        raise ValueError("search must be an object")
    if not isinstance(body["search"].get("query"), str) or not body["search"]["query"].strip():
        raise ValueError("query must be a non-empty string")
    configurations = body.get("configurations")
    if not isinstance(configurations, list) or not 1 <= len(configurations) <= 128:
        raise ValueError("configurations must contain between 1 and 128 entries")
    for entry in configurations:
        if not isinstance(entry, dict):
            raise ValueError("each configuration must be an object")
        stage, ranking, seed = (entry.get(k) for k in ("stage", "ranking", "seed_method"))
        if entry.get("mode") == "compare":
            valid = stage in ("lexical", "hybrid", "ppr", "fused") and ranking == stage
            valid = valid and (seed == "none" if stage in ("lexical", "hybrid") else seed in SEED_METHODS)
        else:
            valid = entry.get("mode") == "ranking" and stage == "ppr" and ranking in RANKINGS and seed in SEED_METHODS
        if not valid:
            raise ValueError("invalid stage/ranking/seed/mode configuration")
    if type(body.get("benchmark", False)) is not bool:
        raise ValueError("benchmark must be a boolean")
    return configurations


def _execute(searcher, ranker, params, configurations, reuse, progress_callback=None,
             progress_offset=0, progress_total=None, phase="optimized",
             include_completed_entries=False):
    started = perf_counter()
    retrieval = None
    retrieval_steps = {}
    outputs = {}
    entries = []
    retrieval_seconds = ranking_seconds = 0.0
    counts = {"retrieval_calls": 0, "ranking_calls": 0, "graph_builds": 0, "ppr_runs": 0}
    phases = {"graph_seconds": 0.0, "ppr_seconds": 0.0, "mmr_seconds": 0.0, "cross_encoder_seconds": 0.0}
    batch_ranker = ranker.for_batch() if reuse else None
    if progress_total is None:
        progress_total = len(configurations)

    def report_progress(**event):
        if progress_callback is not None:
            progress_callback({"phase": phase, **event})

    class CaptureSearcher:
        def search(self, **settings):
            self.retrieval = searcher.search(**settings)
            return deepcopy(self.retrieval)

    for configuration in configurations:
        if retrieval is None or not reuse:
            report_progress(completed=progress_offset, total=progress_total,
                            activity="retrieval", configuration=configuration)
            tick = perf_counter()
            # The standard validator and parameter handling are reused.  Bypass
            # Redis completely; only this request's intermediate inputs persist.
            capture = CaptureSearcher()
            search_request(capture, ranker, None, {
                **params, "stage": "hybrid", "ranking": "", "seed_method": "hits",
                "seed_methods": ",".join(SEED_METHODS), "bypass_cache": "true",
            })
            retrieval = capture.retrieval
            retrieval_steps = retrieval.get("timings", {})
            retrieval_seconds += perf_counter() - tick
            counts["retrieval_calls"] += 1
        stage = configuration["stage"]
        ranking = configuration["ranking"]
        seed = configuration["seed_method"]
        effective_ranking = ranking if configuration["mode"] == "ranking" and ranking != "ppr" else None
        effective_seed = seed if seed != "none" else "hits"
        # These rankings do not use graph seeds. Their rows remain distinct,
        # but the calculation is performed only once.
        key = (stage, effective_ranking, "none" if ranking in ("lexical", "vector", "hybrid", "hybrid_max", "rrf", "cross_encoder") else effective_seed,
               params.get("graph_alpha", 0.85), params.get("graph_hop_decay", 0.5), params.get("graph_mix", 0.3),
               tuple(params.get("ensemble_rankings", ENSEMBLE_RANKINGS)))
        reused = reuse and key in outputs
        if not reused:
            active_ranker = batch_ranker if reuse else ranker.for_batch()
            timing_before = dict(active_ranker.batch_timings)
            tick = perf_counter()
            response = run_pipeline(retrieval, active_ranker, stage, effective_seed,
                                    ranking=effective_ranking, query=params.get("query"),
                                    graph_alpha=params.get("graph_alpha", 0.85),
                                     graph_hop_decay=params.get("graph_hop_decay", 0.5),
                                     graph_mix=params.get("graph_mix", 0.3),
                                     query_seed_fallback=params.get("query_seed_fallback", "hits"),
                                     ensemble_rankings=params.get("ensemble_rankings", ENSEMBLE_RANKINGS))
            computation_seconds = perf_counter() - tick
            ranking_seconds += computation_seconds
            diagnostic_timings = response.get("diagnostics", {})
            phases["cross_encoder_seconds"] += diagnostic_timings.get("cross_encoder_seconds", 0.0)
            step_names = (
                "graph_seconds", "graph_article_fetch_seconds", "graph_entity_load_extract_seconds",
                "graph_assembly_seconds", "graph_pruning_seconds", "ppr_seconds", "mmr_seconds",
            )
            step_timings = {key: active_ranker.batch_timings.get(key, 0.0) - timing_before.get(key, 0.0)
                            for key in step_names}
            step_timings["ranking_seconds"] = computation_seconds
            step_timings["cross_encoder_seconds"] = diagnostic_timings.get("cross_encoder_seconds", 0.0)
            counts["ranking_calls"] += 1
            outputs[key] = {
                "ranked": response["ranked"], "retrieval_id": response.get("retrieval_id"),
                "diagnostics": response.get("diagnostics", {}),
                "computation_seconds": computation_seconds,
                "step_timings": step_timings,
            }
            if configuration["mode"] == "compare" and stage == "lexical":
                outputs[key]["retrieval_id"] = str(response.get("retrieval_id")) + ":lexical"
                outputs[key]["diagnostics"] = {
                    **outputs[key]["diagnostics"], "returned_articles": len(response["ranked"]),
                    "returned_chunks": retrieval.get("diagnostics", {}).get("lexical_returned_chunks"),
                }
            if not reuse:
                for name in ("graph_builds", "ppr_runs"):
                    counts[name] += active_ranker.batch_counts[name]
                for name, seconds in active_ranker.batch_timings.items():
                    phases[name] = phases.get(name, 0.0) + seconds
        entries.append({**configuration, **deepcopy(outputs[key]), "computation_reused": reused})
        completed_event = {
            "completed": progress_offset + len(entries), "total": progress_total,
            "activity": "ranking", "configuration": configuration,
        }
        if include_completed_entries:
            completed_event.update(
                entry=deepcopy(entries[-1]), retrieval_steps=deepcopy(retrieval_steps),
                retrieval_seconds=retrieval_seconds,
                group_elapsed_seconds=perf_counter() - started,
                retrieval_snapshot=deepcopy(retrieval),
            )
        report_progress(**completed_event)
    if reuse:
        for name in ("graph_builds", "ppr_runs"):
            counts[name] = batch_ranker.batch_counts[name]
        phases.update(batch_ranker.batch_timings)
    return entries, {
        "wall_seconds": perf_counter() - started,
        "retrieval_seconds": retrieval_seconds, "ranking_seconds": ranking_seconds,
        "retrieval_steps": retrieval_steps, "counts": counts, **phases,
    }, {key: retrieval.get("diagnostics", {}).get(key) for key in (
        "lexical_candidate_article_urls", "hybrid_eligible_article_urls")}


def _equivalent(left, right):
    """Check ordering and scores, not timings or stochastic graph annotations."""
    return len(left) == len(right) and all(
        len(a["ranked"]) == len(b["ranked"]) and all(
            x["article"] == y["article"] and isclose(float(x["score"]), float(y["score"]), rel_tol=1e-6, abs_tol=1e-8)
            for x, y in zip(a["ranked"], b["ranked"])
        ) for a, b in zip(left, right)
    )


def evaluate_request(searcher, ranker, body, progress_callback=None, include_completed_entries=False):
    configurations = _validate(body)
    progress_total = len(configurations) * (2 if body.get("benchmark", False) else 1)
    optimized, timings, membership = _execute(
        searcher, ranker, body["search"], configurations, reuse=True,
        progress_callback=progress_callback, progress_total=progress_total,
        phase="optimized", include_completed_entries=include_completed_entries,
    )
    report = {"search_version": SEARCH_VERSION, "evaluation_version": "reuse_v1",
              "cache_bypassed": True, "results": optimized, "pool_membership": membership,
              "performance": {"optimized": timings}}
    if body.get("benchmark", False):
        baseline, baseline_timings, _ = _execute(
            searcher, ranker, body["search"], configurations, reuse=False,
            progress_callback=progress_callback, progress_offset=len(configurations),
            progress_total=progress_total, phase="baseline",
            include_completed_entries=include_completed_entries,
        )
        report["performance"].update(
            baseline=baseline_timings,
            speedup=baseline_timings["wall_seconds"] / max(timings["wall_seconds"], 1e-9),
            equivalent=_equivalent(optimized, baseline),
            benchmark_order="optimized_then_independent_baseline",
            baseline_definition="one fresh retrieval and ranking per output row",
        )
    return report
