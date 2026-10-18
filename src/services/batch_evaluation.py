"""Run repeatable search evaluations from a validated JSON input file."""

import csv
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.models import G1Articles
from services.batch_checkpoint import (
    BatchStopped, ResultJournal, defer_stop_signals, durable_flush,
    output_lock, stop_on_termination, sync_directory,
)
from services.search_pipeline import (ENSEMBLE_COMPONENT_RANKINGS, ENSEMBLE_RANKINGS,
                                      QUERY_SEED_FALLBACKS, SEARCH_VERSION)
from services.batch_summary import LiveSummary, summary_paths

SCHEMA_VERSION = 1
BATCH_KS = (1, 3, 5, 10, 20)
API_TIMEOUT_SECONDS = 600
SEARCH_WINDOW = {
    "date_from": "2025-06-01",
    "date_to": "2026-06-30",
}
SHARED_SEARCH_SETTINGS = {
    "offset": 0,
}
QUORUM_VALUES = (0.3, 0.5, 0.7, 0.9)
SEED_METHODS = ("louvain", "hits", "ppr_top10", "query_entities")
RANKINGS = ("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr",
            "graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion",
            "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf")
SEARCH_PRESETS = {
    "rapido": {"limit": 1000, "top_k": 250},
    "balanceado": {"limit": 1000, "top_k": 500},
    "profundo": {"limit": 1000, "top_k": 1000},
}

DOCUMENT_KEYS = {"schema_version", "evaluations"}
EVALUATION_KEYS = {"id", "query", "relevant_urls"}
OPTIONAL_EVALUATION_KEYS = {"query_formulation"}


def validate_document(document: object) -> list[dict[str, object]]:
    """Validate the rigid JSON schema and return its evaluation entries."""
    if not isinstance(document, dict):
        raise ValueError("input must be a JSON object")
    if set(document) != DOCUMENT_KEYS:
        raise ValueError(
            "top-level keys must be exactly: schema_version, evaluations"
        )
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    evaluations = document["evaluations"]
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("evaluations must be a non-empty array")

    seen_ids: set[str] = set()
    for index, item in enumerate(evaluations):
        location = f"evaluations[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        if not EVALUATION_KEYS <= set(item) or set(item) - EVALUATION_KEYS - OPTIONAL_EVALUATION_KEYS:
            raise ValueError(
                f"{location} keys must be exactly: id, query, relevant_urls, with optional query_formulation"
            )
        if "query_formulation" in item and (
            not isinstance(item["query_formulation"], str) or not item["query_formulation"].strip()
        ):
            raise ValueError(f"{location}.query_formulation must be a non-empty string")

        for field in ("id", "query"):
            value = item[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{location}.{field} must be a non-empty string")
        evaluation_id = item["id"].strip()
        if evaluation_id in seen_ids:
            raise ValueError(f"duplicate evaluation id: {evaluation_id!r}")
        seen_ids.add(evaluation_id)

        urls = item["relevant_urls"]
        if not isinstance(urls, list) or not urls:
            raise ValueError(
                f"{location}.relevant_urls must be a non-empty array"
            )
        if any(not isinstance(url, str) or not url.strip() for url in urls):
            raise ValueError(f"{location}.relevant_urls must contain non-empty strings")
        if len(set(urls)) != len(urls):
            raise ValueError(f"{location}.relevant_urls must contain unique URLs")
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{location} contains an invalid absolute URL: {url!r}")

    # The frontend trims the search text before sending it; mirror that here.
    return [
        {**item, "id": item["id"].strip(), "query": item["query"].strip(),
         "query_formulation": item.get("query_formulation", "unspecified").strip()}
        for item in evaluations
    ]


def load_evaluation_file(path: str | Path) -> list[dict[str, object]]:
    """Read and validate a UTF-8 JSON evaluation file."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as input_file:
            document = json.load(input_file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read evaluation file {path}: {exc}") from exc
    return validate_document(document)


def output_paths(input_path: str | Path, output_path: str | Path | None) -> tuple[Path, Path]:
    input_path = Path(input_path)
    json_path = (
        Path(output_path)
        if output_path is not None
        else input_path.with_name(f"{input_path.stem}.results.json")
    )
    if json_path.suffix.lower() != ".json":
        raise ValueError("--output must have a .json extension")
    csv_path = json_path.with_suffix(".csv")
    if not json_path.parent.is_dir() or not csv_path.parent.is_dir():
        raise ValueError(f"output directory does not exist: {json_path.parent}")
    input_resolved = input_path.resolve()
    if input_resolved in {
        json_path.resolve(), csv_path.resolve(), json_path.with_suffix(".jsonl").resolve(),
        Path(str(json_path) + ".lock").resolve(),
        *(path.resolve() for path in summary_paths(json_path)),
    }:
        raise ValueError("output files must not overwrite the input file")
    return json_path, csv_path


def ensure_output_available(
    paths: tuple[Path, Path], overwrite: bool, resume: bool = False
) -> None:
    if resume and overwrite:
        raise ValueError("--resume and --overwrite are mutually exclusive")
    journal_path = paths[0].with_suffix(".jsonl")
    if resume:
        if not journal_path.is_file():
            raise ValueError(f"checkpoint not found: {journal_path}; old JSON-only batches cannot be resumed")
        return
    existing = [str(path) for path in (*paths, journal_path, *summary_paths(paths[0])) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"output already exists ({', '.join(existing)}); pass --resume to continue or --overwrite to replace it"
        )


def _validate_relevant_urls_exist(engine, evaluations: list[dict[str, object]]) -> None:
    urls = list(dict.fromkeys(
        url
        for item in evaluations
        for url in item["relevant_urls"]
    ))
    existing: set[str] = set()
    # Keep each IN query small enough for PostgreSQL's bind-parameter limits.
    with Session(engine) as session:
        for start in range(0, len(urls), 1000):
            batch = urls[start : start + 1000]
            existing.update(
                session.scalars(select(G1Articles.url).where(G1Articles.url.in_(batch)))
            )
    missing = [url for url in urls if url not in existing]
    if missing:
        raise ValueError(
            f"relevant_urls not found in g1_articles ({len(missing)} missing): "
            f"{missing[:5]}"
        )


def _normalize_api_base_url(api_base_url: str) -> str:
    api_base_url = api_base_url.strip().rstrip("/")
    parsed = urlsplit(api_base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("--api-url must be an HTTP(S) base URL without credentials, query, or fragment")
    return api_base_url


def _search_endpoint_url(
    api_base_url: str,
    query: str,
    preset: dict[str, int],
    seed_method: str,
    quorum: float,
    *, stage="ppr", result_unit="chunks", seed_methods=None, ranking=None,
    query_seed_fallback="hits", ensemble_rankings=ENSEMBLE_RANKINGS,
) -> str:
    params = {
        "query": query,
        **preset,
        **SHARED_SEARCH_SETTINGS,
        "quorum": quorum,
        **SEARCH_WINDOW,
        "seed_method": seed_method,
        "stage": stage, "result_unit": result_unit,
        "bypass_cache": "true",
        "query_seed_fallback": query_seed_fallback,
    }
    if ranking and ranking != "ppr":
        params["ranking"] = ranking
    if seed_methods:
        params["seed_methods"] = ",".join(seed_methods)
    if ranking == "ensemble_rrf":
        params["ensemble_rankings"] = ",".join(ensemble_rankings)
    return f"{api_base_url}/search?{urlencode(params)}"


def _response_from_api(
    api_base_url: str,
    query: str,
    preset: dict[str, int],
    seed_method: str,
    quorum: float,
    **options,
) -> dict:
    endpoint = _search_endpoint_url(api_base_url, query, preset, seed_method, quorum, **options)
    request = Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            message = error_payload.get("error", str(exc)) if isinstance(error_payload, dict) else str(exc)
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = str(exc)
        raise RuntimeError(f"search API returned HTTP {exc.code}: {message}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"could not reach search API at {api_base_url}; is it running? ({exc})"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("search API returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("search API response must be a JSON object")
    if payload.get("error"):
        raise RuntimeError(f"search API error: {payload['error']}")
    if payload.get("search_version") != SEARCH_VERSION:
        raise RuntimeError("search API version mismatch; restart the updated API and use a new output file")
    if payload.get("cache_bypassed") is not True:
        raise RuntimeError("search API did not confirm cache bypass; refusing to save potentially cached results")
    expected_ranking = options.get("ranking")
    if expected_ranking and payload.get("ranking") != expected_ranking:
        raise RuntimeError(
            f"search API returned ranking {payload.get('ranking')!r}; expected {expected_ranking!r}"
        )
    ranked = payload.get("ranked", [])
    if not isinstance(ranked, list):
        raise RuntimeError("search API response field 'ranked' must be an array")
    return payload


def _ranked_urls_from_api(api_base_url, query, preset, seed_method, quorum, **options):
    payload = _response_from_api(api_base_url, query, preset, seed_method, quorum, **options)
    ranked = payload.get("ranked", [])
    return [
        entry["article"]
        for entry in ranked
        if isinstance(entry, dict) and isinstance(entry.get("article"), str)
    ]


def _ranked_urls_from_api_compat(api_base_url, query, preset, seed_method, quorum, options):
    """Call adapters that support ranking options, with legacy-test compatibility."""
    try:
        return _ranked_urls_from_api(api_base_url, query, preset, seed_method, quorum, **options)
    except TypeError as exc:
        # Older injected test doubles accepted only the original five arguments.
        # Never hide real API errors: retry only for an unsupported keyword.
        if "unexpected keyword argument" not in str(exc):
            raise
        return _ranked_urls_from_api(api_base_url, query, preset, seed_method, quorum)


def _evaluation_from_api(api_base_url, item, task, configurations, benchmark=False, query_seed_fallback="hits",
                         ensemble_rankings=ENSEMBLE_RANKINGS):
    body = {
        "search": {"query": item["query"], "limit": task["limit"], "top_k": task["top_k"],
                   "quorum": task["quorum"], "result_unit": task["result_unit"],
                   "query_seed_fallback": query_seed_fallback,
                   "ensemble_rankings": list(ensemble_rankings),
                   **SHARED_SEARCH_SETTINGS, **SEARCH_WINDOW},
        "configurations": configurations, "benchmark": benchmark,
    }
    request = Request(f"{api_base_url}/evaluate", data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("evaluation_version") != "reuse_v1" or payload.get("cache_bypassed") is not True:
        raise RuntimeError("API lacks batch evaluation reuse support; restart the updated API")
    if payload.get("search_version") != SEARCH_VERSION:
        raise RuntimeError("batch evaluation search version mismatch")
    entries = payload.get("results")
    fields = ("mode", "stage", "ranking", "seed_method")
    if not isinstance(entries, list) or len(entries) != len(configurations):
        raise RuntimeError("incomplete batch evaluation response")
    for entry, expected in zip(entries, configurations):
        if any(entry.get(key) != expected[key] for key in fields):
            raise RuntimeError("batch evaluation returned reordered configurations")
        if not isinstance(entry.get("ranked"), list) or any(
            not isinstance(row, dict) or not isinstance(row.get("article"), str) for row in entry["ranked"]
        ):
            raise RuntimeError("invalid batch evaluation ranking")
        diagnostics = entry.setdefault("diagnostics", {})
        for source, target in (("lexical_candidate_article_urls", "lexical_reference_in_pool"),
                               ("hybrid_eligible_article_urls", "hybrid_eligible_reference_in_pool")):
            pool = payload.get("pool_membership", {}).get(source)
            if pool is not None:
                diagnostics[target] = len(set(item["relevant_urls"]) & set(pool))
    if benchmark and payload["performance"].get("equivalent") is not True:
        raise RuntimeError("benchmark found different baseline and optimized rankings; refusing to save")
    return payload


def _coverage(ranked_urls, relevant_urls):
    pool = set(ranked_urls)
    relevant = list(dict.fromkeys(relevant_urls))
    oracle = _metrics_at_ks(relevant, relevant)["metrics"]
    for metric in oracle:
        k = metric["k"]
        # The oracle can put any relevant article that made the pool in the
        # first k positions; the relevance denominator remains the full set.
        hits = min(k, len(set(relevant) & pool))
        metric["precision"] = hits / k
        metric["recall"] = hits / len(relevant) if relevant else 0.0
        metric["f1"] = (2 * metric["precision"] * metric["recall"] /
                        (metric["precision"] + metric["recall"])) if hits else 0.0
    hits = len(pool & set(relevant))
    return {"reference_in_pool": hits, "reference_pool_recall": hits / len(relevant), "oracle_metrics": oracle}


def _paired_comparisons(payload, item, methods):
    if payload.get("search_version") != SEARCH_VERSION or payload.get("stage") != "compare":
        raise RuntimeError("API lacks the expected stage comparison contract; restart the updated API")
    entries = payload.get("rankings")
    expected = [("lexical", "none"), ("hybrid", "none")]
    expected += [(stage, method) for method in methods for stage in ("ppr", "fused")]
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries) or [(e.get("stage"), e.get("seed_method")) for e in entries] != expected:
        raise RuntimeError("API returned incomplete or reordered stage comparisons")
    reference = set(item["relevant_urls"])
    shared = payload.get("diagnostics", {})
    shared_counts = {key: value for key, value in shared.items() if key not in (
        "lexical_candidate_article_urls", "hybrid_eligible_article_urls",
    )}
    for source, target in (
        ("lexical_candidate_article_urls", "lexical_reference_in_pool"),
        ("hybrid_eligible_article_urls", "hybrid_eligible_reference_in_pool"),
    ):
        if source in shared:
            shared_counts[target] = len(reference & set(shared[source]))
    comparisons = []
    baseline = None
    pool_id = payload.get("retrieval_id")
    if not isinstance(pool_id, str) or not pool_id:
        raise RuntimeError("API did not provide a retrieval identifier")
    for entry in entries:
        raw = entry.get("ranked")
        if not isinstance(raw, list) or any(not isinstance(e, dict) or not isinstance(e.get("article"), str) for e in raw):
            raise RuntimeError("invalid article ranking in stage comparison")
        urls = list(dict.fromkeys(e["article"] for e in raw))
        if entry["stage"] == "hybrid":
            baseline = set(urls)
            if entry.get("retrieval_id") != pool_id:
                raise RuntimeError("hybrid comparison has a mismatched retrieval identifier")
        elif entry["stage"] in ("ppr", "fused"):
            if set(urls) != baseline or entry.get("retrieval_id") != pool_id:
                raise RuntimeError("stage comparisons do not share the same hybrid article pool")
        diagnostics = {**shared_counts, **entry.get("diagnostics", {})}
        candidates = diagnostics.pop("lexical_candidate_article_urls", None)
        if candidates is not None:
            diagnostics["lexical_reference_in_pool"] = len(reference & set(candidates))
        embedded = diagnostics.pop("hybrid_eligible_article_urls", None)
        if embedded is not None:
            diagnostics["hybrid_eligible_reference_in_pool"] = len(reference & set(embedded))
        comparisons.append({
            "stage": entry["stage"], "seed_method": entry["seed_method"],
            "retrieval_id": entry.get("retrieval_id"), "ranked_urls": urls,
            "metrics": _metrics_at_ks(urls, item["relevant_urls"]),
            "ranking_metrics": _ranking_metrics(urls, item["relevant_urls"]),
            "coverage": _coverage(urls, item["relevant_urls"]), "diagnostics": diagnostics,
        })
    return comparisons


def _metrics_at_ks(
    ranked_urls: list[str], relevant_urls: list[str]
) -> dict[str, object]:
    """Compute P@k/R@k/F1@k against a fixed, full relevance reference."""
    ranked = list(dict.fromkeys(url for url in ranked_urls if url))
    relevant = list(dict.fromkeys(url for url in relevant_urls if url))
    relevant_set = set(relevant)
    metrics = []
    for k in BATCH_KS:
        hits = sum(url in relevant_set for url in ranked[:k])

        # Missing result slots count as non-relevant, even for short references.
        precision = hits / k
        recall = hits / len(relevant) if relevant else None
        if recall is None:
            f1 = None
        elif precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)

        metrics.append({
            "k": k,
            "relevant_total": len(relevant),
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })

    return {
        "metrics": metrics,
        "relevant_total": len(relevant),
        "ranked_total": len(ranked),
    }


RANKING_METRIC_KS = (5, 10, 20)


def _ranking_metrics(ranked_urls, relevant_urls):
    """Cutoff ranking metrics against the full binary relevance judgment set.

    Unlike _metrics_at_ks, these do not use the editorially ordered
    relevant_urls[:k] prefix. MAP@k is normalized by min(k, |relevant|).
    """
    ranked = list(dict.fromkeys(url for url in ranked_urls if url))
    relevant = {url for url in relevant_urls if url}
    hit_ranks = [rank for rank, url in enumerate(ranked, start=1) if url in relevant]
    result = {
        "mrr@20": 1.0 / hit_ranks[0] if hit_ranks and hit_ranks[0] <= 20 else 0.0,
    }
    for k in RANKING_METRIC_KS:
        relevant_ranks = [rank for rank in hit_ranks if rank <= k]
        precision_sum = sum(position / rank for position, rank in enumerate(relevant_ranks, start=1))
        denominator = min(k, len(relevant))
        result[f"map@{k}"] = precision_sum / denominator if denominator else 0.0
        dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
        ideal_hits = min(k, len(relevant))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        result[f"ndcg@{k}"] = dcg / idcg if idcg else 0.0
    return result


def _csv_fields(ks):
    fields = [
        "id", "query", "query_formulation", "preset", "stage", "ranking", "result_unit", "seed_method", "quorum", "limit", "top_k",
        "relevant_total", "ranked_total",
        "retrieval_id", "elapsed_seconds", "cache_bypassed", "reference_in_pool", "reference_pool_recall",
        "mode", "computation_reused", "group_wall_seconds", "baseline_wall_seconds", "speedup", "benchmark_equivalent",
        "retrieval_calls", "graph_builds", "ppr_runs",
    ]
    fields.extend(DIAGNOSTIC_COLUMNS)
    for k in ks:
        fields.extend((f"precision@{k}", f"recall@{k}", f"f1@{k}"))
        fields.extend((f"oracle_precision@{k}", f"oracle_recall@{k}", f"oracle_f1@{k}"))
    fields.extend(("mrr@20", "map@5", "map@10", "map@20", "ndcg@5", "ndcg@10", "ndcg@20"))

    return fields


def _csv_row(item, result, ks):
    row = {
        "id": item["id"], "query": item["query"],
        "preset": result["preset"], "seed_method": result["seed_method"],
        "quorum": result["quorum"], "limit": result["limit"], "top_k": result["top_k"],
        "relevant_total": result["metrics"]["relevant_total"],
        "ranked_total": result["metrics"]["ranked_total"],
        "query_formulation": item.get("query_formulation", "unspecified"),
        "stage": result.get("stage", "ppr"), "result_unit": result.get("result_unit", "chunks"),
        "ranking": result.get("ranking", result.get("stage", "ppr")),
        "retrieval_id": result.get("retrieval_id"), "elapsed_seconds": result.get("elapsed_seconds"),
        "cache_bypassed": result.get("cache_bypassed"),
        "mode": result.get("mode"), "computation_reused": result.get("computation_reused"),
    }
    performance = result.get("performance", {})
    optimized = performance.get("optimized", {})
    row.update(group_wall_seconds=optimized.get("wall_seconds"),
               baseline_wall_seconds=performance.get("baseline", {}).get("wall_seconds"),
               speedup=performance.get("speedup"), benchmark_equivalent=performance.get("equivalent"))
    row.update({key: optimized.get("counts", {}).get(key) for key in ("retrieval_calls", "graph_builds", "ppr_runs")})
    coverage = result.get("coverage", {})
    row.update({key: coverage.get(key) for key in ("reference_in_pool", "reference_pool_recall")})
    row.update(result.get("ranking_metrics", {}))
    row.update({key: result.get("diagnostics", {}).get(key) for key in DIAGNOSTIC_COLUMNS})
    by_k = {metric["k"]: metric for metric in result["metrics"]["metrics"]}
    oracle = {metric["k"]: metric for metric in coverage.get("oracle_metrics", [])}
    for k in ks:
        for name in ("precision", "recall", "f1"):
            row[f"{name}@{k}"] = by_k[k][name]
            row[f"oracle_{name}@{k}"] = oracle.get(k, {}).get(name)
    return row


DIAGNOSTIC_COLUMNS = (
    "cross_encoder_reranked_count", "cross_encoder_missing_document_count",
    "cross_encoder_candidate_cutoff",
    "effective_seed_method", "query_entity_count", "query_entity_matched_count",
    "query_seed_fallback_reason", "query_seed_type",
    "effective_quorum", "lexical_candidate_chunks", "lexical_candidate_articles",
    "embedded_candidate_chunks", "hybrid_eligible_articles", "returned_chunks", "returned_articles",
    "graph_surviving_articles", "entity_count", "ppr_seed_count", "seed_fallback",
    "candidate_cap_hit", "lexical_reference_in_pool", "hybrid_eligible_reference_in_pool",
)


def _csv_result_rows(item, result, ks):
    for comparison in result.get("comparisons", [result]):
        yield _csv_row(item, {**result, **comparison}, ks)


def _csv_rows(report: dict[str, object]) -> tuple[list[str], list[dict[str, object]]]:
    """Compatibility helper for small, already-loaded reports; runner streams rows."""
    rows = []
    for item in report["evaluations"]:
        for result in item["results"]:
            rows.extend(_csv_result_rows(item, result, report["ks"]))
    return _csv_fields(report["ks"]), rows


def _tasks(evaluations, presets=None, quorums=None, methods=None, rankings=None, compare=False, result_unit="chunks"):
    for item in evaluations:
        for name, preset in (presets if presets is not None else SEARCH_PRESETS).items():
            for quorum in (quorums if quorums is not None else QUORUM_VALUES):
                if compare:
                    # Keep each comparison as its own checkpoint/result.  The API
                    # request is still shared for the whole group below, so this
                    # does not give up the shared retrieval pool.
                    comparison_tasks = [("lexical", "none"), ("hybrid", "none")]
                    comparison_tasks += [
                        (stage, method)
                        for method in (methods if methods is not None else SEED_METHODS)
                        for stage in ("ppr", "fused")
                    ]
                    for stage, method in comparison_tasks:
                        yield item, {
                            "id": item["id"], "preset": name, "seed_method": method,
                            "quorum": quorum, "stage": stage, "ranking": stage,
                            "result_unit": result_unit, "mode": "compare", **preset,
                        }
                for method in (methods if methods is not None else SEED_METHODS):
                    for ranking in (rankings if rankings is not None else ("ppr",)):
                        yield item, {
                            "id": item["id"], "preset": name, "seed_method": method,
                            "quorum": quorum, "stage": "ppr", "ranking": ranking,
                            "result_unit": result_unit, "mode": "ranking", **preset,
                        }


def _format_duration(seconds):
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class _DurationEstimator:
    """Tiny in-memory EWMA estimator keyed by search configuration."""

    def __init__(self, alpha=0.3, workers=1):
        self.alpha = alpha
        self.workers = workers
        self.by_signature = {}
        self.global_ewma = None
        self.remaining = Counter()

    def set_remaining(self, units):
        self.remaining = Counter(
            _request_signature(entries[0][0], entries[0][1]) for _, entries in units
        )

    def update(self, signature, seconds):
        previous = self.by_signature.get(signature)
        value = seconds if previous is None else self.alpha * seconds + (1 - self.alpha) * previous
        self.by_signature[signature] = value
        self.global_ewma = value if self.global_ewma is None else self.alpha * seconds + (1 - self.alpha) * self.global_ewma

    def estimate(self, signature):
        return self.by_signature.get(signature, self.global_ewma)

    def complete(self, signature):
        self.remaining[signature] -= 1
        if self.remaining[signature] <= 0:
            del self.remaining[signature]

    def remaining_seconds(self):
        if not self.remaining:
            return 0.0
        weighted = []
        for signature, count in self.remaining.items():
            estimate = self.estimate(signature)
            if estimate is None:
                return None
            weighted.append((estimate, count))
        total = sum(seconds * count for seconds, count in weighted)
        longest = max(seconds for seconds, _ in weighted)
        # O(number of parameter signatures), independent of remaining row count.
        return max(total / self.workers, longest)


def _request_signature(item, task):
    """Return the parameters that determine one actual API request."""
    if task.get("reuse"):
        return ("evaluate", task["preset"], task["limit"], task["top_k"], task["quorum"], task["result_unit"])
    if task["mode"] == "compare":
        return (task["mode"], task["preset"], task["limit"], task["top_k"], task["quorum"], task["result_unit"])
    return (task["mode"], task["preset"], task["limit"], task["top_k"], task["quorum"],
            task["stage"], task["ranking"], task["seed_method"], task["result_unit"])


def _work_units(task_list):
    """Group tasks that share one HTTP request; other rows are singleton work."""
    index = 0
    while index < len(task_list):
        item, task = task_list[index]
        if task.get("reuse"):
            key = (item["id"], task["preset"], task["quorum"])
            end = index + 1
            while end < len(task_list):
                next_item, next_task = task_list[end]
                if (not next_task.get("reuse") or
                    (next_item["id"], next_task["preset"], next_task["quorum"]) != key):
                    break
                end += 1
        elif task["mode"] == "compare":
            key = (item["id"], task["preset"], task["quorum"], task["limit"], task["top_k"])
            end = index + 1
            while end < len(task_list):
                next_item, next_task = task_list[end]
                if next_task["mode"] != "compare" or (
                    next_item["id"], next_task["preset"], next_task["quorum"],
                    next_task["limit"], next_task["top_k"],
                ) != key:
                    break
                end += 1
        else:
            end = index + 1
        yield index, task_list[index:end]
        index = end


def _execute_work_unit(api_base_url, entries, methods, result_unit, benchmark, query_seed_fallback,
                       ensemble_rankings=ENSEMBLE_RANKINGS):
    """Perform one HTTP request and prepare all rows it serves."""
    started = time.monotonic()
    item, first_task = entries[0]
    label = (f"{item['id']} / {first_task['preset']} / "
             f"quorum={first_task['quorum']} / mode={first_task['mode']}")
    try:
        if first_task.get("reuse"):
            fields = ("mode", "stage", "ranking", "seed_method")
            configurations = [{key: task[key] for key in fields} for _, task in entries]
            if query_seed_fallback == "hits" and ensemble_rankings == ENSEMBLE_RANKINGS:
                payload = _evaluation_from_api(api_base_url, item, first_task, configurations, benchmark)
            elif query_seed_fallback == "hits":
                payload = _evaluation_from_api(api_base_url, item, first_task, configurations, benchmark,
                                               ensemble_rankings=ensemble_rankings)
            else:
                payload = _evaluation_from_api(api_base_url, item, first_task, configurations, benchmark,
                                               query_seed_fallback, ensemble_rankings)
            by_configuration = {tuple(entry[key] for key in fields): entry for entry in payload["results"]}
            elapsed = time.monotonic() - started
            results = []
            for row_item, task in entries:
                entry = by_configuration[tuple(task[key] for key in fields)]
                ranked_urls = list(dict.fromkeys(row["article"] for row in entry["ranked"]))
                result = {
                    **{key: value for key, value in task.items() if key != "id"},
                    "ranked_urls": ranked_urls,
                    "metrics": _metrics_at_ks(ranked_urls, row_item["relevant_urls"]),
                    "ranking_metrics": _ranking_metrics(ranked_urls, row_item["relevant_urls"]),
                    "coverage": _coverage(ranked_urls, row_item["relevant_urls"]),
                    "cache_bypassed": True, "elapsed_seconds": round(elapsed, 3),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "diagnostics": entry.get("diagnostics", {}),
                    "retrieval_id": entry.get("retrieval_id"),
                    "computation_reused": entry["computation_reused"],
                    "performance": payload["performance"],
                }
                results.append((row_item, task, result))
            return results, elapsed

        request_args = (
            api_base_url, item["query"],
            {"limit": first_task["limit"], "top_k": first_task["top_k"]},
            methods[0] if first_task["mode"] == "compare" else first_task["seed_method"],
            first_task["quorum"],
        )
        if first_task["mode"] == "compare":
            payload = _response_from_api(*request_args, stage="compare", result_unit=result_unit,
                                         seed_methods=methods, query_seed_fallback=query_seed_fallback)
            if payload.get("result_unit") != result_unit:
                raise RuntimeError("API returned the wrong result unit")
            comparisons = _paired_comparisons(payload, item, methods)
            by_comparison = {(row["stage"], row["seed_method"]): row for row in comparisons}
            elapsed = time.monotonic() - started
            results = []
            for row_item, task in entries:
                comparison = by_comparison[(task["stage"], task["seed_method"])]
                result = {
                    **{key: value for key, value in task.items() if key != "id"},
                    "ranked_urls": comparison["ranked_urls"],
                    "metrics": comparison["metrics"], "coverage": comparison["coverage"],
                    "ranking_metrics": comparison["ranking_metrics"],
                    "cache_bypassed": True, "elapsed_seconds": round(elapsed, 3),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "diagnostics": comparison["diagnostics"],
                    "retrieval_id": comparison["retrieval_id"],
                }
                results.append((row_item, task, result))
            return results, elapsed

        options = {}
        if result_unit != "chunks":
            options["result_unit"] = result_unit
        options["ranking"] = first_task["ranking"]
        options["query_seed_fallback"] = query_seed_fallback
        if first_task["ranking"] == "ensemble_rrf":
            options["ensemble_rankings"] = ensemble_rankings
        ranked_urls = _ranked_urls_from_api_compat(*request_args, options)
        elapsed = time.monotonic() - started
        result = {
            **{key: value for key, value in first_task.items() if key != "id"},
            "ranked_urls": ranked_urls,
            "metrics": _metrics_at_ks(ranked_urls, item["relevant_urls"]),
            "ranking_metrics": _ranking_metrics(ranked_urls, item["relevant_urls"]),
            "coverage": _coverage(ranked_urls, item["relevant_urls"]),
            "cache_bypassed": True, "elapsed_seconds": round(elapsed, 3),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        return [(item, first_task, result)], elapsed
    except Exception as exc:
        raise RuntimeError(f"evaluation {label} failed: {exc}") from exc


class _InlineExecutor:
    """Keep the default single-worker path on the main thread for signals."""
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @staticmethod
    def submit(function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future


def _timing_text(started, remaining_seconds, remaining=None, now=None):
    """Session elapsed time and an ETA based on actual API-request timings."""
    now = time.monotonic() if now is None else now
    elapsed = _format_duration(now - started)
    # Keep the old helper call shape available to callers outside the runner.
    if remaining is not None:
        durations = remaining_seconds
        if remaining <= 0:
            remaining_seconds = 0.0
        elif not durations:
            remaining_seconds = None
        else:
            remaining_seconds = sum(durations) / len(durations) * remaining
    if remaining_seconds is None:
        estimate = "calculating"
    elif remaining_seconds <= 0:
        estimate = "00:00:00"
    else:
        estimate = f"~{_format_duration(math.ceil(remaining_seconds))}"
    return f"Elapsed: {elapsed} | Remaining: {estimate}"


def _export_checkpoint(journal, metadata, evaluations, json_path, csv_path, status, total):
    """Stream a consistent view from the journal, never loading prior results."""
    # Unique temporary names must never clobber an unrelated user's *.tmp file.
    with ExitStack() as stack:
        detailed = stack.enter_context(tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=json_path.parent,
            prefix=f".{json_path.name}.", suffix=".tmp", delete=False,
        ))
        json_temp = Path(detailed.name)
        stack.callback(json_temp.unlink, missing_ok=True)
        summary = stack.enter_context(tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=csv_path.parent,
            prefix=f".{csv_path.name}.", suffix=".tmp", delete=False,
        ))
        csv_temp = Path(summary.name)
        stack.callback(csv_temp.unlink, missing_ok=True)
        writer = csv.DictWriter(summary, fieldnames=_csv_fields(metadata["ks"]))
        writer.writeheader()
        detailed.write("{\n")
        for key, value in {
            **metadata, "status": status, "completed_results": journal.completed,
            "total_results": total,
        }.items():
            detailed.write(json.dumps(key) + ": ")
            json.dump(value, detailed, ensure_ascii=False)
            detailed.write(",\n")
        detailed.write('"evaluations": [\n')
        records = journal.records()
        pending = next(records, None)
        for position, item in enumerate(evaluations):
            if position:
                detailed.write(",\n")
            detailed.write("{")
            for key in ("id", "query", "query_formulation", "relevant_urls"):
                detailed.write(json.dumps(key) + ": ")
                json.dump(item[key], detailed, ensure_ascii=False)
                detailed.write(", ")
            detailed.write('"results": [\n')
            first = True
            while pending is not None and pending["task"]["id"] == item["id"]:
                result = pending["result"]
                if not first:
                    detailed.write(",\n")
                json.dump(result, detailed, ensure_ascii=False)
                writer.writerows(_csv_result_rows(item, result, metadata["ks"]))
                first = False
                pending = next(records, None)
            detailed.write("\n]}")
        detailed.write("\n]}\n")
        durable_flush(detailed)
        durable_flush(summary)
        with defer_stop_signals():
            os.replace(json_temp, json_path)
            os.replace(csv_temp, csv_path)
            sync_directory(json_path.parent)
            if csv_path.parent != json_path.parent:
                sync_directory(csv_path.parent)


def run_batch_evaluation(
    engine,
    api_base_url: str,
    evaluations: list[dict[str, object]],
    json_path: Path,
    csv_path: Path,
    *,
    resume: bool = False,
    overwrite: bool = False,
    compare_stages: bool = False,
    result_unit: str = "chunks",
    presets=None,
    quorums=None,
    seed_methods=None,
    rankings=None,
    reuse: bool = False,
    benchmark: bool = False,
    workers: int = 1,
    query_seed_fallback: str = "hits",
    ensemble_rankings=None,
) -> dict[str, object]:
    """Persist each configuration immediately; return only a small run summary."""
    api_base_url = _normalize_api_base_url(api_base_url)
    evaluations = validate_document({"schema_version": SCHEMA_VERSION, "evaluations": evaluations})
    if result_unit not in ("chunks", "articles"):
        raise ValueError("result_unit must be chunks or articles")
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("workers must be an integer between 1 and 16")
    if query_seed_fallback not in QUERY_SEED_FALLBACKS:
        raise ValueError(f"query_seed_fallback must be one of {QUERY_SEED_FALLBACKS}")
    ensemble_methods = tuple(ensemble_rankings) if ensemble_rankings is not None else ENSEMBLE_RANKINGS
    if (not ensemble_methods or len(set(ensemble_methods)) != len(ensemble_methods)
            or any(method not in ENSEMBLE_COMPONENT_RANKINGS for method in ensemble_methods)):
        raise ValueError("ensemble_rankings must contain unique supported non-ensemble rankings")
    names = tuple(presets) if presets is not None else tuple(SEARCH_PRESETS)
    methods = tuple(seed_methods) if seed_methods is not None else SEED_METHODS
    selected_rankings = tuple(rankings) if rankings is not None else RANKINGS
    thresholds = tuple(quorums) if quorums is not None else QUORUM_VALUES
    if not names or any(name not in SEARCH_PRESETS for name in names) or len(set(names)) != len(names):
        raise ValueError("invalid or repeated presets")
    if not methods or any(method not in SEED_METHODS for method in methods) or len(set(methods)) != len(methods):
        raise ValueError("invalid or repeated seed methods")
    if not thresholds or any(not 0 <= q <= 1 for q in thresholds) or len(set(thresholds)) != len(thresholds):
        raise ValueError("invalid or repeated quorums")
    valid_rankings = set(RANKINGS)
    if not selected_rankings or any(ranking not in valid_rankings for ranking in selected_rankings) or len(set(selected_rankings)) != len(selected_rankings):
        raise ValueError(f"invalid or repeated rankings; valid values: {sorted(valid_rankings)}")
    selected_presets = {name: SEARCH_PRESETS[name] for name in names}
    task_list = list(_tasks(evaluations, selected_presets, thresholds, methods, selected_rankings, compare_stages, result_unit))
    if benchmark and not reuse:
        raise ValueError("benchmark requires reuse")
    if reuse:
        task_list = [(item, {**task, "reuse": True}) for item, task in task_list]
    def tasks():
        return iter(task_list)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "search_api": f"{api_base_url}/search",
        "search_window": SEARCH_WINDOW,
        "shared_search_settings": SHARED_SEARCH_SETTINGS,
        "quorum_values": list(thresholds),
        "presets": selected_presets,
        "seed_methods": list(methods),
        "rankings": list(selected_rankings),
        "compare_stages": compare_stages, "result_unit": result_unit,
        "comparison_persistence": "individual_rows_v2",
        "reuse": reuse, "benchmark": benchmark,
        "query_seed_fallback": query_seed_fallback,
        "ensemble_rankings": list(ensemble_methods),
        "search_version": SEARCH_VERSION,
        "bypass_cache": True,
        "ks": list(BATCH_KS),
        "relevance_reference": "all_relevant_urls_fixed",
    }
    config = {
        "metadata": metadata,
        "evaluations": evaluations,
        "metric_algorithm": "fixed_full_relevance_at_k_v2",
        "ranking_metric_algorithm": "binary_full_relevance_mrr_map_ndcg_v1",
    }
    total = len(task_list)
    metadata["total_comparison_rows"] = total
    journal_path = json_path.with_suffix(".jsonl")
    started = time.monotonic()
    work_units = list(_work_units(task_list))
    duration_estimator = _DurationEstimator(workers=workers)
    status = "running"
    stop_signal = None
    with output_lock(json_path), stop_on_termination():
        ensure_output_available((json_path, csv_path), overwrite, resume)
        journal = ResultJournal(journal_path, config, (task for _, task in tasks()), resume)
        live_summary = LiveSummary(BATCH_KS)
        items_by_id = {item["id"]: item for item in evaluations}
        for record in journal.records():
            live_summary.add(items_by_id[record["task"]["id"]], record["result"])
        runnable = [unit for unit in work_units if unit[0] + len(unit[1]) > journal.completed]
        duration_estimator.set_remaining(runnable)
        print(
            f"Batch: {journal.completed}/{total} saved. Live CSV: {csv_path}. "
            f"Live summary: {summary_paths(json_path)[0]}. "
                f"Checkpoint: {journal_path} | Workers: {workers} | "
                f"{_timing_text(started, duration_estimator.remaining_seconds())}",
            flush=True,
        )
        try:
            live_summary.write(json_path, journal.completed, total, status)
            if journal.completed < total:
                _validate_relevant_urls_exist(engine, evaluations)
            _export_checkpoint(journal, metadata, evaluations, json_path, csv_path, status, total)
            # The export wrote one UTF-8 BOM before the header. Append ordinary
            # UTF-8 so subsequent rows can never introduce embedded BOMs.
            with csv_path.open("a", encoding="utf-8", newline="") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=_csv_fields(metadata["ks"]))
                executor_type = ThreadPoolExecutor if workers > 1 else _InlineExecutor
                executor_options = {"max_workers": workers, "thread_name_prefix": "batch-evaluation"} if workers > 1 else {}
                with executor_type(**executor_options) as executor:
                    pending = {}
                    next_submit = 0

                    def submit_bounded():
                        nonlocal next_submit
                        while next_submit < len(runnable) and len(pending) < workers:
                            unit_start, entries = runnable[next_submit]
                            item, task = entries[0]
                            label = (f"{item['id']} / {task['preset']} / ranking={task['ranking']} / "
                                     f"{task['seed_method']} / quorum={task['quorum']} / mode={task['mode']}")
                            print(f"[Queue {next_submit + 1}/{len(runnable)}; max-running={workers}] {label}", flush=True)
                            future = executor.submit(_execute_work_unit, api_base_url, entries, methods,
                                                     result_unit, benchmark, query_seed_fallback, ensemble_methods)
                            pending[next_submit] = future
                            next_submit += 1

                    submit_bounded()
                    for unit_position, (unit_start, entries) in enumerate(runnable):
                        unit_results, elapsed = pending.pop(unit_position).result()
                        item, first_task = entries[0]
                        signature = _request_signature(item, first_task)
                        duration_estimator.update(signature, elapsed)
                        duration_estimator.complete(signature)
                        unit_eta = _timing_text(started, duration_estimator.remaining_seconds())
                        for offset_in_unit, (row_item, task, result) in enumerate(unit_results):
                            index = unit_start + offset_in_unit
                            if index < journal.completed:
                                continue
                            if index != journal.completed:
                                raise RuntimeError(f"internal task ordering error: expected {journal.completed}, got {index}")
                            label = (f"{row_item['id']} / {task['preset']} / ranking={task['ranking']} / "
                                     f"{task['seed_method']} / quorum={task['quorum']} / mode={task['mode']}")
                            with defer_stop_signals():
                                journal.append(task, result)
                                writer.writerows(_csv_result_rows(row_item, result, metadata["ks"]))
                                durable_flush(output_file)
                                live_summary.add(row_item, result)
                                live_summary.write(json_path, journal.completed, total, status)
                            metrics = " | ".join(
                                f"k={m['k']}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f}"
                                for m in result["metrics"]["metrics"]
                            )
                            print(
                                f"[{journal.completed}/{total}] Saved {label} ({result['elapsed_seconds']:.1f}s) | "
                                f"{unit_eta} | {metrics}",
                                flush=True,
                            )
                        del unit_results
                        submit_bounded()
            status = "completed"
        except KeyboardInterrupt as exc:
            status = "interrupted"
            stop_signal = exc.signum if isinstance(exc, BatchStopped) else signal.SIGINT
            print(
                f"Stopped: {journal.completed}/{total} saved | "
                f"{_timing_text(started, duration_estimator.remaining_seconds())}. "
                "Restart with --resume; the unsaved request will run again.",
                flush=True,
            )
        except Exception:
            status = "failed"
            print(
                f"Batch failed with {journal.completed}/{total} saved. "
                f"{_timing_text(started, duration_estimator.remaining_seconds())}. "
                "Fix the error and restart with --resume.",
                file=sys.stderr, flush=True,
            )
            raise
        finally:
            # Disk exhaustion may also prevent export; the journal stays authoritative.
            _export_checkpoint(journal, metadata, evaluations, json_path, csv_path, status, total)
            live_summary.write(json_path, journal.completed, total, status)
        if status == "completed":
            print(
                f"Batch complete: {journal.completed}/{total} saved | "
                f"{_timing_text(started, 0)}",
                flush=True,
            )
    return {
        "status": status, "completed_results": journal.completed, "total_results": total,
        "json_path": str(json_path), "csv_path": str(csv_path), "journal_path": str(journal_path),
        "summary_path": str(summary_paths(json_path)[0]), "summary_json_path": str(summary_paths(json_path)[1]),
        "stop_signal": stop_signal, "workers": workers,
    }
