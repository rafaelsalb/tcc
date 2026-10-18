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


def _execute(searcher, ranker, params, configurations, reuse):
    started = perf_counter()
    retrieval = None
    outputs = {}
    entries = []
    retrieval_seconds = ranking_seconds = 0.0
    counts = {"retrieval_calls": 0, "ranking_calls": 0, "graph_builds": 0, "ppr_runs": 0}
    phases = {"graph_seconds": 0.0, "ppr_seconds": 0.0, "mmr_seconds": 0.0, "cross_encoder_seconds": 0.0}
    batch_ranker = ranker.for_batch() if reuse else None
    class CaptureSearcher:
        def search(self, **settings):
            self.retrieval = searcher.search(**settings)
            return deepcopy(self.retrieval)

    for configuration in configurations:
        if retrieval is None or not reuse:
            tick = perf_counter()
            # The standard validator and parameter handling are reused.  Bypass
            # Redis completely; only this request's intermediate inputs persist.
            capture = CaptureSearcher()
            search_request(capture, ranker, None, {
                **params, "stage": "hybrid", "ranking": "", "seed_method": "hits",
                "seed_methods": ",".join(SEED_METHODS), "bypass_cache": "true",
            })
            retrieval = capture.retrieval
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
            tick = perf_counter()
            response = run_pipeline(retrieval, active_ranker, stage, effective_seed,
                                    ranking=effective_ranking, query=params.get("query"),
                                    graph_alpha=params.get("graph_alpha", 0.85),
                                     graph_hop_decay=params.get("graph_hop_decay", 0.5),
                                     graph_mix=params.get("graph_mix", 0.3),
                                     query_seed_fallback=params.get("query_seed_fallback", "hits"),
                                     ensemble_rankings=params.get("ensemble_rankings", ENSEMBLE_RANKINGS))
            ranking_seconds += perf_counter() - tick
            if ranking in ("cross_encoder", "graph_hits_cross_encoder"):
                phases["cross_encoder_seconds"] += perf_counter() - tick
            counts["ranking_calls"] += 1
            outputs[key] = {
                "ranked": response["ranked"], "retrieval_id": response.get("retrieval_id"),
                "diagnostics": response.get("diagnostics", {}),
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
                    phases[name] += seconds
        entries.append({**configuration, **deepcopy(outputs[key]), "computation_reused": reused})
    if reuse:
        for name in ("graph_builds", "ppr_runs"):
            counts[name] = batch_ranker.batch_counts[name]
        phases.update(batch_ranker.batch_timings)
    return entries, {
        "wall_seconds": perf_counter() - started,
        "retrieval_seconds": retrieval_seconds, "ranking_seconds": ranking_seconds,
        "counts": counts, **phases,
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


def evaluate_request(searcher, ranker, body):
    configurations = _validate(body)
    optimized, timings, membership = _execute(searcher, ranker, body["search"], configurations, reuse=True)
    report = {"search_version": SEARCH_VERSION, "evaluation_version": "reuse_v1",
              "cache_bypassed": True, "results": optimized, "pool_membership": membership,
              "performance": {"optimized": timings}}
    if body.get("benchmark", False):
        baseline, baseline_timings, _ = _execute(searcher, ranker, body["search"], configurations, reuse=False)
        report["performance"].update(
            baseline=baseline_timings,
            speedup=baseline_timings["wall_seconds"] / max(timings["wall_seconds"], 1e-9),
            equivalent=_equivalent(optimized, baseline),
            benchmark_order="optimized_then_independent_baseline",
            baseline_definition="one fresh retrieval and ranking per output row",
        )
    return report
