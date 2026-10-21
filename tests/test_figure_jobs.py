import io
import json

import pytest

from services import figure_jobs as figure_job_module
from services.figure_jobs import FigureJobManager, PROGRESS_PREFIX


class RecordingExecutor:
    def __init__(self, max_workers, thread_name_prefix):
        self.submissions = []

    def submit(self, fn, *args):
        self.submissions.append((fn, args))

    def shutdown(self, wait=True):
        pass


def manager(tmp_path, known_runs=("a1", "b2"), max_queued_jobs=4):
    instance = FigureJobManager(tmp_path, lambda run_id: {"run_id": run_id}
                                if run_id in known_runs else None,
                                max_queued_jobs=max_queued_jobs)
    instance._executor = RecordingExecutor(max_workers=1, thread_name_prefix="test")
    return instance


def test_submit_validates_run_selection_and_returns_queued_job(tmp_path):
    jobs = manager(tmp_path)
    job = jobs.submit(["a1", "b2"], formats=["pdf", "png"], baselines=["hybrid_max", "rrf"],
                      include_partial=True, include_ranking_overlap=False)
    assert job["status"] == "queued"
    assert job["run_ids"] == ["a1", "b2"]
    assert job["formats"] == ["pdf", "png"]
    assert job["include_partial"] is True
    assert "graph_hits" in job["rankings"]
    assert "query_entities" in job["seed_methods"]
    assert "overview" in job["figure_families"]
    assert len(jobs._executor.submissions) == 1


@pytest.mark.parametrize("runs,formats,baselines", [
    ([], ["pdf"], ["hybrid_max"]),
    (["missing"], ["pdf"], ["hybrid_max"]),
    (["a1", "a1"], ["pdf"], ["hybrid_max"]),
    (["a1"], ["exe"], ["hybrid_max"]),
    (["a1"], ["pdf"], ["not-a-ranking"]),
])
def test_submit_rejects_invalid_job_options(tmp_path, runs, formats, baselines):
    jobs = manager(tmp_path)
    with pytest.raises(ValueError):
        jobs.submit(runs, formats=formats, baselines=baselines)
    assert not jobs._executor.submissions


@pytest.mark.parametrize("kwargs", [
    {"rankings": []},
    {"rankings": ["not-a-ranking"]},
    {"seed_methods": ["invalid"]},
    {"rankings": ["graph_hits"], "seed_methods": []},
    {"figure_families": []},
    {"figure_families": ["unknown"]},
    {"filters": {"themes": [""]}},
    {"filters": {"quorums": [1.1]}},
    {"filters": {"other": ["x"]}},
])
def test_submit_rejects_invalid_method_or_scope_selection(tmp_path, kwargs):
    jobs = manager(tmp_path)
    with pytest.raises(ValueError):
        jobs.submit(["a1"], **kwargs)
    assert not jobs._executor.submissions


def test_job_queue_is_bounded(tmp_path):
    jobs = manager(tmp_path, max_queued_jobs=1)
    jobs.submit(["a1"])
    with pytest.raises(ValueError, match="queue is full"):
        jobs.submit(["b2"])


def test_progress_events_merge_loading_plotting_and_run_completion(tmp_path):
    jobs = manager(tmp_path)
    job = jobs.submit(["a1", "b2"])
    jobs._update_progress(job["job_id"], {
        "phase": "loading", "run_id": "a1", "run_index": 1, "run_total": 2,
        "loaded_rows": 250, "total_rows": 832,
    })
    loading = jobs.get(job["job_id"])["progress"]
    assert loading["current_run_id"] == "a1"
    assert loading["completed_runs"] == 0
    assert loading["loaded_rows"] == 250

    jobs._update_progress(job["job_id"], {
        "phase": "plotting", "run_id": "a1", "run_index": 1, "run_total": 2,
        "completed_tasks": 4, "total_tasks": 15, "current_task": "Qualidade dos rankings",
    })
    plotting = jobs.get(job["job_id"])["progress"]
    assert plotting["total_rows"] == 832  # Partial events retain prior phase details.
    assert plotting["completed_tasks"] == 4

    jobs._update_progress(job["job_id"], {
        "phase": "run_complete", "run_id": "a1", "run_index": 1, "run_total": 2,
    })
    complete = jobs.get(job["job_id"])["progress"]
    assert complete["completed_runs"] == 1
    assert complete["current_run_id"] is None


def test_worker_consumes_structured_events_and_tracks_zip_creation(monkeypatch, tmp_path):
    jobs = manager(tmp_path)
    job = jobs.submit(["a1"])
    job_id = job["job_id"]
    events = [
        {"phase": "loading", "run_id": "a1", "run_index": 1, "run_total": 1,
         "loaded_rows": 250, "total_rows": 832},
        {"phase": "plotting", "run_id": "a1", "run_index": 1, "run_total": 1,
         "completed_tasks": 3, "total_tasks": 14, "current_task": "Perfis por corte"},
        {"phase": "run_complete", "run_id": "a1", "run_index": 1, "run_total": 1,
         "completed_tasks": 14, "total_tasks": 14},
    ]
    lines = "".join(PROGRESS_PREFIX + json.dumps(event) + "\n" for event in events)

    class CompletedProcess:
        stdout = io.StringIO(lines)

        @staticmethod
        def wait():
            return 0

    captured_command = {}

    def fake_popen(command, **kwargs):
        captured_command["args"] = command
        output = tmp_path / job_id / "figures"
        (output / "manifest.json").write_text("{}")
        return CompletedProcess()

    monkeypatch.setattr(figure_job_module.subprocess, "Popen", fake_popen)
    observed = []
    original_update_progress = jobs._update_progress

    def capture_progress(current_job_id, event):
        observed.append(event.copy())
        original_update_progress(current_job_id, event)

    monkeypatch.setattr(jobs, "_update_progress", capture_progress)
    jobs._run(job_id)

    finished = jobs.get(job_id)
    assert finished["status"] == "completed"
    assert finished["progress"]["phase"] == "completed"
    assert finished["progress"]["package_files_done"] == 1
    assert finished["progress"]["package_seconds"] >= 0
    assert [event["phase"] for event in observed[:3]] == ["loading", "plotting", "run_complete"]
    assert any(event["phase"] == "packaging" for event in observed)
    assert jobs.download_path(job_id).is_file()
    command = captured_command["args"]
    assert command[command.index("--ranking") + 1] == "cross_encoder"
    assert "--seed-method" in command
    assert "--figure-family" in command


def test_worker_passes_selected_methods_families_and_scope_filters(monkeypatch, tmp_path):
    jobs = manager(tmp_path)
    job = jobs.submit(
        ["a1"], rankings=["graph_hits"], seed_methods=["query_entities"],
        baselines=[], figure_families=["graph"],
        filters={"themes": ["theme_a"], "quorums": [.3]},
    )
    job_id = job["job_id"]
    captured = {}

    class CompletedProcess:
        stdout = io.StringIO("")

        @staticmethod
        def wait():
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return CompletedProcess()

    monkeypatch.setattr(figure_job_module.subprocess, "Popen", fake_popen)
    jobs._run(job_id)
    command = captured["command"]
    assert command[command.index("--ranking") + 1] == "graph_hits"
    assert command[command.index("--seed-method") + 1] == "query_entities"
    assert command[command.index("--figure-family") + 1] == "graph"
    assert command[command.index("--filter-theme") + 1] == "theme_a"
    assert command[command.index("--filter-quorum") + 1] == "0.3"
