import json

import pytest

from services.batch_summary import LiveSummary, summary_paths
from services import batch_evaluation as batch


def result(ranking="ppr", seed="hits", mode="ranking", score=1.0, computation_seconds=None):
    return {"mode": mode, "ranking": ranking, "stage": "ppr", "seed_method": seed,
            "preset": "rapido", "quorum": 0.7, "limit": 250, "top_k": 100, "result_unit": "articles",
             "metrics": {"metrics": [{"k": k, "precision": score, "recall": score, "f1": score}
                                      for k in batch.BATCH_KS]},
             "ranking_metrics": {"mrr@20": score, "map@5": score, "map@10": score,
                                 "map@20": score, "ndcg@5": score, "ndcg@10": score,
                                 "ndcg@20": score},
             "coverage": {"oracle_metrics": [{"k": k, "precision": 1., "recall": 1., "f1": 1.}
                                             for k in batch.BATCH_KS], "reference_pool_recall": 1.0},
             "computation_seconds": computation_seconds}


def test_summary_lists_every_group_and_reports_actual_and_oracle_means(tmp_path):
    summary = LiveSummary(batch.BATCH_KS)
    for i in range(5):
        summary.add({"id": f"theme{i}__keyword", "query_formulation": "keyword"}, result(score=i / 4))
    summary.add({"id": "theme0__question", "query_formulation": "question"}, result(score=1))
    report = summary.snapshot(6, 10, "running")
    assert len(report["groups"]["themes"]) == 5
    assert report["groups"]["themes"][0]["parameters"]["theme"] == "theme4"
    theme0 = next(g for g in report["groups"]["themes"] if g["parameters"]["theme"] == "theme0")
    assert theme0["means"]["f1@20"] == 0.5
    assert theme0["means"]["oracle_f1@20"] == 1
    assert theme0["means"]["ndcg@20"] == 0.5
    assert theme0["queries"] == 2
    assert not report["groups"]["stages"]
    path = tmp_path / "run.json"
    summary.write(path, 6, 10, "running")
    md_path, json_path = summary_paths(path)
    assert "theme4" in md_path.read_text()
    assert "Métricas de ranking (referência completa)" in md_path.read_text()
    assert json.loads(json_path.read_text())["completed_results"] == 6
    assert not list(tmp_path.glob("*.tmp"))


def test_seed_independent_results_excluded_and_stages_only_from_comparisons():
    summary = LiveSummary(batch.BATCH_KS)
    item = {"id": "theme__keyword"}
    summary.add(item, result("rrf", "hits"))
    summary.add(item, result("ppr", "louvain", mode="compare"))
    report = summary.snapshot(2, 2, "completed")
    assert [g["parameters"] for g in report["groups"]["seeding_methods"]] == [{"seed_method": "louvain"}]
    assert [g["parameters"] for g in report["groups"]["stages"]] == [{"stage": "ppr"}]


def test_summary_orders_parameter_combinations_by_computation_time():
    summary = LiveSummary(batch.BATCH_KS)
    item = {"id": "theme__keyword"}
    summary.add(item, result("ppr", "hits", computation_seconds=0.2))
    summary.add(item, result("graph_salsa", "louvain", computation_seconds=2.5))
    report = summary.snapshot(2, 2, "completed")
    assert report["fastest_combinations"][0]["parameters"]["ranking"] == "ppr"
    assert report["slowest_combinations"][0]["parameters"]["ranking"] == "graph_salsa"
    assert report["fastest_combinations"][0]["means"]["computation_seconds"] == 0.2


def test_resume_rebuilds_summary_and_updates_before_next_request(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 250, "top_k": 100}})
    monkeypatch.setattr(batch, "RANKINGS", ("ppr",))
    monkeypatch.setattr(batch, "SEED_METHODS", ("hits",))
    path = tmp_path / "run.json"
    md_path, summary_json = summary_paths(path)
    calls = []
    interrupted = True

    def request(*args, **kwargs):
        report = json.loads(summary_json.read_text())
        assert report["completed_results"] == len(calls)
        if calls and interrupted:
            raise KeyboardInterrupt()
        calls.append(args)
        return ["https://g1.globo.com/a"]

    monkeypatch.setattr(batch, "_ranked_urls_from_api", request)
    args = (None, "http://localhost:5000", [{"id": "tema__keyword", "query": "teste",
             "relevant_urls": ["https://g1.globo.com/a"]}], path, path.with_suffix(".csv"))
    options = {"quorums": (0.3, 0.7)}
    batch.run_batch_evaluation(*args, **options)
    assert json.loads(summary_json.read_text())["status"] == "interrupted"
    # Derived files may be missing or stale: resume rebuilds from the journal.
    md_path.unlink()
    summary_json.write_text("stale")
    interrupted = False
    batch.run_batch_evaluation(*args, resume=True, **options)
    report = json.loads(summary_json.read_text())
    assert report["status"] == "completed"
    assert report["completed_results"] == report["summarized_rows"] == 2
    assert report["groups"]["overall"][0]["rows"] == 2
    assert md_path.exists()


def test_summary_paths_cannot_overwrite_input_and_existing_outputs_are_protected(tmp_path):
    path = tmp_path / "run.json"
    md_path, summary_json = summary_paths(path)
    summary_json.write_text("user work")
    with pytest.raises(FileExistsError):
        batch.ensure_output_available((path, path.with_suffix(".csv")), overwrite=False)
    with pytest.raises(ValueError, match="overwrite the input"):
        batch.output_paths(summary_json, path)
