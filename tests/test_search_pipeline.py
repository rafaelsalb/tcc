import copy
import math
from types import SimpleNamespace

import pytest

from services.search_pipeline import (CACHE_NAMESPACE, SEARCH_VERSION, SEED_METHODS,
                                     fuse_rankings, reciprocal_rank_fusion, run_pipeline, search_request)


def retrieval():
    return {
        "articles": [], "results": [], "result_unit": "articles", "retrieval_id": "pool-123",
        "ranked": [{"article": "a", "score": 0.9}, {"article": "b", "score": 0.8}],
        "lexical_ranked": [{"article": "c", "score": 0.7}, {"article": "a", "score": 0.4}],
        "vector_ranked": [{"article": "b", "score": 1}, {"article": "a", "score": 2}],
        "lexical_only_ranked": [{"article": "c", "score": 1}, {"article": "a", "score": 2}],
        "diagnostics": {"returned_articles": 2, "returned_chunks": 2, "lexical_returned_chunks": 2,
                        "lexical_candidate_article_urls": ["a", "b", "c"]},
    }


class Ranker:
    def __init__(self):
        self.calls = []

    def ppr(self, urls, seed_method):
        self.calls.append((list(urls), seed_method))
        ranked = [{"article": u, "score": 1 / (i + 1)} for i, u in enumerate(reversed(urls))]
        graph = {
            "nodes": [{"id": url, "label": url, "type": "article", "score": 0.5}
                      for url in urls],
            "links": [],
            "meta": {"graph_surviving_articles": 2, "ppr_seed_count": 1,
                     "seed_method": seed_method},
        }
        return {}, ranked, graph

    def graph_rank(self, urls, method, seed_method, alpha, hop_decay):
        self.graph_call = (method, seed_method, alpha, hop_decay)
        ranked = [{"article": u, "score": float(i + 1)} for i, u in enumerate(urls)]
        graph = {
            "nodes": [{"id": url, "label": url, "type": "article", "score": float(i + 1)}
                      for i, url in enumerate(urls)],
            "links": [], "meta": {"graph_method": method},
        }
        return ranked, graph


class Cache:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl


def test_compare_has_two_baselines_and_two_rows_per_seed_shared_pool_and_no_input_mutation():
    source = retrieval()
    original = copy.deepcopy(source)
    ranker = Ranker()
    result = run_pipeline(source, ranker, "compare")
    assert source == original
    assert result["search_version"] == SEARCH_VERSION
    assert len(result["rankings"]) == 2 + 2 * len(SEED_METHODS)
    assert [method for _, method in ranker.calls] == list(SEED_METHODS)
    assert all(urls == ["a", "b"] for urls, _ in ranker.calls)
    for row in result["rankings"][1:]:
        assert row["retrieval_id"] == "pool-123"
        assert {e["article"] for e in row["ranked"]} == {"a", "b"}
    assert result["graph"]["nodes"]
    assert set(result["graphs_by_seed"]) == set(SEED_METHODS)
    assert all(row["graph"]["nodes"] for row in result["rankings"]
               if row["stage"] in ("ppr", "fused"))
    assert result["rankings"][0]["retrieval_id"] != "pool-123"
    assert "lexical_candidate_article_urls" in result["diagnostics"]
    assert all("lexical_candidate_article_urls" not in row["diagnostics"] for row in result["rankings"])


@pytest.mark.parametrize("stage", ["lexical", "hybrid"])
def test_retrieval_only_stages_never_invoke_graph(stage):
    ranker = Ranker()
    result = run_pipeline(retrieval(), ranker, stage)
    assert not ranker.calls
    assert [e["article"] for e in result["ranked"]] == (["c", "a"] if stage == "lexical" else ["a", "b"])


@pytest.mark.parametrize("ranking", ["hybrid_max", "rrf", "fused", "mmr"])
def test_ranking_options_are_selectable_and_part_of_the_response(ranking):
    ranker = Ranker()
    result = run_pipeline(retrieval(), ranker, "ppr", ranking=ranking, query="short")
    assert result["ranking"] == ranking
    assert {entry["article"] for entry in result["ranked"]} == {"a", "b"}
    assert ("graph" in result) == (ranking in ("fused", "mmr"))


def test_lexical_and_vector_rankings_are_selectable_within_hybrid_pool():
    source = retrieval()
    source["lexical_only_ranked"] = [{"article": x} for x in ("c", "b", "a")]
    source["vector_ranked"] = [{"article": x} for x in ("b", "a", "c")]
    assert [x["article"] for x in run_pipeline(source, Ranker(), ranking="lexical")["ranked"]] == ["b", "a"]
    assert [x["article"] for x in run_pipeline(source, Ranker(), ranking="vector")["ranked"]] == ["b", "a"]


def test_ensemble_rrf_combines_selected_rankings_and_limits_to_hybrid_pool(monkeypatch):
    source = retrieval()
    source["ranked"] = [{"article": x, "score": 1.0} for x in ("a", "b")]
    source["lexical_only_ranked"] = [{"article": x} for x in ("a", "b", "c")]
    source["vector_ranked"] = [{"article": x} for x in ("b", "a", "c")]
    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank", lambda query, rows: [
        {"article": "b", "score": 2.0}, {"article": "a", "score": 1.0}, {"article": "c", "score": 0.0}
    ])
    methods = ("lexical", "vector", "cross_encoder")
    result = run_pipeline(source, Ranker(), ranking="ensemble_rrf", query="short",
                          ensemble_rankings=methods)
    expected = reciprocal_rank_fusion([
        [{"article": "a"}, {"article": "b"}],
        [{"article": "b"}, {"article": "a"}],
        [{"article": "b"}, {"article": "a"}, {"article": "c"}],
    ], candidate_urls={"a", "b"})
    assert result["ranked"] == expected
    assert result["diagnostics"]["ensemble_rankings"] == list(methods)
    assert result["diagnostics"]["ensemble_component_count"] == 3


def test_ensemble_rrf_preserves_graph_component_payload():
    result = run_pipeline(retrieval(), Ranker(), ranking="ensemble_rrf", query="short",
                          ensemble_rankings=("rrf", "ppr"))

    assert result["graph"]["nodes"]
    assert result["graph_source"] == "ppr"
    assert result["diagnostics"]["graph_source_component"] == "ppr"
    assert "ppr" in result["component_graphs"]


@pytest.mark.parametrize("methods", [(), ("ensemble_rrf",), ("unknown",)])
def test_ensemble_rrf_rejects_empty_nested_or_unknown_methods(methods):
    with pytest.raises(ValueError, match="ensemble_rankings"):
        run_pipeline(retrieval(), Ranker(), ranking="ensemble_rrf", ensemble_rankings=methods)


def test_lexical_and_vector_ranking_options_align_channels_to_hybrid_pool():
    source = retrieval()
    source["lexical_only_ranked"] = [{"article": url, "score": rank}
                                     for rank, url in enumerate(("c", "b", "a"), 1)]
    source["vector_ranked"] = [{"article": url, "score": rank}
                               for rank, url in enumerate(("b", "a", "c"), 1)]
    lexical = run_pipeline(source, Ranker(), "ppr", ranking="lexical")["ranked"]
    vector = run_pipeline(source, Ranker(), "ppr", ranking="vector")["ranked"]
    assert [row["article"] for row in lexical] == ["b", "a"]
    assert [row["article"] for row in vector] == ["b", "a"]


def test_graph_independent_ranking_can_opt_in_to_auxiliary_graph_without_changing_ranking():
    source = retrieval()
    ranker = Ranker()
    result = run_pipeline(source, ranker, ranking="lexical", include_graph=True)

    assert [row["article"] for row in result["ranked"]] == ["a"]
    assert result["graph"]["nodes"]
    assert result["graph"]["meta"]["graph_purpose"] == "auxiliary_visualization"
    assert result["graph_source"] == "auxiliary_ppr"
    assert ranker.calls == [(["a"], "hits")]


def test_graph_independent_ranking_does_not_build_graph_by_default():
    ranker = Ranker()
    result = run_pipeline(retrieval(), ranker, ranking="lexical")

    assert "graph" not in result
    assert not ranker.calls


def test_search_request_include_graph_option_is_cacheable_and_configurable():
    cache, ranker = Cache(), Ranker()
    searcher = SimpleNamespace(search=lambda **_: retrieval())
    params = {"query": "short", "ranking": "lexical"}

    with_graph = search_request(searcher, ranker, cache, {**params, "include_graph": "true"})
    without_graph = search_request(searcher, ranker, cache, params)

    assert with_graph["graph"]["meta"]["graph_purpose"] == "auxiliary_visualization"
    assert "graph" not in without_graph
    assert len(ranker.calls) == 1
    assert len([key for key in cache.values if ":response:" in key]) == 2


def test_search_request_accepts_include_graph_function_argument():
    ranker = Ranker()
    response = search_request(
        SimpleNamespace(search=lambda **_: retrieval()), ranker, Cache(),
        {"query": "short", "ranking": "lexical"}, include_graph=True,
    )

    assert response["graph"]["meta"]["graph_purpose"] == "auxiliary_visualization"


def test_ensemble_rrf_combines_selected_methods_and_reports_components(monkeypatch):
    source = retrieval()
    source["lexical_only_ranked"] = [{"article": url, "score": rank}
                                     for rank, url in enumerate(("a", "b", "c"), 1)]
    source["vector_ranked"] = [{"article": url, "score": rank}
                               for rank, url in enumerate(("b", "a", "c"), 1)]
    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank", lambda q, rows: [
        {"article": "b", "score": 2.0}, {"article": "a", "score": 1.0}, {"article": "c", "score": 0.0}
    ])
    components = ("lexical", "vector", "cross_encoder")
    result = run_pipeline(source, Ranker(), "ppr", ranking="ensemble_rrf", query="short",
                          ensemble_rankings=components)
    # Add the cross-encoder list as the third independent rank channel.
    from services.search_pipeline import reciprocal_rank_fusion
    expected = reciprocal_rank_fusion([
        [{"article": "a"}, {"article": "b"}],
        [{"article": "b"}, {"article": "a"}],
        [{"article": "b"}, {"article": "a"}, {"article": "c"}],
    ], candidate_urls={"a", "b"})
    assert result["ranked"] == expected
    assert result["diagnostics"]["ensemble_rankings"] == list(components)
    assert result["diagnostics"]["ensemble_component_count"] == 3
    assert {row["article"] for row in result["ranked"]} == {"a", "b"}


@pytest.mark.parametrize("components", [(), ("ensemble_rrf",), ("not_a_ranking",)])
def test_ensemble_rrf_rejects_empty_nested_or_unknown_components(components):
    with pytest.raises(ValueError, match="ensemble_rankings"):
        run_pipeline(retrieval(), Ranker(), "ppr", ranking="ensemble_rrf", ensemble_rankings=components)


@pytest.mark.parametrize("ranking,method", [
    ("graph_rwr", "rwr"), ("graph_hits", "hits"), ("graph_salsa", "salsa"),
    ("graph_path", "path"), ("graph_walk", "walk"), ("graph_fusion", "hits"),
])
def test_graph_rankings_are_selectable(ranking, method):
    ranker = Ranker()
    result = run_pipeline(retrieval(), ranker, "ppr", ranking=ranking, graph_alpha=0.8,
                          graph_hop_decay=0.4, graph_mix=0.2)
    assert result["ranking"] == ranking
    assert ranker.graph_call == (method, "hits", 0.8, 0.4)
    assert {row["article"] for row in result["ranked"]} == {"a", "b"}
    assert result["graph"]["nodes"]
    assert result["graph"]["meta"]["graph_method"] == method
    if ranking == "graph_fusion":
        assert result["diagnostics"]["graph_fusion_method"] == "rrf"
        assert result["diagnostics"]["graph_fusion_rrf_k"] == 60
        assert "graph_mix" not in result["diagnostics"]


def test_graph_hits_cross_encoder_reranks_only_top_250_and_preserves_tail(monkeypatch):
    hybrid = [{"article": f"article-{i}", "score": 1.0} for i in range(260)]
    rows = [{"article_url": f"article-{i}", "chunk": f"chunk-{i}"} for i in range(260)]
    captured = {}

    def probabilities(query, candidates):
        captured["query"] = query
        captured["chunks"] = [row["chunk"] for row in candidates]
        return {row["article_url"]: (i + 1) / 250 for i, row in enumerate(candidates)}

    def graph_hits(candidates, **kwargs):
        captured["candidate_count"] = len(candidates)
        captured["fallback_seed_method"] = kwargs["fallback_seed_method"]
        return [{"article": url, "score": 1.0} for url in reversed(candidates)], {
            "meta": {"query_entity_count": 1, "query_entity_matched_count": 1,
                     "query_seed_fallback_reason": None, "query_seed_type": "entity"}}

    monkeypatch.setattr("services.search_pipeline._cross_encoder_probabilities", probabilities)
    ranker = Ranker()
    ranker.graph_hits_cross_encoder = graph_hits
    result = run_pipeline({"ranked": hybrid, "results": rows}, ranker, "ppr",
                          ranking="graph_hits_cross_encoder", query="query", seed_method="louvain")
    assert captured == {"query": "query", "chunks": [f"chunk-{i}" for i in range(250)],
                        "candidate_count": 250, "fallback_seed_method": "louvain"}
    assert [row["article"] for row in result["ranked"][:250]] == [f"article-{i}" for i in reversed(range(250))]
    assert [row["article"] for row in result["ranked"][250:]] == [f"article-{i}" for i in range(250, 260)]
    assert result["diagnostics"]["cross_encoder_candidate_cutoff"] == 250


def test_rrf_uses_provided_lexical_and_vector_order_and_never_substitutes_hybrid():
    source = retrieval()
    source.update(
        ranked=[{"article": url, "score": 1.0} for url in ("b", "a", "c")],
        lexical_only_ranked=[{"article": url, "score": rank} for rank, url in enumerate(("a", "b", "c"), 1)],
        vector_ranked=[{"article": url, "score": rank} for rank, url in enumerate(("c", "b", "a"), 1)],
    )
    result = run_pipeline(source, Ranker(), "ppr", ranking="rrf", query="short")
    assert [row["article"] for row in result["ranked"]] == ["a", "c", "b"]

    source["vector_ranked"] = []
    source["lexical_only_ranked"] = []
    source["lexical_ranked"] = []
    result = run_pipeline(source, Ranker(), "ppr", ranking="rrf", query="short")
    assert result["ranked"] == []


def test_cross_encoder_option_is_lazy_and_reports_missing_runtime(monkeypatch):
    import sys

    monkeypatch.setenv("CROSS_ENCODER_MODEL", "missing-test-model")
    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    source = retrieval()
    source["results"] = [{"article_url": "a", "article_title": "A", "chunk": "text"}]
    with pytest.raises(RuntimeError, match="cross_encoder"):
        run_pipeline(source, Ranker(), "ppr", ranking="cross_encoder", query="short")


def test_empty_cross_encoder_input_never_loads_or_calls_model(monkeypatch):
    import sys
    from services.search_pipeline import _cross_encoder_rank

    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert _cross_encoder_rank("test", []) == []

    class Model:
        def predict(self, pairs):
            pytest.fail("empty input must not call predict")

    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", Model())
    assert _cross_encoder_rank("test", []) == []


@pytest.mark.parametrize("empty_pool", [False, True])
def test_cross_encoder_empty_or_missing_documents(monkeypatch, empty_pool):
    import sys

    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    source = retrieval()
    if empty_pool:
        source["ranked"] = []
    result = run_pipeline(source, Ranker(), "ppr", ranking="cross_encoder", query="test")
    assert result["ranked"] == source["ranked"]
    assert result["diagnostics"]["cross_encoder_reranked_count"] == 0
    assert result["diagnostics"]["cross_encoder_missing_document_count"] == (0 if empty_pool else 2)


def test_cross_encoder_predict_reuses_pair_logits_within_request(monkeypatch):
    from services import search_pipeline

    class FakeModel:
        tokenizer = None
        max_length = None

        def __init__(self):
            self.calls = []

        def predict(self, pairs):
            self.calls.append(list(pairs))
            return [float(len(self.calls) * 10 + index) for index, _ in enumerate(pairs)]

    model = FakeModel()
    monkeypatch.setattr(search_pipeline, "_CROSS_ENCODER", model)
    cache = {}
    first_rows = [
        {"article_url": "a", "chunk": "chunk a"},
        {"article_url": "b", "chunk": "chunk b"},
    ]
    first = search_pipeline._cross_encoder_predict("query", first_rows, score_cache=cache)
    repeated = search_pipeline._cross_encoder_predict(
        "query", [dict(row) for row in first_rows], score_cache=cache,
    )
    partial = search_pipeline._cross_encoder_predict(
        "query", [dict(first_rows[1]), {"article_url": "c", "chunk": "chunk c"}],
        score_cache=cache,
    )
    assert len(model.calls) == 2
    assert [len(call) for call in model.calls] == [2, 1]
    assert [score for _, score in first] == [10.0, 11.0]
    assert [score for _, score in repeated] == [10.0, 11.0]
    assert [score for _, score in partial] == [11.0, 20.0]


def test_cross_encoder_reranks_only_first_fifty_and_preserves_the_tail(monkeypatch):
    hybrid = [{"article": f"article-{i}", "score": 1 / (i + 1)} for i in range(275)]
    results = [
        {"article_url": f"article-{i}", "article_title": f"Article {i}", "chunk": f"chunk {i}"}
        for i in range(275)
    ]
    retrieval_data = {"ranked": hybrid, "lexical_ranked": [], "vector_ranked": [], "results": results,
                      "diagnostics": {}, "result_unit": "articles", "retrieval_id": "pool"}
    captured = {}

    def fake_cross_encoder(query, candidates):
        captured["query"] = query
        captured["count"] = len(candidates)
        captured["chunks"] = [row["chunk"] for row in candidates]
        return [{"article": row["article_url"], "score": 1.0} for row in reversed(candidates)]

    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank", fake_cross_encoder)
    result = run_pipeline(retrieval_data, Ranker(), "ppr", ranking="cross_encoder", query="test")
    assert captured["query"] == "test"
    assert captured["count"] == 250
    assert captured["chunks"] == [f"chunk {i}" for i in range(250)]
    assert [entry["article"] for entry in result["ranked"][:250]] == [f"article-{i}" for i in reversed(range(250))]
    assert [entry["article"] for entry in result["ranked"][250:]] == [f"article-{i}" for i in range(250, 275)]
    assert result["diagnostics"]["cross_encoder_reranked_count"] == 250


def test_cross_encoder_uses_first_ranked_chunk_once_per_article(monkeypatch):
    hybrid = [{"article": f"article-{i}", "score": 1.0} for i in range(251)]
    results = [{"article_url": "article-0", "article_title": "Do not use title", "chunk": "first chunk"},
               {"article_url": "article-0", "article_title": "Do not use title", "chunk": "second chunk"}]
    results.extend({"article_url": f"article-{i}", "article_title": "unused", "chunk": f"text {i}"}
                   for i in range(1, 250))
    captured = []
    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank",
                        lambda query, candidates: captured.extend(candidates) or
                        [{"article": row["article_url"], "score": 1.0} for row in candidates])
    response = run_pipeline({"ranked": hybrid, "results": results}, Ranker(), "ppr",
                            ranking="cross_encoder", query="query")
    assert len(captured) == 250
    assert captured[0]["chunk"] == "first chunk"
    assert len({row["article_url"] for row in captured}) == 250
    assert response["diagnostics"]["cross_encoder_reranked_count"] == 250
    assert response["diagnostics"]["cross_encoder_missing_document_count"] == 0


def test_cross_encoder_truncates_chunk_to_remaining_pair_context(monkeypatch):
    from services.search_pipeline import _cross_encoder_rank

    class Tokenizer:
        model_max_length = 10

        @staticmethod
        def num_special_tokens_to_add(pair):
            assert pair is True
            return 3

        @staticmethod
        def encode(text, add_special_tokens=False, truncation=False, max_length=None):
            tokens = text.split()
            return tokens[:max_length] if truncation else tokens

        @staticmethod
        def decode(tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False):
            return " ".join(tokens)

    class Model:
        tokenizer = Tokenizer()
        max_length = 10

        def predict(self, pairs):
            self.pairs = pairs
            return [1.0]

    model = Model()
    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", model)
    rows = [{"article_url": "a", "chunk": "one two three four five six seven eight nine ten"}]
    assert _cross_encoder_rank("query words", rows) == [{"article": "a", "score": 1.0}]
    # 10 max tokens - 3 pair-special tokens - 2 query tokens = 5 chunk tokens.
    assert model.pairs == [("query words", "one two three four five")]


def test_cross_encoder_probabilities_apply_sigmoid_to_logits(monkeypatch):
    from services.search_pipeline import _cross_encoder_probabilities

    monkeypatch.setattr("services.search_pipeline._cross_encoder_predict", lambda query, rows: [
        (rows[0], 0.0), (rows[1], 2.0), (rows[2], -2.0),
    ])
    rows = [{"article_url": url} for url in ("zero", "positive", "negative")]
    probabilities = _cross_encoder_probabilities("query", rows)
    assert probabilities["zero"] == pytest.approx(0.5)
    assert probabilities["positive"] == pytest.approx(1 / (1 + math.exp(-2)))
    assert probabilities["negative"] == pytest.approx(1 / (1 + math.exp(2)))


def test_graph_hits_cross_encoder_limits_to_250_and_preserves_hybrid_tail(monkeypatch):
    hybrid = [{"article": f"article-{i}", "score": 1 / (i + 1)} for i in range(260)]
    results = [{"article_url": f"article-{i}", "chunk": f"chunk-{i}"} for i in range(260)]
    captured = {}

    def probabilities(query, candidates):
        captured["query"] = query
        captured["chunks"] = [row["chunk"] for row in candidates]
        return {row["article_url"]: (i + 1) / 250 for i, row in enumerate(candidates)}

    def hits(candidates, **kwargs):
        captured["candidate_count"] = len(candidates)
        captured["fallback"] = kwargs["fallback_seed_method"]
        return [{"article": url, "score": 1.0} for url in reversed(candidates)], {
            "meta": {"query_entity_count": 1, "query_entity_matched_count": 1,
                     "query_seed_fallback_reason": None, "query_seed_type": "entity"}}

    monkeypatch.setattr("services.search_pipeline._cross_encoder_probabilities", probabilities)
    ranker = Ranker()
    ranker.graph_hits_cross_encoder = hits
    result = run_pipeline({"ranked": hybrid, "results": results}, ranker, "ppr",
                          ranking="graph_hits_cross_encoder", query="query",
                          seed_method="louvain")
    assert captured["query"] == "query"
    assert captured["chunks"] == [f"chunk-{i}" for i in range(250)]
    assert captured["candidate_count"] == 250
    assert captured["fallback"] == "louvain"
    assert [row["article"] for row in result["ranked"][:250]] == [f"article-{i}" for i in reversed(range(250))]
    assert [row["article"] for row in result["ranked"][250:]] == [f"article-{i}" for i in range(250, 260)]
    assert result["diagnostics"]["cross_encoder_candidate_cutoff"] == 250


def test_cross_encoder_reranks_entire_short_pool(monkeypatch):
    retrieval_data = retrieval()
    retrieval_data["results"] = [
        {"article_url": "a", "article_title": "A", "chunk": "a"},
        {"article_url": "b", "article_title": "B", "chunk": "b"},
    ]
    captured = []
    monkeypatch.setattr(
        "services.search_pipeline._cross_encoder_rank",
        lambda query, candidates: captured.append(len(candidates)) or [
            {"article": row["article_url"], "score": 1.0} for row in candidates
        ],
    )
    result = run_pipeline(retrieval_data, Ranker(), "ppr", ranking="cross_encoder", query="test")
    assert captured == [2]
    assert result["diagnostics"]["cross_encoder_reranked_count"] == 2


def test_invalid_ranking_is_rejected_before_retrieval():
    with pytest.raises(ValueError, match="invalid ranking"):
        search_request(None, None, Cache(), {"query": "short", "ranking": "llm"})


def test_empty_compare_returns_all_rows_without_graph_calls():
    source = retrieval()
    source.update(ranked=[], lexical_ranked=[])
    ranker = Ranker()
    result = run_pipeline(source, ranker, "compare")
    assert not ranker.calls
    assert len(result["rankings"]) == 2 + 2 * len(SEED_METHODS)
    assert all(not row["ranked"] for row in result["rankings"])


def test_fusion_preserves_pool_and_deduplicates_each_ranking():
    a = [{"article": "a"}, {"article": "a"}, {"article": "b"}]
    b = [{"article": "b"}, {"article": "a"}]
    ranked = fuse_rankings(a, b)
    assert [e["article"] for e in ranked] == ["a", "b"]  # Equal RRF, deterministic tie.
    assert ranked[0]["score"] == pytest.approx(1 / 61 + 1 / 62)


def test_api_reuses_retrieval_across_stages_and_seeds_but_not_units():
    calls = []

    def search(**settings):
        calls.append(settings)
        return retrieval()

    cache, ranker = Cache(), Ranker()
    searcher = SimpleNamespace(search=search)
    params = {"query": "short", "result_unit": "articles"}
    search_request(searcher, ranker, cache, {**params, "stage": "hybrid"})
    assert len(calls) == 1 and not ranker.calls
    search_request(searcher, ranker, cache, {**params, "seed_method": "ppr_top10"})
    assert len(calls) == 1 and len(ranker.calls) == 1
    search_request(searcher, ranker, cache, {**params, "seed_method": "ppr_top10"})
    assert len(ranker.calls) == 1  # Response cache, no graph recomputation.
    search_request(searcher, ranker, cache, {**params, "stage": "compare"})
    assert len(calls) == 1
    search_request(searcher, ranker, cache, {**params, "result_unit": "chunks"})
    assert len(calls) == 2
    search_request(searcher, ranker, cache, {**params, "stage": "lexical"})
    assert len(calls) == 3 and calls[-1]["retrieval_stage"] == "lexical"
    assert all(key.startswith(f"search_cache:{CACHE_NAMESPACE}:{SEARCH_VERSION}:") for key in cache.values)


def test_ranking_is_not_forwarded_to_search_service():
    received = []

    def search(**settings):
        received.append(settings)
        return retrieval()

    search_request(
        SimpleNamespace(search=search), Ranker(), Cache(),
        {"query": "short", "ranking": "hybrid_max"},
    )

    assert received
    assert "ranking" not in received[0]


def test_graph_query_parameters_reach_ranker_and_separate_response_cache_entries():
    cache, ranker = Cache(), Ranker()
    searcher = SimpleNamespace(search=lambda **_: retrieval())
    for mix in (0.2, 0.7):
        search_request(searcher, ranker, cache, {
            "query": "short", "ranking": "graph_fusion", "graph_alpha": "0.75",
            "graph_hop_decay": "0.4", "graph_mix": str(mix),
        })
        assert ranker.graph_call == ("hits", "hits", 0.75, 0.4)
    response_keys = [key for key in cache.values if ":response:" in key]
    assert len(response_keys) == 2


@pytest.mark.parametrize("stage", ["lexical", "hybrid", "ppr", "fused", "compare"])
@pytest.mark.parametrize("value", ["true", "1", True])
def test_bypass_never_reads_or_writes_redis_and_recomputes_each_request(stage, value):
    class NoCacheAccess:
        def get(self, *args):
            pytest.fail("bypassed request must not read Redis")

        def setex(self, *args):
            pytest.fail("bypassed request must not write Redis")

    calls = []

    def search(**settings):
        calls.append(settings)
        return retrieval()

    ranker = Ranker()
    params = {"query": "short", "stage": stage, "bypass_cache": value}
    for _ in range(2):
        result = search_request(SimpleNamespace(search=search), ranker, NoCacheAccess(), params)
        assert result["cache_bypassed"] is True
        assert result["search_version"] == SEARCH_VERSION
    assert len(calls) == 2
    expected_graph_calls = 2 * len(SEED_METHODS) if stage == "compare" else 2 if stage in ("ppr", "fused") else 0
    assert len(ranker.calls) == expected_graph_calls


def test_bypass_does_not_overwrite_existing_cached_results():
    cache, ranker = Cache(), Ranker()
    calls = []

    def search(**settings):
        calls.append(settings)
        value = retrieval()
        value["retrieval_id"] = f"pool-{len(calls)}"
        return value

    searcher = SimpleNamespace(search=search)
    first = search_request(searcher, ranker, cache, {"query": "short"})
    before = dict(cache.values)
    fresh = search_request(searcher, ranker, cache, {"query": "short", "bypass_cache": "true"})
    assert fresh["retrieval_id"] != first["retrieval_id"]
    assert cache.values == before
    cached = search_request(searcher, ranker, cache, {"query": "short", "bypass_cache": "false"})
    assert cached == first and cached["cache_bypassed"] is False
    assert len(calls) == 2


def test_search_version_is_part_of_cache_namespace(monkeypatch):
    calls = []

    def search(**settings):
        calls.append(settings)
        return retrieval()

    cache = Cache()
    searcher = SimpleNamespace(search=search)
    search_request(searcher, Ranker(), cache, {"query": "short", "stage": "hybrid"})
    monkeypatch.setattr("services.search_pipeline.SEARCH_VERSION", "future_version")
    search_request(searcher, Ranker(), cache, {"query": "short", "stage": "hybrid"})
    assert len(calls) == 2


@pytest.mark.parametrize("extra", [
    {"stage": "bad"}, {"seed_method": "hits_top10"}, {"result_unit": "bad"},
    {"top_k": "0"}, {"limit": "-1"}, {"offset": "-2"}, {"candidate_cap": "0"},
    {"quorum": "nan"}, {"quorum": "1.1"}, {"seed_methods": "hits,bad"},
    {"date_from": "not-a-date"}, {"date_from": "2026-01-01", "date_to": "2025-01-01"},
    {"top_k": 0}, {"candidate_cap": 0},
    {"bypass_cache": "maybe"},
    {"graph_alpha": "1"}, {"graph_hop_decay": "-0.1"}, {"graph_mix": "1.1"},
    {"include_graph": "maybe"},
])
def test_api_rejects_invalid_options_before_work(extra):
    with pytest.raises(ValueError):
        search_request(None, None, Cache(), {"query": "short", **extra})
