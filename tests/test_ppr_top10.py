import math
from types import SimpleNamespace

import pytest

from services.ranking import RankingService


def test_entity_seeds_use_normalized_initial_pr_not_raw_pr_or_article_scores():
    scores = {"article": 100, "entity:a": 0.4, "entity:b": 0.2}
    counts = {"article": 1, "entity:a": 100, "entity:b": 1}
    assert RankingService._ppr_top10_seeds(scores, {"article"}, counts) == {"entity:b"}


@pytest.mark.parametrize("count", [0, 1, 9, 10, 11, 19, 20, 21])
def test_top_decile_rounds_up_and_breaks_ties_by_identity(count):
    names = [f"entity:{i:03d}" for i in range(count)]
    scores = {name: 1.0 for name in reversed(names)}
    seeds = RankingService._ppr_top10_seeds(scores, set(), {name: 2 for name in names})
    assert seeds == set(names[:math.ceil(count / 10)])


def make_ranker(entity_count):
    articles = [SimpleNamespace(url="article-a", title="a"), SimpleNamespace(url="article-b", title="b")]
    entities = [SimpleNamespace(text_=f"Pessoa {i:02d}", canonical=None) for i in range(entity_count)]
    repository = SimpleNamespace(get_all=lambda **kwargs: articles)
    ner = SimpleNamespace(
        entity_repository=None,
        batch_get_or_extract_entities_and_store_for_articles=lambda *args, **kwargs: {
            article.url: entities for article in articles
        },
    )
    return RankingService(repository, ner)


def test_actual_graph_gives_top_entities_equal_weight_every_other_node_zero(monkeypatch):
    monkeypatch.setattr("services.ranking.nx.hits", lambda *args, **kwargs: pytest.fail("ppr_top10 must not use HITS"))
    service = make_ranker(11)
    _, ranked, graph = service.ppr(["article-a", "article-b"], seed_method="ppr_top10")
    seeds = [node for node in graph["nodes"] if node["ppr_seed"]]
    assert len(seeds) == 2
    assert all(node["type"] == "entity" and node["personalization"] == 0.5 for node in seeds)
    assert all(node["personalization"] == 0 for node in graph["nodes"] if not node["ppr_seed"])
    assert graph["meta"]["seed_fallback"] is None
    assert {e["article"] for e in ranked} == {"article-a", "article-b"}


def test_no_entities_keeps_articles_and_reports_uniform_article_fallback():
    _, ranked, graph = make_ranker(0).ppr(["article-a", "article-b"], seed_method="ppr_top10")
    assert graph["meta"]["seed_fallback"] == "no_surviving_entities"
    assert graph["meta"]["ppr_seed_count"] == 0
    assert all(node["personalization"] == 0.5 for node in graph["nodes"])
    assert len(ranked) == 2
    assert all(entry["score"] == pytest.approx(0.5) for entry in ranked)


def test_mmr_changes_final_article_order_when_redundancy_penalty_applies():
    service = make_ranker(11)
    _, ppr_ranked, _ = service.ppr(["article-a", "article-b"], seed_method="ppr_top10")
    _, mmr_ranked, _ = service.ppr(
        ["article-a", "article-b"], seed_method="ppr_top10", mmr_enabled=True,
        mmr_lambda=1.0,
    )
    assert {entry["article"] for entry in ppr_ranked} == {"article-a", "article-b"}
    assert {entry["article"] for entry in mmr_ranked} == {"article-a", "article-b"}


@pytest.mark.parametrize("method", ["louvain", "hits", "ppr_top10"])
def test_each_graph_method_retains_all_input_articles(method):
    _, ranked, graph = make_ranker(11).ppr(["article-a", "article-b"], seed_method=method)
    assert {entry["article"] for entry in ranked} == {"article-a", "article-b"}
    assert graph["meta"]["seed_method"] == method
    assert sum(n["personalization"] for n in graph["nodes"]) == pytest.approx(1.0)


def make_query_ranker(article_entities, query_entities):
    urls = [f"article-{i}" for i in range(3)]
    articles = [SimpleNamespace(url=url, title=url) for url in urls]
    ner = SimpleNamespace(
        entity_repository=None,
        batch_get_or_extract_entities_and_store_for_articles=lambda requested, **kwargs: {
            url: [SimpleNamespace(text_=text, canonical=canonical)
                  for text, canonical in article_entities.get(url, [])]
            for url in requested
        },
        extract_entities=lambda query: query_entities,
    )
    return RankingService(SimpleNamespace(get_all=lambda **kwargs: articles), ner), urls


def test_query_entities_seed_matches_canonical_graph_entity():
    common = [(f"Shared {i}", None) for i in range(12)]
    articles = {f"article-{i}": [*common, ("President", "http://dbpedia.org/resource/Query_Person")]
                for i in range(3)}
    query_entities = [{"text": "A person alias", "canonical": "http://dbpedia.org/resource/Query_Person", "label": "PER"}]
    ranker, urls = make_query_ranker(articles, query_entities)
    _, ranked, graph = ranker.ppr(urls, seed_method="query_entities", query="who")
    seeds = [node for node in graph["nodes"] if node["ppr_seed"]]
    assert [node["id"] for node in seeds] == ["entity:http://dbpedia.org/resource/Query_Person"]
    assert graph["meta"]["effective_seed_method"] == "query_entities"
    assert graph["meta"]["query_entity_count"] == graph["meta"]["query_entity_matched_count"] == 1
    assert graph["meta"]["query_seed_fallback_reason"] is None
    assert {row["article"] for row in ranked} == set(urls)


def test_query_entity_pruned_from_core_seeds_its_surviving_article_neighbors():
    common = [(f"Shared {i}", None) for i in range(12)]
    articles = {"article-0": [*common, ("Rare query entity", None)],
                "article-1": common, "article-2": common}
    query_entities = [{"text": "Rare query entity", "canonical": None, "label": "ORG"}]
    ranker, urls = make_query_ranker(articles, query_entities)
    _, _, graph = ranker.ppr(urls, seed_method="query_entities", query="rare")
    seeds = [node for node in graph["nodes"] if node["ppr_seed"]]
    assert [node["id"] for node in seeds] == ["article-0"]
    assert seeds[0]["personalization"] == pytest.approx(1.0)
    assert graph["meta"]["query_entity_count"] == graph["meta"]["query_entity_matched_count"] == 1
    assert graph["meta"]["query_seed_type"] == "article"
    assert graph["meta"]["query_seed_fallback_reason"] == "matched_entities_pruned_to_articles"


def test_unmatched_query_entities_fall_back_to_configured_existing_seed_method():
    ranker, urls = make_query_ranker(
        {f"article-{i}": [(f"Shared {j}", None) for j in range(12)] for i in range(3)},
        [{"text": "Absent person", "canonical": "http://dbpedia.org/resource/Absent", "label": "PER"}],
    )
    _, _, graph = ranker.ppr(urls, seed_method="query_entities", query="absent", query_seed_fallback="louvain")
    assert graph["meta"]["seed_method"] == "query_entities"
    assert graph["meta"]["effective_seed_method"] == "louvain"
    assert graph["meta"]["query_entity_count"] == 1
    assert graph["meta"]["query_entity_matched_count"] == 0
    assert graph["meta"]["query_seed_fallback_reason"] == "no_graph_match"


def test_query_entities_without_named_entities_falls_back_to_hits():
    ranker, urls = make_query_ranker(
        {f"article-{i}": [(f"Shared {j}", None) for j in range(12)] for i in range(3)}, [],
    )
    _, _, graph = ranker.ppr(urls, seed_method="query_entities", query="generic words")
    assert graph["meta"]["effective_seed_method"] == "hits"
    assert graph["meta"]["query_entity_count"] == 0
    assert graph["meta"]["query_seed_fallback_reason"] == "no_query_entities"


def test_query_seed_rejects_invalid_legacy_fallback():
    ranker, urls = make_query_ranker({}, [])
    with pytest.raises(ValueError, match="query_seed_fallback"):
        ranker.ppr(urls, seed_method="query_entities", query="x", query_seed_fallback="query_entities")


def test_weighted_query_entity_hits_orders_articles_by_cross_encoder_probability():
    common = [(f"Shared {i}", None) for i in range(12)]
    articles = {f"article-{i}": [*common, ("Query organisation", None)] for i in range(3)}
    query_entities = [{"text": "Query organisation", "canonical": None, "label": "ORG"}]
    ranker, urls = make_query_ranker(articles, query_entities)
    ranked, graph = ranker.graph_hits_cross_encoder(
        urls, query="Query organisation",
        article_probabilities={"article-0": 0.1, "article-1": 0.9, "article-2": 0.5},
    )
    assert [row["article"] for row in ranked] == ["article-1", "article-2", "article-0"]
    assert graph["meta"]["graph_method"] == "hits_cross_encoder"
    assert graph["meta"]["query_entity_count"] == graph["meta"]["query_entity_matched_count"] == 1
    assert graph["meta"]["cross_encoder_probability_count"] == 3
    assert graph["meta"]["query_seed_fallback_reason"] is None


def test_weighted_query_entity_hits_reports_legacy_fallback_when_no_match():
    articles = {f"article-{i}": [(f"Shared {j}", None) for j in range(12)] for i in range(3)}
    ranker, urls = make_query_ranker(articles, [])
    ranked, graph = ranker.graph_hits_cross_encoder(
        urls, query="No named entity", article_probabilities={url: 0.5 for url in urls},
        fallback_seed_method="louvain",
    )
    assert {row["article"] for row in ranked} == set(urls)
    assert graph["meta"]["graph_method"] == "hits_cross_encoder_fallback"
    assert graph["meta"]["effective_seed_method"] == "louvain"
    assert graph["meta"]["query_seed_fallback_reason"] == "no_query_entities"


def test_cross_encoder_probability_weights_query_entity_hits():
    common = [(f"Shared {i}", None) for i in range(12)]
    articles = {f"article-{i}": [*common, ("Query organisation", None)] for i in range(3)}
    query_entities = [{"text": "Query organisation", "canonical": None, "label": "ORG"}]
    ranker, urls = make_query_ranker(articles, query_entities)
    ranked, graph = ranker.graph_hits_cross_encoder(
        urls, query="Query organisation",
        article_probabilities={"article-0": 0.1, "article-1": 0.9, "article-2": 0.5},
    )
    assert [row["article"] for row in ranked] == ["article-1", "article-2", "article-0"]
    assert graph["meta"]["graph_method"] == "hits_cross_encoder"
    assert graph["meta"]["query_entity_matched_count"] == 1
    assert graph["meta"]["cross_encoder_probability_count"] == 3


def test_cross_encoder_graph_falls_back_when_query_has_no_graph_entity():
    articles = {f"article-{i}": [(f"Shared {j}", None) for j in range(12)] for i in range(3)}
    ranker, urls = make_query_ranker(articles, [])
    ranked, graph = ranker.graph_hits_cross_encoder(
        urls, query="generic query", article_probabilities={url: 0.5 for url in urls},
        fallback_seed_method="louvain",
    )
    assert {row["article"] for row in ranked} == set(urls)
    assert graph["meta"]["graph_method"] == "hits_cross_encoder_fallback"
    assert graph["meta"]["query_seed_fallback_reason"] == "no_query_entities"


@pytest.mark.parametrize("method", ["rwr", "hits", "salsa", "path", "walk"])
def test_graph_rank_methods_return_finite_scores_for_candidate_pool(method):
    import networkx as nx

    # "pruned" is still a retrieval candidate, but k-core may remove it from G.
    urls = ["a", "b", "c", "pruned"]
    graph = nx.DiGraph()
    for entity, article in (("entity:seed", "a"), ("entity:seed", "b"),
                            ("entity:other", "b"), ("entity:other", "c")):
        graph.add_edge(entity, article)
        graph.add_edge(article, entity)
    prepared = {"G": graph, "original_graph": graph, "seed_fallback": None}
    service = object.__new__(RankingService)
    service._prepare_graph = lambda _: prepared
    service._ppr_inputs = lambda *args: {
        "top_entity_ids": {"entity:seed"}, "personalization": {"entity:seed": 1.0},
    }
    ranked, diagnostics = service.graph_rank(urls, method=method)
    assert {row["article"] for row in ranked} == set(urls)
    assert all(math.isfinite(row["score"]) and row["score"] >= 0 for row in ranked)
    assert next(row["score"] for row in ranked if row["article"] == "pruned") == 0.0
    assert diagnostics["meta"]["graph_method"] == method
