import csv
import json
import math
from urllib.parse import parse_qs, urlsplit

import pytest

import services.batch_evaluation as batch_evaluation
from services.batch_evaluation import validate_document


def valid_document():
    return {
        "schema_version": 1,
        "evaluations": [{
            "id": "eval-1",
            "query": "consulta de teste",
            "relevant_urls": [f"https://g1.globo.com/artigo/{i}" for i in range(10)],
        }],
    }


@pytest.mark.parametrize("count", [1, 2, 3, 5, 9, 10, 11, 20, 21, 50])
def test_validate_document_accepts_any_positive_number_of_relevant_urls(count):
    document = valid_document()
    urls = [f"https://g1.globo.com/artigo/{i}" for i in reversed(range(count))]
    document["evaluations"][0]["relevant_urls"] = urls

    evaluations = validate_document(document)

    assert len(evaluations) == 1
    assert evaluations[0]["relevant_urls"] == urls


@pytest.mark.parametrize("urls", [[], None, "https://g1.globo.com/artigo/1", {}])
def test_validate_document_requires_a_non_empty_relevant_url_list(urls):
    document = valid_document()
    document["evaluations"][0]["relevant_urls"] = urls

    with pytest.raises(ValueError, match="non-empty array"):
        validate_document(document)


def test_validate_document_rejects_duplicate_relevant_urls():
    document = valid_document()
    document["evaluations"][0]["relevant_urls"][-1] = document["evaluations"][0]["relevant_urls"][0]

    with pytest.raises(ValueError, match="unique URLs"):
        validate_document(document)


def test_validate_document_rejects_unknown_fields():
    document = valid_document()
    document["evaluations"][0]["extra"] = True

    with pytest.raises(ValueError, match="keys must be exactly"):
        validate_document(document)


def test_search_endpoint_url_uses_preset_date_range_and_seed_method():
    url = batch_evaluation._search_endpoint_url(
        "http://localhost:5000",
        "investigações & economia",
        batch_evaluation.SEARCH_PRESETS["balanceado"],
        "hits",
        0.7,
    )
    parsed = urlsplit(url)

    assert parsed.path == "/search"
    assert parse_qs(parsed.query) == {
        "query": ["investigações & economia"],
        "limit": ["1000"],
        "top_k": ["500"],
        "offset": ["0"],
        "seed_method": ["hits"],
        "quorum": ["0.7"],
        "date_from": ["2025-06-01"],
        "date_to": ["2026-06-30"],
        "stage": ["ppr"],
        "result_unit": ["chunks"],
        "bypass_cache": ["true"],
        "query_seed_fallback": ["hits"],
    }


def test_ensemble_method_components_are_encoded_on_api_request():
    url = batch_evaluation._search_endpoint_url(
        "http://localhost:5000", "consulta", {"limit": 20, "top_k": 10}, "hits", 0.7,
        ranking="ensemble_rrf", ensemble_rankings=("lexical", "vector", "ppr"),
    )
    assert parse_qs(urlsplit(url).query)["ensemble_rankings"] == ["lexical,vector,ppr"]


def test_batch_presets_have_expected_paired_search_depth():
    assert batch_evaluation.SEARCH_PRESETS == {
        "rapido": {"limit": 1000, "top_k": 250},
        "balanceado": {"limit": 1000, "top_k": 500},
        "profundo": {"limit": 1000, "top_k": 1000},
    }


@pytest.mark.parametrize("stage", ["lexical", "hybrid", "ppr", "fused", "compare"])
@pytest.mark.parametrize("unit", ["chunks", "articles"])
def test_batch_requests_always_bypass_cache_for_every_stage_and_unit(stage, unit):
    url = batch_evaluation._search_endpoint_url(
        "http://localhost:5000", "query", {"limit": 40, "top_k": 10}, "ppr_top10", 0.7,
        stage=stage, result_unit=unit, seed_methods=("hits", "ppr_top10"),
    )
    params = parse_qs(urlsplit(url).query)
    assert params["bypass_cache"] == ["true"]
    assert params["stage"] == [stage] and params["result_unit"] == [unit]


def test_seed_methods_include_louvain_and_hits():
    assert batch_evaluation.SEED_METHODS == ("louvain", "hits", "ppr_top10", "query_entities")
    assert batch_evaluation.QUORUM_VALUES == (0.3, 0.5, 0.7, 0.9)


def test_ranked_urls_are_read_from_api_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"search_version": batch_evaluation.SEARCH_VERSION, "cache_bypassed": True,
                               "ranked": [{"article": "https://g1.globo.com/a", "score": 0.25}, {}]}).encode()

    monkeypatch.setattr(batch_evaluation, "urlopen", lambda *args, **kwargs: FakeResponse())

    assert batch_evaluation._ranked_urls_from_api(
        "http://localhost:5000",
        "query",
        batch_evaluation.SEARCH_PRESETS["balanceado"],
        "louvain",
        0.7,
    ) == ["https://g1.globo.com/a"]


def test_ranked_urls_are_empty_when_api_returns_no_ranked_results(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"search_version": batch_evaluation.SEARCH_VERSION, "cache_bypassed": True,
                               "articles": [], "total": 0}).encode()

    monkeypatch.setattr(batch_evaluation, "urlopen", lambda *args, **kwargs: FakeResponse())

    assert batch_evaluation._ranked_urls_from_api(
        "http://localhost:5000",
        "query",
        batch_evaluation.SEARCH_PRESETS["balanceado"],
        "louvain",
        0.7,
    ) == []


@pytest.mark.parametrize("confirmation", [None, False, "true"])
def test_batch_rejects_api_response_without_real_cache_bypass(monkeypatch, confirmation):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"search_version": batch_evaluation.SEARCH_VERSION,
                               "cache_bypassed": confirmation, "ranked": []}).encode()

    def request(req, **kwargs):
        assert parse_qs(urlsplit(req.full_url).query)["bypass_cache"] == ["true"]
        return FakeResponse()

    monkeypatch.setattr(batch_evaluation, "urlopen", request)
    with pytest.raises(RuntimeError, match="did not confirm cache bypass"):
        batch_evaluation._ranked_urls_from_api("http://localhost:5000", "query", {"limit": 40, "top_k": 10}, "hits", 0.7)


def test_precision_at_10_uses_ten_as_fixed_denominator_when_fewer_are_returned():
    relevant = [f"https://g1.globo.com/article/{i}" for i in range(10)]
    ranked = [
        relevant[0],
        "https://g1.globo.com/other/1",
        "https://g1.globo.com/other/2",
        "https://g1.globo.com/other/3",
        "https://g1.globo.com/other/4",
        "https://g1.globo.com/other/5",
        "https://g1.globo.com/other/6",
        "https://g1.globo.com/other/7",
    ]

    result = batch_evaluation._metrics_at_ks(ranked, relevant)

    assert [metric["k"] for metric in result["metrics"]] == [1, 3, 5, 10, 20]
    metric = next(metric for metric in result["metrics"] if metric["k"] == 10)
    assert metric["precision"] == 0.1
    assert metric["recall"] == 0.1
    assert metric["f1"] == pytest.approx(0.1)
    top_one = next(metric for metric in result["metrics"] if metric["k"] == 1)
    assert top_one["precision"] == 1.0
    assert top_one["recall"] == 0.1
    assert "hits" not in metric
    assert "avg_ppr" not in metric


def test_metrics_at_all_ks_are_zero_when_search_returns_no_results():
    relevant = [f"https://g1.globo.com/article/{i}" for i in range(10)]

    result = batch_evaluation._metrics_at_ks([], relevant)

    assert [metric["k"] for metric in result["metrics"]] == [1, 3, 5, 10, 20]
    for metric in result["metrics"]:
        assert metric["precision"] == 0
        assert metric["recall"] == 0
        assert metric["f1"] == 0
        assert metric["relevant_total"] == len(relevant)


def test_each_k_counts_hits_against_the_fixed_full_relevance_list():
    relevant = [f"https://g1.globo.com/article/{i}" for i in range(30)]
    ranked = [
        relevant[4], relevant[0], relevant[2], "https://g1.globo.com/other",
        relevant[1], relevant[9], relevant[3], relevant[19], relevant[6], relevant[29],
    ]

    result = batch_evaluation._metrics_at_ks(ranked, relevant)

    expected_hits = {1: 1, 3: 3, 5: 4, 10: 9, 20: 9}
    assert result["relevant_total"] == 30
    assert result["ranked_total"] == 10
    for metric in result["metrics"]:
        k = metric["k"]
        hits = expected_hits[k]
        assert metric["relevant_total"] == 30
        assert metric["precision"] == pytest.approx(hits / k)
        assert metric["recall"] == pytest.approx(hits / 30)
        expected_f1 = 2 * (hits / k) * (hits / 30) / ((hits / k) + (hits / 30)) if hits else 0
        assert metric["f1"] == pytest.approx(expected_f1)


def test_short_relevant_list_uses_full_size_as_recall_denominator_at_each_k():
    relevant = ["https://g1.globo.com/a", "https://g1.globo.com/b"]

    result = batch_evaluation._metrics_at_ks(relevant, relevant)

    for metric in result["metrics"]:
        k = metric["k"]
        hits = min(k, 2)
        precision = hits / k
        assert metric["relevant_total"] == 2
        assert metric["precision"] == pytest.approx(precision)
        recall = hits / 2
        assert metric["recall"] == pytest.approx(recall)
        assert metric["f1"] == pytest.approx(2 * precision * recall / (precision + recall))


def test_ranked_urls_are_deduplicated_before_cutoffs_against_full_reference():
    relevant = [f"https://g1.globo.com/article/{i}" for i in range(20)]
    ranked = ["", relevant[0], relevant[0], relevant[1], "", relevant[2], relevant[0]]

    result = batch_evaluation._metrics_at_ks(ranked, relevant)

    assert result["ranked_total"] == 3
    metric = next(metric for metric in result["metrics"] if metric["k"] == 3)
    assert metric["precision"] == 1
    assert metric["recall"] == pytest.approx(3 / 20)
    assert metric["f1"] == pytest.approx(6 / 23)


def test_ranking_metrics_use_the_full_binary_relevance_set():
    relevant = ["a", "b", "c", "d"]
    ranked = ["other", "a", "other-2", "b", "other-3", "c"]

    metrics = batch_evaluation._ranking_metrics(ranked, relevant)

    assert metrics["mrr@20"] == pytest.approx(0.5)
    # At ranks 2 and 4, precision-at-hit is 1/2 and 2/4; divide by 4 judged positives.
    assert metrics["map@5"] == pytest.approx(0.25)
    assert metrics["map@10"] == pytest.approx(0.375)
    assert metrics["map@20"] == pytest.approx(0.375)
    assert metrics["ndcg@5"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5))
        / sum(1 / math.log2(i + 1) for i in range(1, 5))
    )
    ideal_dcg = sum(1 / math.log2(i + 1) for i in range(1, 5))
    assert metrics["ndcg@10"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5) + 1 / math.log2(7)) / ideal_dcg
    )
    assert metrics["ndcg@10"] == metrics["ndcg@20"]


def test_ranking_metrics_are_zero_when_no_relevant_results_are_ranked():
    metrics = batch_evaluation._ranking_metrics(["other"], ["relevant"])
    assert all(value == 0 for value in metrics.values())


def test_batch_csv_has_one_row_per_preset_seed_method_and_quorum():
    metrics = [
        {"k": k, "precision": 1 / k, "recall": 1 / k, "f1": 1 / k}
        for k in reversed(batch_evaluation.BATCH_KS)
    ]
    report = {
        "ks": list(batch_evaluation.BATCH_KS),
        "evaluations": [{
            "id": "eval-1",
            "query": "test",
            "results": [
                {
                    "preset": preset_name,
                    "seed_method": seed_method,
                    "quorum": quorum,
                    **settings,
                    "metrics": {
                        "relevant_total": 10,
                        "ranked_total": 10,
                        "metrics": metrics,
                    },
                    "ranking_metrics": {"mrr@20": 0.5, "map@5": 0.4, "map@10": 0.3,
                                        "map@20": 0.2, "ndcg@5": 0.6, "ndcg@10": 0.5,
                                        "ndcg@20": 0.4},
                }
                for preset_name, settings in batch_evaluation.SEARCH_PRESETS.items()
                for quorum in batch_evaluation.QUORUM_VALUES
                for seed_method in batch_evaluation.SEED_METHODS
            ],
        }],
    }

    fields, rows = batch_evaluation._csv_rows(report)

    assert fields[:7] == ["id", "query", "query_formulation", "preset", "stage", "ranking", "result_unit"]
    assert "reference_pool_recall" in fields
    assert "effective_quorum" in fields
    assert all(name in fields for name in ("mrr@20", "map@20", "ndcg@20"))
    assert len(fields) == len(set(fields))
    assert len(rows) == len(batch_evaluation.SEARCH_PRESETS) * len(batch_evaluation.QUORUM_VALUES) * len(batch_evaluation.SEED_METHODS)
    assert {(row["preset"], row["seed_method"], row["quorum"]) for row in rows} == {
        (preset, method, quorum)
        for preset in batch_evaluation.SEARCH_PRESETS
        for quorum in batch_evaluation.QUORUM_VALUES
        for method in batch_evaluation.SEED_METHODS
    }
    for row in rows:
        assert row["mrr@20"] == 0.5
        assert row["ndcg@20"] == 0.4
        for k in batch_evaluation.BATCH_KS:
            for name in ("precision", "recall", "f1"):
                assert row[f"{name}@{k}"] == pytest.approx(1 / k)
                assert f"oracle_{name}@{k}" in fields


def test_batch_evaluation_runs_every_quorum_value(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(batch_evaluation, "RANKINGS", ("ppr",))

    monkeypatch.setattr(
        batch_evaluation,
        "_validate_relevant_urls_exist",
        lambda engine, evaluations: None,
    )

    def fake_ranked_urls(api_base_url, query, preset, seed_method, quorum):
        calls.append((preset, seed_method, quorum))
        return []

    monkeypatch.setattr(batch_evaluation, "_ranked_urls_from_api", fake_ranked_urls)

    summary = batch_evaluation.run_batch_evaluation(
        engine=None,
        api_base_url="http://localhost:5000",
        evaluations=valid_document()["evaluations"],
        json_path=tmp_path / "results.json",
        csv_path=tmp_path / "results.csv",
    )

    expected = {
        (preset, method, quorum)
        for preset in batch_evaluation.SEARCH_PRESETS
        for method in batch_evaluation.SEED_METHODS
        for quorum in batch_evaluation.QUORUM_VALUES
    }
    assert len(calls) == 3 * len(batch_evaluation.SEED_METHODS) * len(batch_evaluation.QUORUM_VALUES)
    assert {
        (preset["top_k"], method, quorum)
        for preset, method, quorum in calls
    } == {
        (batch_evaluation.SEARCH_PRESETS[preset]["top_k"], method, quorum)
        for preset, method, quorum in expected
    }
    assert summary["status"] == "completed"
    assert summary["completed_results"] == summary["total_results"] == 3 * len(batch_evaluation.SEED_METHODS) * len(batch_evaluation.QUORUM_VALUES)
    assert "evaluations" not in summary
    with (tmp_path / "results.json").open(encoding="utf-8") as stream:
        report = json.load(stream)
    assert len(report["evaluations"][0]["results"]) == 3 * len(batch_evaluation.SEED_METHODS) * len(batch_evaluation.QUORUM_VALUES)
    assert report["ks"] == [1, 3, 5, 10, 20]
    assert report["relevance_reference"] == "all_relevant_urls_fixed"
    assert report["bypass_cache"] is True
    assert all(result["cache_bypassed"] is True for result in report["evaluations"][0]["results"])
    for result in report["evaluations"][0]["results"]:
        assert [metric["k"] for metric in result["metrics"]["metrics"]] == report["ks"]

    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == 1 + 3 * len(batch_evaluation.SEED_METHODS) * len(batch_evaluation.QUORUM_VALUES)
    with (tmp_path / "results.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3 * len(batch_evaluation.SEED_METHODS) * len(batch_evaluation.QUORUM_VALUES)
    for row in rows:
        for k in batch_evaluation.BATCH_KS:
            for name in ("precision", "recall", "f1"):
                assert float(row[f"{name}@{k}"]) == 0
