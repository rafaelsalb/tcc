import csv
import json

import pytest

from services import batch_evaluation as batch
from services.search_pipeline import run_pipeline


A, B, C, X = [f"https://g1.globo.com/{letter}" for letter in "abcx"]


class Ranker:
    def ppr(self, urls, seed_method):
        return {}, [{"article": u, "score": 1.0} for u in reversed(urls)], {
            "meta": {"graph_surviving_articles": 3, "entity_count": 20, "ppr_seed_count": 2, "seed_fallback": None},
        }


def response(methods=batch.SEED_METHODS):
    return run_pipeline({
        "retrieval_id": "group-one", "result_unit": "articles",
        "ranked": [{"article": u, "score": 1.0} for u in [B, A, X]],
        "lexical_ranked": [{"article": u, "score": 1.0} for u in [A, C, X]],
        "diagnostics": {"lexical_candidate_article_urls": [A, B, C, X],
                        "hybrid_eligible_article_urls": [A, B, X],
                        "lexical_candidate_articles": 4, "lexical_candidate_chunks": 10,
                        "effective_quorum": 1, "returned_articles": 3},
    }, Ranker(), "compare", seed_methods=methods)


def evaluation():
    return {"id": "case", "query": "short", "query_formulation": "short_theme", "relevant_urls": [A, B, C]}


def test_coverage_distinguishes_missing_candidates_from_bad_order():
    coverage = batch._coverage([X, B, A, C], [A, B, C])
    assert coverage["reference_in_pool"] == 3
    assert coverage["reference_pool_recall"] == 1
    oracle = {m["k"]: m for m in coverage["oracle_metrics"]}
    actual = {m["k"]: m for m in batch._metrics_at_ks([X, B, A, C], [A, B, C])["metrics"]}
    assert actual[1]["precision"] == 0
    assert oracle[1]["precision"] == 1
    assert actual[1]["recall"] == 0
    assert oracle[1]["recall"] == pytest.approx(1 / 3)
    assert oracle[1]["f1"] == pytest.approx(0.5)
    assert oracle[20]["precision"] == pytest.approx(3 / 20)
    assert oracle[20]["recall"] == 1
    assert oracle[20]["f1"] == pytest.approx(6 / 23)


def test_paired_results_keep_diagnostics_but_not_large_lexical_url_list():
    comparisons = batch._paired_comparisons(response(), evaluation(), batch.SEED_METHODS)
    assert len(comparisons) == 2 + 2 * len(batch.SEED_METHODS)
    for result in comparisons:
        assert result["diagnostics"]["lexical_reference_in_pool"] == 3
        assert "lexical_candidate_article_urls" not in result["diagnostics"]
        assert "hybrid_eligible_article_urls" not in result["diagnostics"]
        assert result["diagnostics"]["hybrid_eligible_reference_in_pool"] == 2
        assert result["coverage"]["reference_in_pool"] == 2


@pytest.mark.parametrize("damage", ["version", "missing_stage", "pool", "identifier", "shape"])
def test_invalid_comparison_contract_is_rejected(damage):
    payload = response()
    if damage == "version":
        payload.pop("search_version")
    elif damage == "missing_stage":
        payload["rankings"].pop()
    elif damage == "pool":
        payload["rankings"][2]["ranked"].pop()
    elif damage == "identifier":
        payload["rankings"][2]["retrieval_id"] = "different"
    else:
        payload["rankings"][2]["ranked"] = [None]
    with pytest.raises(RuntimeError):
        batch._paired_comparisons(payload, evaluation(), batch.SEED_METHODS)


def test_formulation_is_optional_validated_and_not_inferred_from_id():
    doc = {"schema_version": 1, "evaluations": [evaluation()]}
    assert batch.validate_document(doc)[0]["query_formulation"] == "short_theme"
    doc["evaluations"][0].pop("query_formulation")
    doc["evaluations"][0]["id"] = "case__keyword"
    assert batch.validate_document(doc)[0]["query_formulation"] == "unspecified"
    for value in ("", None, 1):
        doc["evaluations"][0]["query_formulation"] = value
        with pytest.raises(ValueError, match="query_formulation"):
            batch.validate_document(doc)


def test_comparison_results_are_checkpointed_individually_and_resume_reuses_group(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 40, "top_k": 3}})
    calls = []
    stop = True
    csv_path, json_path = tmp_path / "stages.csv", tmp_path / "stages.json"

    def api(*args, **options):
        if calls and stop:
            with csv_path.open(newline="", encoding="utf-8-sig") as stream:
                assert len(list(csv.DictReader(stream))) == 2 + 2 * len(batch.SEED_METHODS)
            raise KeyboardInterrupt()
        calls.append((args, options))
        if options.get("stage") == "compare":
            return response(options["seed_methods"])
        return {"search_version": batch.SEARCH_VERSION, "cache_bypassed": True,
                "ranking": options["ranking"], "ranked": [{"article": A, "score": 1.0}]}

    monkeypatch.setattr(batch, "_response_from_api", api)
    args = (None, "http://localhost:5000", [evaluation()], json_path, csv_path)
    options = {"compare_stages": True, "result_unit": "articles", "quorums": (0.3, 0.7)}
    summary = batch.run_batch_evaluation(*args, **options)
    compare_rows = 2 + 2 * len(batch.SEED_METHODS)
    assert summary["status"] == "interrupted" and summary["completed_results"] == compare_rows
    assert len(json_path.with_suffix(".jsonl").read_bytes().splitlines()) == compare_rows + 1
    stop = False
    summary = batch.run_batch_evaluation(*args, resume=True, **options)
    assert summary["completed_results"] == summary["total_results"] == 2 * (compare_rows + len(batch.RANKINGS) * len(batch.SEED_METHODS))
    assert len(calls) == 2 + 2 * len(batch.RANKINGS) * len(batch.SEED_METHODS)  # Compare once per quorum.
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == summary["total_results"]
    assert {r["stage"] for r in rows} == {"lexical", "hybrid", "ppr", "fused"}
    assert all(r["query_formulation"] == "short_theme" and r["result_unit"] == "articles" for r in rows)
    assert {r["seed_method"] for r in rows} == {"none", *batch.SEED_METHODS}
    report = json.loads(json_path.read_text())
    assert report["total_comparison_rows"] == summary["total_results"]
    assert len(report["evaluations"][0]["results"]) == summary["total_results"]
    assert all("comparisons" not in result for result in report["evaluations"][0]["results"])
    with pytest.raises(ValueError, match="does not match"):
        batch.run_batch_evaluation(*args, resume=True, **{**options, "result_unit": "chunks"})


def test_default_compare_uses_all_three_paired_presets_and_rejects_old_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    calls = []

    def api(base, query, preset, method, quorum, **options):
        calls.append((preset["top_k"], preset["limit"]))
        if options.get("stage") == "compare":
            return response(options["seed_methods"])
        return {"search_version": batch.SEARCH_VERSION, "cache_bypassed": True,
                "ranking": options["ranking"], "ranked": [{"article": A, "score": 1.0}]}

    monkeypatch.setattr(batch, "_response_from_api", api)
    args = (None, "http://localhost:5000", [evaluation()], tmp_path / "pairs.json", tmp_path / "pairs.csv")
    options = {"compare_stages": True, "result_unit": "articles", "quorums": (0.7,), "seed_methods": ("ppr_top10",)}
    summary = batch.run_batch_evaluation(*args, **options)
    expected_rows = 3 * (2 + 2 * len(options["seed_methods"]) + len(batch.RANKINGS) * len(options["seed_methods"]))
    assert len(calls) == 3 + 3 * len(batch.RANKINGS)  # comparison request per preset plus each ranking.
    assert summary["completed_results"] == summary["total_results"] == expected_rows
    with args[4].open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == expected_rows
    assert {(int(row["top_k"]), int(row["limit"])) for row in rows} == set(calls)
    metadata = json.loads(args[3].read_text())
    assert metadata["presets"] == batch.SEARCH_PRESETS

    previous_settings = {name: dict(settings) for name, settings in batch.SEARCH_PRESETS.items()}
    previous_settings["rapido"]["limit"] = 400
    monkeypatch.setattr(batch, "SEARCH_PRESETS", previous_settings)
    with pytest.raises(ValueError, match="does not match"):
        batch.run_batch_evaluation(*args, resume=True, **options)
    assert len(calls) == 3 + 3 * len(batch.RANKINGS)


def test_ordinary_batch_defaults_to_all_rankings(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 250, "top_k": 100}})
    monkeypatch.setattr(batch, "QUORUM_VALUES", (0.7,))
    calls = []

    def api(*args, **options):
        calls.append(options["ranking"])
        return {"search_version": batch.SEARCH_VERSION, "cache_bypassed": True, "ranking": options["ranking"], "ranked": []}

    monkeypatch.setattr(batch, "_ranked_urls_from_api", api)
    args = (None, "http://localhost:5000", [evaluation()], tmp_path / "all.json", tmp_path / "all.csv")
    summary = batch.run_batch_evaluation(*args)

    assert summary["completed_results"] == len(batch.RANKINGS) * len(batch.SEED_METHODS)
    assert set(calls) == set(batch.RANKINGS)
    report = json.loads(args[3].read_text())
    assert report["rankings"] == list(batch.RANKINGS)


@pytest.mark.parametrize("kwargs", [
    {"presets": []}, {"presets": ["rapido", "rapido"]},
    {"quorums": [float("nan")]}, {"quorums": [0.3, 0.3]},
    {"seed_methods": ["hits_top10"]}, {"result_unit": "bad"},
])
def test_invalid_experiment_options_fail_before_creating_outputs(tmp_path, kwargs):
    with pytest.raises(ValueError):
        batch.run_batch_evaluation(None, "http://localhost:5000", [evaluation()], tmp_path / "x.json", tmp_path / "x.csv", **kwargs)
    assert not list(tmp_path.iterdir())
