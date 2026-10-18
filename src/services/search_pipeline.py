"""Stage comparisons without re-running retrieval or importing model services."""

import copy
from datetime import date
import hashlib
import json
import math
from time import perf_counter


SEARCH_VERSION = "stages_v9"
CACHE_NAMESPACE = "v19"
SEED_METHODS = ("louvain", "hits", "ppr_top10", "query_entities")
QUERY_SEED_FALLBACKS = ("hits", "louvain", "ppr_top10")
STAGES = ("lexical", "hybrid", "ppr", "fused", "compare")
RANKINGS = ("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr",
            "graph_rwr", "graph_hits", "graph_salsa", "graph_path",
            "graph_walk", "graph_fusion", "graph_hits_cross_encoder",
            "lexical", "vector", "ensemble_rrf")
ENSEMBLE_RANKINGS = ("rrf", "cross_encoder", "ppr")
ENSEMBLE_COMPONENT_RANKINGS = tuple(ranking for ranking in RANKINGS if ranking != "ensemble_rrf")
CROSS_ENCODER_RERANK_LIMIT = 250


def search_request(searcher, ranker, cache, params):
    """Cache retrieval independently so every graph seed sees the same pool."""
    query = (params.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    bypass_value = str(params.get("bypass_cache", "false")).strip().lower()
    if bypass_value not in ("", "false", "0", "true", "1"):
        raise ValueError("bypass_cache must be true/false or 1/0")
    bypass_cache = bypass_value in ("true", "1")
    diagnostics_value = str(params.get("pool_diagnostics", "false")).strip().lower()
    if diagnostics_value not in ("", "false", "0", "true", "1"):
        raise ValueError("pool_diagnostics must be true/false or 1/0")
    include_pool_diagnostics = diagnostics_value in ("true", "1")
    try:
        raw_k = str(params.get("top_k", "5")).strip().lower()
        top_k = 5 if raw_k in ("", "null", "none") else int(raw_k)
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))
        cap = int(params.get("candidate_cap", 20000))
        quorum = float(params.get("quorum", 0.7))
        graph_alpha = float(params.get("graph_alpha", 0.85))
        graph_hop_decay = float(params.get("graph_hop_decay", 0.5))
        graph_mix = float(params.get("graph_mix", 0.3))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid numeric search parameter") from exc
    if top_k < 1 or limit < 1 or offset < 0 or cap < 1 or not 0 <= quorum <= 1:
        raise ValueError("positive top_k/limit/candidate_cap, nonnegative offset and quorum in [0,1] required")
    if not 0 < graph_alpha < 1 or not 0 <= graph_hop_decay <= 1 or not 0 <= graph_mix <= 1:
        raise ValueError("graph_alpha must be in (0,1), graph_hop_decay and graph_mix in [0,1]")
    stage = (params.get("stage") or "ppr").strip().lower()
    ranking = (params.get("ranking") or "").strip().lower() or None
    unit = (params.get("result_unit") or "chunks").strip().lower()
    method = (params.get("seed_method") or "hits").strip().lower()
    query_seed_fallback = (params.get("query_seed_fallback") or "hits").strip().lower()
    raw_methods = params.get("seed_methods") or ",".join(SEED_METHODS)
    if isinstance(raw_methods, str):
        raw_methods = raw_methods.split(",")
    raw_ensemble = params.get("ensemble_rankings") or ",".join(ENSEMBLE_RANKINGS)
    if isinstance(raw_ensemble, str):
        raw_ensemble = raw_ensemble.split(",")
    if (not isinstance(raw_methods, (list, tuple)) or not all(isinstance(m, str) for m in raw_methods)
            or not isinstance(raw_ensemble, (list, tuple)) or not all(isinstance(m, str) for m in raw_ensemble)):
        raise ValueError("seed_methods and ensemble_rankings must be strings or lists of strings")
    methods = tuple(dict.fromkeys(m.strip().lower() for m in raw_methods))
    ensemble_rankings = tuple(dict.fromkeys(m.strip().lower() for m in raw_ensemble))
    if ranking is not None and ranking not in RANKINGS:
        raise ValueError("invalid ranking")
    if (stage not in STAGES or unit not in ("chunks", "articles") or method not in SEED_METHODS
            or any(m not in SEED_METHODS for m in methods) or query_seed_fallback not in QUERY_SEED_FALLBACKS
            or not ensemble_rankings or any(m not in RANKINGS or m == "ensemble_rrf" for m in ensemble_rankings)):
        raise ValueError("invalid stage, result_unit, seed_method or seed_methods")
    date_from, date_to = params.get("date_from"), params.get("date_to")
    if date_from:
        date.fromisoformat(date_from)
    if date_to:
        date.fromisoformat(date_to)
    if date_from and date_to and date.fromisoformat(date_from) > date.fromisoformat(date_to):
        raise ValueError("date_from must be before or equal to date_to")
    settings = {
        "query": query, "top_k": top_k, "limit": limit, "offset": offset,
        "date_from": date_from, "date_to": date_to,
        "quorum_threshold": quorum, "candidate_cap": cap, "result_unit": unit,
        "retrieval_stage": "lexical" if stage == "lexical" else "hybrid",
        "include_pool_diagnostics": include_pool_diagnostics,
    }

    def key(kind, value):
        digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        # Algorithm changes must not reuse entries from an earlier search version.
        return f"{CACHE_NAMESPACE}:{SEARCH_VERSION}:{kind}:{digest}"

    graph_settings = {"graph_alpha": graph_alpha, "graph_hop_decay": graph_hop_decay, "graph_mix": graph_mix}
    response_key = key("response", {**settings, **graph_settings, "stage": stage, "ranking": ranking,
                                    "seed_method": method, "seed_methods": methods,
                                    "query_seed_fallback": query_seed_fallback,
                                    "ensemble_rankings": ensemble_rankings})
    cached = cache.hget("search_cache", response_key) if not bypass_cache else None
    if cached:
        return json.loads(cached)
    retrieval_key = key("retrieval", settings)
    cached_retrieval = cache.hget("search_cache", retrieval_key) if not bypass_cache else None
    if cached_retrieval:
        retrieval = json.loads(cached_retrieval)
    else:
        retrieval = searcher.search(**settings)
        for article in retrieval.get("articles", []):
            if article.get("date_published") is not None:
                article["date_published"] = str(article["date_published"])
        if not bypass_cache:
            cache.hset("search_cache", retrieval_key, json.dumps(retrieval, default=str))
    active_ranker = ranker.for_batch() if hasattr(ranker, "for_batch") else ranker
    ranking_started = perf_counter()
    response = run_pipeline(retrieval, active_ranker, stage, method, methods, ranking=ranking, query=query,
                            graph_alpha=graph_alpha, graph_hop_decay=graph_hop_decay, graph_mix=graph_mix,
                            query_seed_fallback=query_seed_fallback, ensemble_rankings=ensemble_rankings)
    ranking_seconds = perf_counter() - ranking_started
    response["timings"] = {
        **retrieval.get("timings", {}),
        "ranking_seconds": ranking_seconds,
        **getattr(active_ranker, "batch_timings", {}),
        "cross_encoder_seconds": response.get("diagnostics", {}).get("cross_encoder_seconds", 0.0),
        "search_pipeline_seconds": perf_counter() - ranking_started,
    }
    response["cache_bypassed"] = bypass_cache
    if not bypass_cache:
        cache.hset("search_cache", response_key, json.dumps(response, default=str))
    return response


def fuse_rankings(hybrid, ppr, rrf_k=60):
    return reciprocal_rank_fusion((hybrid, ppr), rrf_k=rrf_k)


def reciprocal_rank_fusion(rankings, rrf_k=60, candidate_urls=None):
    """Equal-weight RRF over multiple article rankings, with stable tie breaks."""
    if rrf_k < 0:
        raise ValueError("rrf_k must be non-negative")
    scores = {}
    for ranking in rankings:
        seen = set()
        for entry in ranking:
            url = entry["article"]
            if url in seen:
                continue
            seen.add(url)
            scores[url] = scores.get(url, 0.0) + 1 / (rrf_k + len(seen))
    if candidate_urls is not None:
        scores = {url: score for url, score in scores.items() if url in candidate_urls}
    return [{"article": url, "score": score} for url, score in
            sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]


def run_pipeline(retrieval, ranker, stage="ppr", seed_method="hits", seed_methods=SEED_METHODS, ranking=None, query=None,
                 graph_alpha=0.85, graph_hop_decay=0.5, graph_mix=0.3, query_seed_fallback="hits",
                 ensemble_rankings=ENSEMBLE_RANKINGS):
    if stage not in STAGES or seed_method not in SEED_METHODS:
        raise ValueError("invalid search stage or seeding method")
    if not seed_methods or any(method not in SEED_METHODS for method in seed_methods):
        raise ValueError("invalid comparison seed_methods")
    if query_seed_fallback not in QUERY_SEED_FALLBACKS:
        raise ValueError("invalid query_seed_fallback")
    ensemble_rankings = tuple(dict.fromkeys(ensemble_rankings))
    if not ensemble_rankings or any(method not in ENSEMBLE_COMPONENT_RANKINGS for method in ensemble_rankings):
        raise ValueError("ensemble_rankings must list supported non-ensemble ranking methods")
    response = copy.deepcopy(retrieval)
    hybrid = response.get("ranked", [])
    lexical = response.get("lexical_ranked", [])
    vector = response.get("vector_ranked", [])
    lexical_only = response.get("lexical_only_ranked", [])
    diagnostics = response.get("diagnostics", {})
    # Large pool-membership lists belong only in the shared comparison header,
    # not eight times inside the per-stage records or every ordinary UI response.
    counts = {key: value for key, value in diagnostics.items() if key not in (
        "lexical_candidate_article_urls", "hybrid_eligible_article_urls",
    )}
    common = {"retrieval_id": response.get("retrieval_id"), "result_unit": response.get("result_unit", "chunks")}
    response.update(search_version=SEARCH_VERSION, stage=stage, ranking=ranking or stage)
    if ranking == "hybrid_max":
        response["ranked"] = hybrid
        return response
    candidate_urls = {entry["article"] for entry in hybrid}
    if ranking == "lexical":
        response["ranked"] = [entry for entry in (lexical_only or lexical) if entry["article"] in candidate_urls]
        return response
    if ranking == "vector":
        response["ranked"] = [entry for entry in vector if entry["article"] in candidate_urls]
        return response
    if ranking == "ensemble_rrf":
        component_rankings = []
        cross_encoder_seconds = 0.0
        for component in ensemble_rankings:
            component_response = run_pipeline(
                retrieval, ranker, "ppr", seed_method, seed_methods, ranking=component, query=query,
                graph_alpha=graph_alpha, graph_hop_decay=graph_hop_decay, graph_mix=graph_mix,
                query_seed_fallback=query_seed_fallback, ensemble_rankings=ensemble_rankings,
            )
            component_rankings.append(component_response.get("ranked", []))
            cross_encoder_seconds += component_response.get("diagnostics", {}).get("cross_encoder_seconds", 0.0)
        response["ranked"] = reciprocal_rank_fusion(component_rankings, candidate_urls=candidate_urls)
        response["diagnostics"] = {**counts, "ensemble_rankings": list(ensemble_rankings),
                                   "ensemble_component_count": len(ensemble_rankings),
                                   "ensemble_candidate_count": len(response["ranked"]),
                                   "cross_encoder_seconds": cross_encoder_seconds}
        return response
    if ranking == "rrf":
        candidate_urls = {entry["article"] for entry in hybrid}
        lexical_for_rrf = lexical_only or lexical
        vector_for_rrf = vector
        response["ranked"] = [
            entry for entry in fuse_rankings(lexical_for_rrf, vector_for_rrf)
            if entry["article"] in candidate_urls
        ]
        return response
    if ranking == "cross_encoder":
        hybrid_urls = [entry["article"] for entry in hybrid]
        rerank_urls = hybrid_urls[:CROSS_ENCODER_RERANK_LIMIT]
        rerank_url_set = set(rerank_urls)
        # Search results are ordered by retrieval score; preserve only the first
        # (best-ranked) chunk for each candidate article.
        first_chunk_by_url = {}
        for row in response.get("results", []):
            url = row.get("article_url")
            chunk = row.get("chunk")
            if url in rerank_url_set and url not in first_chunk_by_url and isinstance(chunk, str) and chunk.strip():
                first_chunk_by_url[url] = row
        rerank_results = [first_chunk_by_url[url] for url in rerank_urls if url in first_chunk_by_url]
        cross_encoder_started = perf_counter()
        score_cache = getattr(ranker, "_batch_cross_encoder_scores", None)
        reranked = (_cross_encoder_rank(query, rerank_results, score_cache=score_cache)
                    if score_cache is not None else _cross_encoder_rank(query, rerank_results))
        cross_encoder_seconds = perf_counter() - cross_encoder_started
        reranked_urls = {entry["article"] for entry in reranked}
        response["ranked"] = reranked + [
            entry for entry in hybrid
            if entry["article"] not in reranked_urls
        ]
        response.setdefault("diagnostics", {})[
            "cross_encoder_reranked_count"
        ] = len(rerank_results)
        response["diagnostics"]["cross_encoder_missing_document_count"] = len(rerank_url_set - set(first_chunk_by_url))
        response["diagnostics"]["cross_encoder_seconds"] = cross_encoder_seconds
        return response
    if ranking == "graph_hits_cross_encoder":
        hybrid_urls = [entry["article"] for entry in hybrid]
        rerank_urls = hybrid_urls[:CROSS_ENCODER_RERANK_LIMIT]
        rerank_url_set = set(rerank_urls)
        first_chunk_by_url = {}
        for row in response.get("results", []):
            url, chunk = row.get("article_url"), row.get("chunk")
            if url in rerank_url_set and url not in first_chunk_by_url and isinstance(chunk, str) and chunk.strip():
                first_chunk_by_url[url] = row
        rerank_results = [first_chunk_by_url[url] for url in rerank_urls if url in first_chunk_by_url]
        cross_encoder_started = perf_counter()
        score_cache = getattr(ranker, "_batch_cross_encoder_scores", None)
        probabilities = (_cross_encoder_probabilities(query, rerank_results, score_cache=score_cache)
                         if score_cache is not None else _cross_encoder_probabilities(query, rerank_results))
        cross_encoder_seconds = perf_counter() - cross_encoder_started
        if rerank_urls:
            graph_ranked, graph = ranker.graph_hits_cross_encoder(
                rerank_urls, query=query, article_probabilities=probabilities,
                fallback_seed_method=seed_method, query_seed_fallback=query_seed_fallback,
            )
        else:
            graph_ranked, graph = [], {"meta": {"graph_surviving_articles": 0,
                                                  "query_seed_fallback_reason": "no_candidates"}}
        reranked_urls = {row["article"] for row in graph_ranked}
        response["ranked"] = graph_ranked + [row for row in hybrid if row["article"] not in reranked_urls]
        response["diagnostics"] = {
            **counts, **graph.get("meta", {}),
            "cross_encoder_reranked_count": len(rerank_results),
            "cross_encoder_missing_document_count": len(rerank_url_set - set(first_chunk_by_url)),
            "cross_encoder_candidate_cutoff": CROSS_ENCODER_RERANK_LIMIT,
            "cross_encoder_seconds": cross_encoder_seconds,
        }
        return response
    if ranking in ("graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion"):
        urls = [entry["article"] for entry in hybrid]
        if urls:
            graph_kwargs = {
                "method": "hits" if ranking == "graph_fusion" else ranking.removeprefix("graph_"),
                "seed_method": seed_method, "alpha": graph_alpha, "hop_decay": graph_hop_decay,
            }
            if seed_method == "query_entities":
                graph_kwargs.update(query=query, query_seed_fallback=query_seed_fallback)
            try:
                graph_ranked, graph = ranker.graph_rank(urls, **graph_kwargs)
            except TypeError as exc:
                if seed_method != "query_entities" or "unexpected keyword argument" not in str(exc):
                    raise
                graph_kwargs.pop("query", None)
                graph_kwargs.pop("query_seed_fallback", None)
                graph_ranked, graph = ranker.graph_rank(urls, **graph_kwargs)
        else:
            graph_ranked, graph = [], {"meta": {"graph_surviving_articles": 0}}
        if ranking == "graph_fusion":
            graph_ranked = reciprocal_rank_fusion([hybrid, graph_ranked], candidate_urls=set(urls))
        response["ranked"] = graph_ranked
        response["diagnostics"] = {**counts, **graph.get("meta", {}), "graph_alpha": graph_alpha,
                                   "graph_hop_decay": graph_hop_decay}
        if ranking == "graph_fusion":
            response["diagnostics"].update(graph_fusion_method="rrf", graph_fusion_rrf_k=60)
        else:
            response["diagnostics"]["graph_mix"] = graph_mix
        return response
    if stage in ("lexical", "hybrid"):
        response["ranked"] = lexical if stage == "lexical" else hybrid
        response["diagnostics"] = counts
        return response
    urls = [entry["article"] for entry in hybrid]
    rankings = []
    if stage == "compare":
        rankings.extend([
            {**common, "retrieval_id": common["retrieval_id"] + ":lexical",
             "stage": "lexical", "seed_method": "none", "ranked": lexical,
             "diagnostics": {**counts, "returned_articles": len(lexical),
                             "returned_chunks": diagnostics.get("lexical_returned_chunks")}},
            {**common, "stage": "hybrid", "seed_method": "none", "ranked": hybrid, "diagnostics": counts},
        ])
    for method in dict.fromkeys(seed_methods if stage == "compare" else (seed_method,)):
        if urls:
            rank_kwargs = {"mmr_enabled": True} if ranking == "mmr" else {}
            seed_kwargs = {"seed_method": method}
            if method == "query_entities":
                seed_kwargs.update(query=query, query_seed_fallback=query_seed_fallback)
            try:
                page_rank, ranked, graph = ranker.ppr(urls, **seed_kwargs, **rank_kwargs)
            except TypeError as exc:
                # Small compatibility doubles and third-party ranking adapters
                # may not expose the optional MMR keyword yet.
                message = str(exc)
                if ("mmr_enabled" in rank_kwargs and "mmr_enabled" in message):
                    page_rank, ranked, graph = ranker.ppr(urls, **seed_kwargs)
                elif method == "query_entities" and "unexpected keyword argument" in message:
                    # Compatibility adapters can exercise routing without
                    # implementing query-aware seeding; production rankers do.
                    page_rank, ranked, graph = ranker.ppr(urls, seed_method=method)
                else:
                    raise
        else:
            page_rank, ranked = {}, []
            graph = {"nodes": [], "links": [], "meta": {"graph_surviving_articles": 0, "entity_count": 0, "ppr_seed_count": 0, "seed_fallback": "no_candidates"}}
        graph_diagnostics = {**counts, **graph.get("meta", {})}
        fused = fuse_rankings(hybrid, ranked)
        if stage == "compare":
            rankings.extend([
                {**common, "stage": "ppr", "seed_method": method, "ranked": ranked, "diagnostics": graph_diagnostics},
                {**common, "stage": "fused", "seed_method": method, "ranked": fused, "diagnostics": graph_diagnostics},
            ])
        else:
            response.update(page_rank=page_rank, graph=graph, diagnostics=graph_diagnostics)
            response["ranked"] = fused if stage == "fused" or ranking == "fused" else ranked
    if stage == "compare":
        response["rankings"] = rankings
    scores = {entry["article"]: entry["score"] for entry in response["ranked"]}
    total = sum(scores.values())
    response["articles_scores"] = {url: score / total if total else 0.0 for url, score in scores.items()}
    return response


def linear_rank_fusion(textual, graph, graph_mix):
    """Blend normalized rank scores so score scales from each channel do not matter."""
    def normalized(rows):
        values = {row["article"]: max(0.0, float(row.get("score", 0.0))) for row in rows}
        maximum = max(values.values(), default=0.0)
        return {url: score / maximum if maximum else 0.0 for url, score in values.items()}
    text_scores, graph_scores = normalized(textual), normalized(graph)
    urls = set(text_scores) | set(graph_scores)
    return [{"article": url, "score": (1 - graph_mix) * text_scores.get(url, 0.0) + graph_mix * graph_scores.get(url, 0.0)}
            for url in sorted(urls, key=lambda url: (-((1 - graph_mix) * text_scores.get(url, 0.0) + graph_mix * graph_scores.get(url, 0.0)), url))]


_CROSS_ENCODER = None


def _cross_encoder_probabilities(query, results, score_cache=None):
    """Sigmoid-transform cross-encoder logits; return the best probability per article."""
    logits = (_cross_encoder_predict(query, results, score_cache=score_cache)
              if score_cache is not None else _cross_encoder_predict(query, results))
    best = {}
    for row, logit in logits:
        url = row["article_url"]
        best[url] = max(best.get(url, float("-inf")), logit)
    probabilities = {}
    for url, logit in best.items():
        if logit >= 0:
            probabilities[url] = 1.0 / (1.0 + math.exp(-logit))
        else:
            exp_logit = math.exp(logit)
            probabilities[url] = exp_logit / (1.0 + exp_logit)
    return probabilities


def _cross_encoder_rank(query, results, score_cache=None):
    """Optional cross-encoder reranking; loaded lazily from CROSS_ENCODER_MODEL."""
    best = {}
    logits = (_cross_encoder_predict(query, results, score_cache=score_cache)
              if score_cache is not None else _cross_encoder_predict(query, results))
    for row, logit in logits:
        url = row["article_url"]
        best[url] = max(best.get(url, float("-inf")), logit)
    return [{"article": url, "score": score}
            for url, score in sorted(best.items(), key=lambda x: (-x[1], x[0]))]


def _cross_encoder_predict(query, results, score_cache=None):
    """Predict query/chunk logits, reusing scores within one evaluation request."""
    if not results:
        return []
    import os
    model_name = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    global _CROSS_ENCODER

    def cache_key(row):
        return model_name, query, row["article_url"], row["chunk"]

    scores_by_key = {}
    missing = []
    for row in results:
        key = cache_key(row)
        if score_cache is not None and key in score_cache:
            scores_by_key[key] = score_cache[key]
        else:
            missing.append((key, row))

    if missing and _CROSS_ENCODER is None:
        try:
            from sentence_transformers import CrossEncoder
            _CROSS_ENCODER = CrossEncoder(model_name)
        except Exception as exc:
            raise RuntimeError(
                "ranking=cross_encoder requires sentence-transformers and a usable "
                f"CROSS_ENCODER_MODEL ({model_name})"
            ) from exc
    # Only encode uncached pairs. Scores are independent of seed method, so
    # cross_encoder, graph_hits_cross_encoder, and ensemble components can
    # reuse identical logits during this search/evaluation request.
    # Use the highest-ranked retrieved chunk per article as the document text.
    # Explicitly allocate the model's pair-token budget to query and chunk;
    # CrossEncoder.predict also applies model.max_length as a final guard.
    tokenizer = getattr(_CROSS_ENCODER, "tokenizer", None)
    max_length = getattr(_CROSS_ENCODER, "max_length", None)
    pairs = []
    missing_keys = []
    for key, row in missing:
        document = row["chunk"]
        pair_query = query
        if tokenizer is not None and isinstance(max_length, int) and max_length > 0:
            special_tokens = tokenizer.num_special_tokens_to_add(pair=True)
            query_tokens = tokenizer.encode(pair_query, add_special_tokens=False)
            query_budget = max(1, max_length - special_tokens - 1)
            if len(query_tokens) > query_budget:
                query_tokens = query_tokens[:query_budget]
                pair_query = tokenizer.decode(query_tokens, skip_special_tokens=True,
                                              clean_up_tokenization_spaces=False)
            document_budget = max(0, max_length - special_tokens - len(query_tokens))
            document_tokens = (tokenizer.encode(document, add_special_tokens=False,
                                                truncation=True, max_length=document_budget)
                               if document_budget else [])
            document = tokenizer.decode(document_tokens, skip_special_tokens=True,
                                        clean_up_tokenization_spaces=False)
        pairs.append((pair_query, document))
        missing_keys.append(key)
    if pairs:
        scores = _CROSS_ENCODER.predict(pairs)
        for key, score in zip(missing_keys, scores):
            value = float(score)
            scores_by_key[key] = value
            if score_cache is not None:
                score_cache[key] = value
    return [(row, scores_by_key[cache_key(row)]) for row in results]
