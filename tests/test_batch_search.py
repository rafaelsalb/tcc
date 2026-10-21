from copy import deepcopy
import csv
import json
import threading
import time
from types import SimpleNamespace

import pytest

from services.batch_search import evaluate_request
from services.evaluation_jobs import EvaluationJobManager
from services.dashboard_runs import DashboardRunManager
from services.ranking import RankingService
from services import batch_evaluation as batch


def setup_services():
    articles = [SimpleNamespace(url=u, title=u) for u in ("a", "b", "c")]
    entities = [SimpleNamespace(text_=f"Pessoa {i}", canonical=None) for i in range(12)]
    ranker = RankingService(
        SimpleNamespace(get_all=lambda **kwargs: articles),
        SimpleNamespace(entity_repository=None,
                        batch_get_or_extract_entities_and_store_for_articles=lambda *args, **kwargs: {
                            a.url: entities for a in articles}),
    )
    data = {"retrieval_id": "pool", "result_unit": "articles",
            "ranked": [{"article": u, "score": 1 / (i + 1)} for i, u in enumerate(("a", "b", "c"))],
            "lexical_ranked": [{"article": u, "score": 1.0} for u in ("b", "a", "c")],
            "results": [{"article_url": u, "article_title": u} for u in ("a", "b", "c")],
            "diagnostics": {"returned_articles": 3}}
    calls = []

    def search(**kwargs):
        calls.append(kwargs)
        return deepcopy(data)

    return SimpleNamespace(search=search), ranker, calls, data


def configurations():
    return [{"stage": "ppr", "ranking": ranking, "seed_method": seed, "mode": "ranking"}
            for seed in ("louvain", "hits", "ppr_top10")
            for ranking in ("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr")]


def test_reuse_benchmark_preserves_results_and_reduces_work(monkeypatch):
    searcher, ranker, calls, data = setup_services()
    reranks = []

    def rerank(query, rows, score_cache=None):
        reranks.append(query)
        return [{"article": row["article_url"], "score": 1.0} for row in rows]

    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank", rerank)
    original = deepcopy(data)
    report = evaluate_request(searcher, ranker, {
        "search": {"query": "teste", "result_unit": "articles"},
        "configurations": configurations(), "benchmark": True,
    })
    assert report["performance"]["equivalent"] is True
    assert report["performance"]["optimized"]["counts"] == {
        "retrieval_calls": 1, "ranking_calls": 12, "graph_builds": 1, "ppr_runs": 3,
    }
    assert report["performance"]["baseline"]["counts"] == {
        "retrieval_calls": 18, "ranking_calls": 18, "graph_builds": 9, "ppr_runs": 9,
    }
    assert len(reranks) == 4  # One optimized pass, three independent passes.
    assert len(report["results"]) == 18 and len(calls) == 19
    assert all(entry["computation_seconds"] >= 0 for entry in report["results"])
    assert data == original
    assert not hasattr(ranker, "_batch_graphs")


def test_batch_endpoint_evaluates_configurable_ensemble_and_benchmark(monkeypatch):
    searcher, ranker, calls, _ = setup_services()
    monkeypatch.setattr("services.search_pipeline._cross_encoder_rank", lambda query, rows, score_cache=None: [
        {"article": row["article_url"], "score": float(i)} for i, row in enumerate(reversed(rows))
    ])
    report = evaluate_request(searcher, ranker, {
        "search": {"query": "teste", "result_unit": "articles",
                   "ensemble_rankings": ["rrf", "cross_encoder", "ppr"]},
        "configurations": [{"mode": "ranking", "stage": "ppr", "ranking": "ensemble_rrf",
                            "seed_method": "hits"}],
        "benchmark": True,
    })
    assert report["performance"]["equivalent"] is True
    assert len(report["results"]) == 1
    assert len(report["results"][0]["ranked"]) == 3
    assert len(calls) == 2  # one reused retrieval plus one independent baseline retrieval
    assert report["performance"]["optimized"]["counts"]["graph_builds"] == 1
    assert report["performance"]["optimized"]["counts"]["ppr_runs"] == 1


def test_compare_rows_and_ordinary_rows_keep_their_identity():
    searcher, ranker, _, _ = setup_services()
    entries = [{"mode": "compare", "stage": stage, "ranking": stage,
                "seed_method": "none" if stage in ("lexical", "hybrid") else "hits"}
               for stage in ("lexical", "hybrid", "ppr", "fused")]
    entries += [{"mode": "ranking", "stage": "ppr", "ranking": "fused", "seed_method": "hits"}]
    report = evaluate_request(searcher, ranker, {"search": {"query": "teste"}, "configurations": entries})
    assert report["results"][0]["retrieval_id"] == "pool:lexical"
    assert report["performance"]["optimized"]["counts"]["ppr_runs"] == 1
    assert [r["mode"] for r in report["results"]] == ["compare"] * 4 + ["ranking"]


def test_evaluation_reports_progress_after_each_configuration():
    searcher, ranker, _, _ = setup_services()
    configs = configurations()[:3]
    updates = []
    report = evaluate_request(searcher, ranker, {
        "search": {"query": "teste"}, "configurations": configs,
    }, progress_callback=updates.append)
    assert len(report["results"]) == 3
    completion = [update for update in updates if update["activity"] == "ranking"]
    assert [update["completed"] for update in completion] == [1, 2, 3]
    assert all(update["total"] == 3 for update in completion)


def test_background_evaluation_job_exposes_progress_and_result():
    searcher, ranker, _, _ = setup_services()
    manager = EvaluationJobManager(max_workers=1, retention_seconds=60)
    try:
        job_id = manager.submit(searcher, ranker, {
            "search": {"query": "teste"}, "configurations": configurations()[:2],
        })
        deadline = time.monotonic() + 5
        job = manager.get(job_id)
        while job["status"] not in ("completed", "failed") and time.monotonic() < deadline:
            time.sleep(0.01)
            job = manager.get(job_id)
        assert job["status"] == "completed"
        assert job["progress"]["completed"] == job["progress"]["total"] == 2
        assert len(job["result"]["results"]) == 2
    finally:
        manager.shutdown()


def test_empty_evaluation_group_completes_without_model_or_graph(monkeypatch):
    import sys

    searcher, ranker, _, data = setup_services()
    data.update(ranked=[], lexical_ranked=[], results=[])
    monkeypatch.setattr("services.search_pipeline._CROSS_ENCODER", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setattr(ranker, "_prepare_graph", lambda *args: pytest.fail("empty pool must not build a graph"))
    report = evaluate_request(searcher, ranker, {
        "search": {"query": "no matches"}, "configurations": configurations(), "benchmark": True,
    })
    assert len(report["results"]) == 18
    assert all(entry["ranked"] == [] for entry in report["results"])
    assert report["performance"]["equivalent"] is True
    assert report["performance"]["optimized"]["counts"]["graph_builds"] == 0
    for entry in report["results"]:
        if entry["ranking"] == "cross_encoder":
            assert entry["diagnostics"]["cross_encoder_reranked_count"] == 0
            assert entry["diagnostics"]["cross_encoder_missing_document_count"] == 0


@pytest.mark.parametrize("body", [None, {}, {"search": {}, "configurations": []},
    {"search": {}, "configurations": [{"stage": "ppr", "ranking": "bad"}]}])
def test_invalid_evaluations_rejected(body):
    with pytest.raises(ValueError):
        evaluate_request(None, None, body)


def test_cli_reuse_checkpoints_each_row_and_resumes_inside_group(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 50, "top_k": 10}})
    calls = []
    url = "https://g1.globo.com/teste.ghtml"

    def request(base, item, task, configs, benchmark):
        calls.append(task["quorum"])
        return {"results": [{**c, "ranked": [{"article": url, "score": 1.0}],
                             "diagnostics": {}, "retrieval_id": "pool", "computation_reused": False}
                            for c in configs],
                "performance": {"optimized": {"wall_seconds": 1.0,
                                "counts": {"retrieval_calls": 1, "graph_builds": 1, "ppr_runs": 3}}}}

    monkeypatch.setattr(batch, "_evaluation_from_api", request)
    args = (None, "http://localhost:5000", [{"id": "case", "query": "teste", "relevant_urls": [url]}],
            tmp_path / "report.json", tmp_path / "report.csv")
    append = batch.ResultJournal.append

    def interrupt(journal, task, result):
        if journal.completed == 1:
            raise KeyboardInterrupt()
        append(journal, task, result)

    monkeypatch.setattr(batch.ResultJournal, "append", interrupt)
    options = dict(reuse=True, compare_stages=True, quorums=(0.3, 0.7), result_unit="articles")
    summary = batch.run_batch_evaluation(*args, **options)
    assert summary["completed_results"] == 1
    monkeypatch.setattr(batch.ResultJournal, "append", append)
    summary = batch.run_batch_evaluation(*args, resume=True, **options)
    expected_rows = 2 * (2 + 2 * len(batch.SEED_METHODS) + len(batch.RANKINGS) * len(batch.SEED_METHODS))
    assert summary["completed_results"] == summary["total_results"] == expected_rows
    assert calls == [0.3, 0.3, 0.7]  # Only the partially saved group is fetched again.
    with args[4].open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == expected_rows
    assert all(row["retrieval_calls"] == "1" for row in rows)
    report = json.loads(args[3].read_text())
    assert report["reuse"] is True
    assert all(row["ranked_urls"] == [url] for row in report["evaluations"][0]["results"])


def test_batch_transport_validates_equivalence_and_preserves_pool_diagnostics(monkeypatch):
    import json

    searcher, ranker, _, data = setup_services()
    data["diagnostics"]["lexical_candidate_article_urls"] = ["a", "b"]
    data["diagnostics"]["hybrid_eligible_article_urls"] = ["a"]
    configs = [c for c in configurations() if c["ranking"] in ("ppr", "fused", "mmr")]
    damaged = False

    def urlopen(request, timeout):
        assert timeout == batch.JOB_HTTP_TIMEOUT_SECONDS
        if request.get_method() == "POST":
            assert request.full_url == "http://localhost:5000/evaluate/jobs"
            payload = {"job_id": "test-job", "status_url": "/evaluate/jobs/test-job"}
        else:
            assert request.full_url == "http://localhost:5000/evaluate/jobs/test-job"
            result = evaluate_request(searcher, ranker, json.loads(body_data))
            if damaged:
                result["performance"]["equivalent"] = False
            payload = {"job_id": "test-job", "status": "completed", "result": result}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(payload).encode()

        return Response()

    body_data = None
    original_request = batch._job_api_json

    def remember_body(request):
        nonlocal body_data
        if request.get_method() == "POST":
            body_data = request.data
        return original_request(request)

    monkeypatch.setattr(batch, "_job_api_json", remember_body)
    monkeypatch.setattr(batch, "urlopen", urlopen)
    item = {"query": "teste", "relevant_urls": ["a", "b"]}
    task = {"limit": 50, "top_k": 10, "quorum": 0.7, "result_unit": "articles"}
    report = batch._evaluation_from_api("http://localhost:5000", item, task, configs, benchmark=True)
    assert report["results"][0]["diagnostics"]["lexical_reference_in_pool"] == 2
    assert report["results"][0]["diagnostics"]["hybrid_eligible_reference_in_pool"] == 1
    damaged = True
    with pytest.raises(RuntimeError, match="refusing to save"):
        batch._evaluation_from_api("http://localhost:5000", item, task, configs, benchmark=True)


def test_batch_job_transport_polls_until_completed_and_reports_progress(monkeypatch, capsys):
    config = {"mode": "ranking", "stage": "ppr", "ranking": "ppr", "seed_method": "hits"}
    payload = {"evaluation_version": "reuse_v1", "cache_bypassed": True,
               "search_version": batch.SEARCH_VERSION,
               "results": [{**config, "ranked": [{"article": "a", "score": 1.0}],
                            "diagnostics": {}, "retrieval_id": "pool"}],
               "performance": {}}
    responses = iter([
        {"job_id": "job-1", "status_url": "/evaluate/jobs/job-1"},
        {"job_id": "job-1", "status": "running",
         "progress": {"phase": "optimized", "activity": "retrieval", "completed": 0,
                      "total": 1, "configuration": config}},
        {"job_id": "job-1", "status": "completed", "result": payload},
    ])
    monkeypatch.setattr(batch, "_job_api_json", lambda request: next(responses))
    monkeypatch.setattr(batch, "EVALUATION_JOB_POLL_SECONDS", 0)
    result = batch._evaluation_from_api(
        "http://localhost:5000", {"query": "teste", "relevant_urls": ["a"]},
        {"limit": 50, "top_k": 10, "quorum": 0.7, "result_unit": "articles"}, [config],
    )
    assert result["results"][0]["ranked"][0]["article"] == "a"
    assert "0/1 configurations): ppr/hits" in capsys.readouterr().out


def test_dashboard_run_persists_results_and_summary_in_store_without_run_files(monkeypatch, tmp_path):
    from services import dashboard_runs as dashboard_module

    searcher, ranker, _, _ = setup_services()
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    (data_dir / "evals_tiny.json").write_text(json.dumps({
        "schema_version": 1,
        "evaluations": [{"id": "tema__short_question", "query": "teste",
                         "relevant_urls": ["https://g1.globo.com/a.ghtml"]}],
    }), encoding="utf-8")
    monkeypatch.setattr(dashboard_module, "_validate_relevant_urls_exist", lambda *args: None)
    manager = DashboardRunManager(searcher, ranker, None, data_dir)
    try:
        run = manager.start("evals_tiny.json", {
            "presets": ["rapido"], "quorums": [0.3], "seed_methods": ["hits"],
            "rankings": ["hybrid_max", "vector"], "result_unit": "articles",
        })
        deadline = time.monotonic() + 5
        state = manager.get(run["run_id"])
        while state["status"] not in ("completed", "failed") and time.monotonic() < deadline:
            time.sleep(0.01)
            state = manager.get(run["run_id"])
        assert state["status"] == "completed"
        assert state["completed_at"] >= state["created_at"]
        assert state["progress"]["completed"] == state["progress"]["total"] == 2
        page = manager.results(run["run_id"], after=0, limit=1)
        assert len(page["events"]) == 1
        assert page["has_more"] is True
        assert "ranked_urls" not in page["events"][0]["result"]
        assert "ranked_results" not in page["events"][0]["result"]
        next_page = manager.results(run["run_id"], after=page["cursor"], limit=1)
        assert len(next_page["events"]) == 1 and next_page["has_more"] is False
        assert next_page["events"][0]["theme"] == "tema"
        assert next_page["events"][0]["result"]["coverage"]["reference_pool_recall"] == 0.0
        assert "diagnostics" not in next_page["events"][0]["result"]
        assert "retrieval_id" not in next_page["events"][0]["result"]
        grouped_page = manager.results(run["run_id"], after=0, limit=10)
        assert grouped_page["events"][0]["query"] == "teste"
        assert "query" not in grouped_page["events"][1]
        assert "query_formulation" not in grouped_page["events"][1]
        detail = manager.result(run["run_id"], 1)
        assert detail["result"]["ranked_urls"] == ["a", "b", "c"]
        assert detail["result"]["ranked_results"] == [
            {"article": "a", "score": 1.0},
            {"article": "b", "score": 0.5},
            {"article": "c", "score": 1 / 3},
        ]
        summary = manager._memory_artifacts[(run["run_id"], '[null,null,null,"summary"]')]
        retrieval_artifacts = [
            key for (artifact_run_id, key) in manager._memory_artifacts
            if artifact_run_id == run["run_id"] and key.endswith(',"retrieval"]')
        ]
        assert len(retrieval_artifacts) == 1  # one shared retrieval per evaluation group
        assert {entry["parameters"]["ranking"] for entry in summary["groups"]["rankings"]} == {
            "hybrid_max", "vector",
        }
        assert manager._memory_results[run["run_id"]][0]["result"]["ranked_urls"] == ["a", "b", "c"]
        assert not list(tmp_path.rglob("results.jsonl"))
        assert not list(tmp_path.rglob("state.json"))
        assert not list(tmp_path.rglob("run.summary.*"))
    finally:
        manager.shutdown()


def test_dashboard_dataset_catalog_groups_json_evaluations_by_theme(tmp_path):
    from services.dashboard_runs import available_evaluation_sets

    (tmp_path / "evals_themes.json").write_text(json.dumps({
        "schema_version": 1,
        "evaluations": [
            {"id": f"tema__q{i}", "query": f"consulta {i}",
             "relevant_urls": ["https://g1.globo.com/a.ghtml", "https://g1.globo.com/b.ghtml"]}
            for i in range(2)
        ] + [{"id": "outro__q", "query": "outra consulta",
              "relevant_urls": ["https://g1.globo.com/c.ghtml"]}],
    }), encoding="utf-8")
    sets = available_evaluation_sets(tmp_path)
    assert sets == [
        {"id": "evals_themes.json::tema", "label": "tema", "source": "evals_themes.json",
         "count": 2, "articles": 2},
        {"id": "evals_themes.json::outro", "label": "outro", "source": "evals_themes.json",
         "count": 1, "articles": 1},
    ]


def test_dashboard_resolves_multiple_theme_snapshots_and_deduplicates_identical_queries(tmp_path):
    shared = {"id": "tema__q1", "query": "consulta compartilhada",
              "relevant_urls": ["https://g1.globo.com/a.ghtml"]}
    (tmp_path / "evals_a.json").write_text(json.dumps({
        "schema_version": 1,
        "evaluations": [shared, {"id": "outro__q2", "query": "outra",
                                 "relevant_urls": ["https://g1.globo.com/b.ghtml"]}],
    }), encoding="utf-8")
    (tmp_path / "evals_b.json").write_text(json.dumps({
        "schema_version": 1, "evaluations": [shared],
    }), encoding="utf-8")
    manager = DashboardRunManager(None, None, None, tmp_path)
    try:
        choices = manager.available_sets()
        assert all(choice["version_label"] == "Atual" for choice in choices)
        selected = [choice["id"] for choice in choices if choice["label"] in ("tema", "outro")]
        _, evaluations, snapshot, _, _, label = manager._resolve_dataset_selection(selected)
        assert [item["id"] for item in evaluations] == ["tema__q1", "outro__q2"]
        assert snapshot["evaluations"] == evaluations
        assert "Atual" in label
    finally:
        manager.shutdown()


def test_figure_filter_options_return_distinct_facets_without_result_hydration(tmp_path):
    manager = DashboardRunManager(None, None, None, tmp_path)
    try:
        manager._runs["run-a"] = {
            "state": {
                "run_id": "run-a", "status": "completed",
                "settings": {"presets": {"rapido": {}, "profundo": {}}, "quorums": [.3, .5]},
            },
            "dataset_snapshot": {"evaluations": [
                {"id": "tema_a__q1", "query": "consulta um", "query_formulation": "keyword"},
                {"id": "tema_b__q2", "query": "consulta dois", "query_formulation": "short_question"},
            ]},
        }
        manager._memory_results["run-a"] = [
            {"evaluation_id": "tema_a__q1", "query": "consulta um", "query_formulation": "keyword",
             "result": {"preset": "rapido", "quorum": .3}},
            {"evaluation_id": "tema_a__q1", "query": "consulta um", "query_formulation": "keyword",
             "result": {"preset": "rapido", "quorum": .5}},
            {"evaluation_id": "tema_b__q2", "query": "consulta dois", "query_formulation": "short_question",
             "result": {"preset": "profundo", "quorum": .3}},
        ]
        options = manager.figure_filter_options(["run-a"])
        assert options["themes"] == ["tema_a", "tema_b"]
        assert options["formulations"] == ["keyword", "short_question"]
        assert options["presets"] == ["profundo", "rapido"]
        assert options["quorums"] == [.3, .5]
        assert options["queries"] == [
            {"id": "tema_a__q1", "theme": "tema_a", "query": "consulta um"},
            {"id": "tema_b__q2", "theme": "tema_b", "query": "consulta dois"},
        ]
        # Options come from run metadata, including evaluations with no result
        # rows yet; loading them must not depend on scanning result payloads.
        manager._memory_results["run-a"].clear()
        assert manager.figure_filter_options(["run-a"]) == options
    finally:
        manager.shutdown()


def test_dashboard_exposes_a_row_before_the_evaluation_group_finishes(monkeypatch, tmp_path):
    from threading import Event
    from services import dashboard_runs as dashboard_module

    searcher, ranker, _, _ = setup_services()
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    (data_dir / "evals_tiny.json").write_text(json.dumps({
        "schema_version": 1,
        "evaluations": [{"id": "tema__query", "query": "teste",
                         "relevant_urls": ["https://g1.globo.com/a.ghtml"]}],
    }), encoding="utf-8")
    monkeypatch.setattr(dashboard_module, "_validate_relevant_urls_exist", lambda *args: None)
    first_row_persisted = Event()
    allow_group_to_finish = Event()

    def slow_group(_searcher, _ranker, body, progress_callback, include_completed_entries):
        assert include_completed_entries is True
        configs = body["configurations"]
        for index, config in enumerate(configs):
            entry = {**config, "ranked": [{"article": "a", "score": 1.0}],
                     "diagnostics": {}, "retrieval_id": "pool", "computation_seconds": 0.01,
                     "step_timings": {}}
            progress_callback({"activity": "ranking", "completed": index + 1,
                               "total": len(configs), "configuration": config,
                               "entry": entry, "retrieval_steps": {},
                               "retrieval_seconds": 0.1, "group_elapsed_seconds": 0.1})
            if index == 0:
                first_row_persisted.set()
                assert allow_group_to_finish.wait(5)
        return {"performance": {"optimized": {"wall_seconds": 0.2}}}

    monkeypatch.setattr(dashboard_module, "evaluate_request", slow_group)
    manager = DashboardRunManager(searcher, ranker, None, data_dir)
    try:
        run = manager.start("evals_tiny.json", {
            "presets": ["rapido"], "quorums": [0.3], "seed_methods": ["hits"],
            "rankings": ["hybrid_max", "vector"], "result_unit": "articles",
        })
        assert first_row_persisted.wait(5)
        page = manager.results(run["run_id"], after=0, limit=10)
        assert [event["seq"] for event in page["events"]] == [1]
        assert manager.get(run["run_id"])["progress"]["completed"] == 1
        allow_group_to_finish.set()
        deadline = time.monotonic() + 5
        state = manager.get(run["run_id"])
        while state["status"] not in ("completed", "failed") and time.monotonic() < deadline:
            time.sleep(0.01)
            state = manager.get(run["run_id"])
        assert state["status"] == "completed"
        assert state["progress"]["completed"] == 2
    finally:
        allow_group_to_finish.set()
        manager.shutdown()


def test_dashboard_run_can_pause_then_resume_from_saved_configuration_boundary(monkeypatch, tmp_path):
    from threading import Event
    from services import dashboard_runs as dashboard_module

    searcher, ranker, _, _ = setup_services()
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    (data_dir / "evals_pause.json").write_text(json.dumps({
        "schema_version": 1,
        "evaluations": [{"id": "tema__query", "query": "teste",
                         "relevant_urls": ["https://g1.globo.com/a.ghtml"]}],
    }), encoding="utf-8")
    monkeypatch.setattr(dashboard_module, "_validate_relevant_urls_exist", lambda *args: None)
    first_saved = Event()
    continue_first_attempt = Event()
    invocation_configs = []

    def controlled_group(_searcher, _ranker, body, progress_callback, include_completed_entries):
        configs = body["configurations"]
        invocation_configs.append([config["ranking"] for config in configs])
        for index, config in enumerate(configs):
            if len(invocation_configs) == 1 and index == 1:
                first_saved.set()
                assert continue_first_attempt.wait(5)
            entry = {**config, "ranked": [{"article": "a", "score": 1.0}],
                     "diagnostics": {}, "retrieval_id": "pool", "computation_seconds": 0.01,
                     "step_timings": {}}
            progress_callback({"activity": "ranking", "completed": index + 1,
                               "total": len(configs), "configuration": config,
                               "entry": entry, "retrieval_steps": {},
                               "retrieval_seconds": 0.1, "group_elapsed_seconds": 0.1})
        return {"performance": {"optimized": {"wall_seconds": 0.2}}}

    monkeypatch.setattr(dashboard_module, "evaluate_request", controlled_group)
    manager = DashboardRunManager(searcher, ranker, None, data_dir)
    try:
        run = manager.start("evals_pause.json", {
            "presets": ["rapido"], "quorums": [0.3], "seed_methods": ["hits"],
            "rankings": ["hybrid_max", "ppr", "fused"], "result_unit": "articles",
        })
        assert first_saved.wait(5)
        pause_state = manager.pause(run["run_id"])
        assert pause_state["status"] == "pause_requested"
        continue_first_attempt.set()

        deadline = time.monotonic() + 5
        state = manager.get(run["run_id"])
        while state["status"] != "paused" and time.monotonic() < deadline:
            time.sleep(0.01)
            state = manager.get(run["run_id"])
        assert state["status"] == "paused"
        assert state["progress"]["completed"] == 2

        resumed = manager.resume(run["run_id"])
        assert resumed["status"] == "queued"
        deadline = time.monotonic() + 5
        state = manager.get(run["run_id"])
        while state["status"] not in ("completed", "failed") and time.monotonic() < deadline:
            time.sleep(0.01)
            state = manager.get(run["run_id"])
        assert state["status"] == "completed"
        assert state["progress"]["completed"] == state["progress"]["total"] == 3
        assert invocation_configs == [["hybrid_max", "ppr", "fused"], ["fused"]]
        assert [event["seq"] for event in manager.results(run["run_id"], 0, 10)["events"]] == [1, 2, 3]
    finally:
        continue_first_attempt.set()
        manager.shutdown()


def test_parallel_batch_bounds_workers_and_commits_in_task_order(monkeypatch, tmp_path):
    import csv
    import json

    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 50, "top_k": 10}})
    monkeypatch.setattr(batch, "SEED_METHODS", ("hits",))
    monkeypatch.setattr(batch, "RANKINGS", ("hybrid_max",))
    active = maximum = 0
    lock = threading.Lock()
    calls = []

    def request(base, item, task, configs, benchmark):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            calls.append(item["id"])
        time.sleep(0.12 if item["id"] == "case0" else 0.02)
        with lock:
            active -= 1
        return {"results": [{**config, "ranked": [{"article": item["relevant_urls"][0], "score": 1.0}],
                              "diagnostics": {}, "retrieval_id": item["id"], "computation_reused": False}
                             for config in configs],
                "performance": {"optimized": {"wall_seconds": 0.1,
                                "counts": {"retrieval_calls": 1, "graph_builds": 0, "ppr_runs": 0}}}}

    monkeypatch.setattr(batch, "_evaluation_from_api", request)
    evaluations = [{"id": f"case{i}", "query": f"query{i}",
                   "relevant_urls": [f"https://g1.globo.com/{i}.ghtml"]} for i in range(5)]
    json_path, csv_path = tmp_path / "parallel.json", tmp_path / "parallel.csv"
    summary = batch.run_batch_evaluation(None, "http://localhost:5000", evaluations, json_path, csv_path,
                                         reuse=True, workers=2, presets=("rapido",), quorums=(0.7,),
                                         seed_methods=("hits",), rankings=("hybrid_max",))
    assert summary["completed_results"] == 5
    assert maximum == 2
    assert len(calls) == 5 and set(calls) == {f"case{i}" for i in range(5)}
    report = json.loads(json_path.read_text())
    assert [item["id"] for item in report["evaluations"]] == [f"case{i}" for i in range(5)]
    records = [json.loads(line) for line in json_path.with_suffix(".jsonl").read_text().splitlines()[1:]]
    assert [record["index"] for record in records] == list(range(5))
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert [row["id"] for row in csv.DictReader(stream)] == [f"case{i}" for i in range(5)]


def test_parallel_failure_resumes_from_ordered_checkpoint_prefix(monkeypatch, tmp_path):
    import csv

    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 50, "top_k": 10}})
    monkeypatch.setattr(batch, "SEED_METHODS", ("hits",))
    monkeypatch.setattr(batch, "RANKINGS", ("hybrid_max",))
    calls = []
    fail = True

    def request(base, item, task, configs, benchmark):
        calls.append(item["id"])
        if item["id"] == "case1" and fail:
            time.sleep(0.01)
            raise RuntimeError("simulated task failure")
        time.sleep(0.05 if item["id"] == "case0" else 0.01)
        return {"results": [{**config, "ranked": [{"article": item["relevant_urls"][0], "score": 1.0}],
                              "diagnostics": {}, "retrieval_id": item["id"], "computation_reused": False}
                             for config in configs],
                "performance": {"optimized": {"wall_seconds": 0.1,
                                "counts": {"retrieval_calls": 1, "graph_builds": 0, "ppr_runs": 0}}}}

    monkeypatch.setattr(batch, "_evaluation_from_api", request)
    evaluations = [{"id": f"case{i}", "query": f"query{i}",
                   "relevant_urls": [f"https://g1.globo.com/{i}.ghtml"]} for i in range(4)]
    json_path, csv_path = tmp_path / "resume-parallel.json", tmp_path / "resume-parallel.csv"
    options = dict(reuse=True, workers=2, presets=("rapido",), quorums=(0.7,),
                   seed_methods=("hits",), rankings=("hybrid_max",))
    with pytest.raises(RuntimeError, match="simulated task failure"):
        batch.run_batch_evaluation(None, "http://localhost:5000", evaluations, json_path, csv_path, **options)
    partial = json.loads(json_path.read_text())
    assert partial["completed_results"] == 1
    fail = False
    summary = batch.run_batch_evaluation(None, "http://localhost:5000", evaluations, json_path, csv_path,
                                         resume=True, **options)
    assert summary["completed_results"] == 4
    assert calls.count("case0") == 1
    assert calls.count("case1") == 2
    # case2 may have completed while case1 failed, but it was not checkpointed
    # out of order and is safely repeated on resume.
    assert calls.count("case2") == 2
    assert calls.count("case3") == 1
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert [row["id"] for row in csv.DictReader(stream)] == [f"case{i}" for i in range(4)]


@pytest.mark.parametrize("workers", [0, 17, True])
def test_worker_limit_must_be_between_one_and_sixteen(monkeypatch, tmp_path, workers):
    args = (None, "http://localhost:5000", [{"id": "case", "query": "query",
            "relevant_urls": ["https://g1.globo.com/a"]}], tmp_path / "bad.json", tmp_path / "bad.csv")
    with pytest.raises(ValueError, match="workers"):
        batch.run_batch_evaluation(*args, workers=workers)


def test_parallel_legacy_mode_also_obeys_worker_bound(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"rapido": {"limit": 50, "top_k": 10}})
    monkeypatch.setattr(batch, "SEED_METHODS", ("hits",))
    monkeypatch.setattr(batch, "RANKINGS", ("ppr",))
    active = maximum = 0
    lock = threading.Lock()

    def search(base, query, preset, seed, quorum, **options):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return [query]

    monkeypatch.setattr(batch, "_ranked_urls_from_api", search)
    evaluations = [{"id": f"case{i}", "query": f"url-{i}",
                   "relevant_urls": [f"https://g1.globo.com/{i}"]} for i in range(6)]
    json_path, csv_path = tmp_path / "legacy-parallel.json", tmp_path / "legacy-parallel.csv"
    summary = batch.run_batch_evaluation(None, "http://localhost:5000", evaluations, json_path, csv_path,
                                         reuse=False, workers=2, presets=("rapido",), quorums=(0.7,),
                                         seed_methods=("hits",), rankings=("ppr",))
    assert summary["completed_results"] == 6
    assert maximum == 2
    report = json.loads(json_path.read_text())
    assert [item["id"] for item in report["evaluations"]] == [f"case{i}" for i in range(6)]
