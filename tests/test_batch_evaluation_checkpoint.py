import copy
import codecs
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from services import batch_evaluation as batch
from services.batch_checkpoint import BatchStopped, output_lock


@pytest.fixture
def job(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "SEARCH_PRESETS", {"small": {"limit": 4, "top_k": 4}})
    monkeypatch.setattr(batch, "RANKINGS", ("ppr",))
    monkeypatch.setattr(batch, "QUORUM_VALUES", (0.3, 0.5))
    monkeypatch.setattr(batch, "SEED_METHODS", ("louvain", "hits"))
    monkeypatch.setattr(batch, "_validate_relevant_urls_exist", lambda *args: None)
    evaluations = [{"id": "case", "query": "short query", "relevant_urls": [
        "https://g1.globo.com/a", "https://g1.globo.com/b",
    ]}]
    calls = []

    def search(*args):
        calls.append(args)
        return [evaluations[0]["relevant_urls"][0]]

    monkeypatch.setattr(batch, "_ranked_urls_from_api", search)
    args = (None, "http://localhost:5000", evaluations, tmp_path / "run.json", tmp_path / "run.csv")
    return args, calls, search


def read_report(args):
    return json.loads(args[3].read_text())


def read_rows(args):
    with args[4].open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def test_portuguese_text_and_single_csv_bom_survive_live_append_and_resume(job, monkeypatch):
    args, calls, search = job
    query = "tarifaço — Benício, São Paulo e investigação"
    args[2][0].update(query=query, query_formulation="tema específico")

    def assert_csv(expected_count):
        raw = args[4].read_bytes()
        assert raw.startswith(codecs.BOM_UTF8)
        assert raw.count(codecs.BOM_UTF8) == 1
        assert query in raw.decode("utf-8-sig")
        rows = read_rows(args)
        assert len(rows) == expected_count
        assert all(row["id"] == "case" and row["query"] == query for row in rows)
        assert all(row["query_formulation"] == "tema específico" for row in rows)

    def stop_after_live_append(*search_args):
        if calls:
            assert_csv(1)
            raise KeyboardInterrupt()
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", stop_after_live_append)
    assert batch.run_batch_evaluation(*args)["status"] == "interrupted"
    assert_csv(1)
    checkpoint = args[3].with_suffix(".jsonl").read_bytes()

    def resume_and_check_append(*search_args):
        assert_csv(len(calls))
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", resume_and_check_append)
    assert batch.run_batch_evaluation(*args, resume=True)["status"] == "completed"
    assert_csv(4)
    assert args[3].with_suffix(".jsonl").read_bytes().startswith(checkpoint)
    for path in (args[3], args[3].with_suffix(".jsonl")):
        raw = path.read_bytes()
        assert not raw.startswith(codecs.BOM_UTF8)
        assert query in raw.decode("utf-8")
    assert read_report(args)["evaluations"][0]["query"] == query


def test_live_results_are_on_disk_before_next_request(job, monkeypatch, capsys):
    args, calls, search = job

    def checking_search(*search_args):
        if calls:
            assert len(read_rows(args)) == len(calls)
            assert len(args[3].with_suffix(".jsonl").read_bytes().splitlines()) == len(calls) + 1
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", checking_search)
    # The runner must never accumulate an in-memory report for CSV conversion.
    monkeypatch.setattr(batch, "_csv_rows", lambda *a: pytest.fail("runner must stream"))
    summary = batch.run_batch_evaluation(*args)
    assert summary["completed_results"] == 4
    assert len(read_rows(args)) == 4
    assert read_report(args)["status"] == "completed"
    output = capsys.readouterr().out
    assert "Saved case / small / ranking=ppr / louvain / quorum=0.3" in output


def test_failure_then_resume_skips_saved_configurations(job, monkeypatch):
    args, calls, search = job

    def failing_search(*search_args):
        if len(calls) == 2:
            raise RuntimeError("API unavailable")
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", failing_search)
    with pytest.raises(RuntimeError, match="API unavailable"):
        batch.run_batch_evaluation(*args)
    partial = read_report(args)
    saved = partial["evaluations"][0]["results"]
    assert partial["status"] == "failed"
    assert partial["completed_results"] == len(saved) == len(read_rows(args)) == 2
    monkeypatch.setattr(batch, "_ranked_urls_from_api", search)
    summary = batch.run_batch_evaluation(*args, resume=True)
    assert summary["completed_results"] == len(calls) == 4
    assert read_report(args)["evaluations"][0]["results"][:2] == saved
    assert len(read_rows(args)) == 4
    batch.run_batch_evaluation(*args, resume=True)
    assert len(calls) == 4  # A completed batch only rebuilds exports.


def test_printed_elapsed_and_eta_restart_from_new_samples_on_resume(job, monkeypatch, capsys):
    args, calls, search = job
    clock = [0.0]
    monkeypatch.setattr(batch.time, "monotonic", lambda: clock[0])

    def first_session(*search_args):
        if len(calls) == 2:
            raise KeyboardInterrupt()
        clock[0] += 10
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", first_session)
    batch.run_batch_evaluation(*args)
    output = capsys.readouterr().out
    first_saved = next(line for line in output.splitlines() if "[1/4] Saved" in line)
    assert "Elapsed: 00:00:10 | Remaining: ~00:00:30" in first_saved

    clock[0] = 1000  # Downtime is not included in the next session.

    def resumed_session(*search_args):
        clock[0] += 20
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", resumed_session)
    batch.run_batch_evaluation(*args, resume=True)
    output = capsys.readouterr().out
    assert "Elapsed: 00:00:00 | Remaining: calculating" in output.splitlines()[0]
    third_saved = next(line for line in output.splitlines() if "[3/4] Saved" in line)
    assert "Elapsed: 00:00:20 | Remaining: ~00:00:20" in third_saved
    assert "Elapsed: 00:00:40 | Remaining: 00:00:00" in output.splitlines()[-1]
    assert len(calls) == 4


@pytest.mark.parametrize("stop", [KeyboardInterrupt(), BatchStopped(signal.SIGTERM)])
def test_graceful_stop_and_resume(job, monkeypatch, stop):
    args, calls, search = job

    def stopping_search(*search_args):
        if calls:
            raise stop
        return search(*search_args)

    monkeypatch.setattr(batch, "_ranked_urls_from_api", stopping_search)
    summary = batch.run_batch_evaluation(*args)
    assert summary["status"] == "interrupted"
    assert summary["stop_signal"] == getattr(stop, "signum", signal.SIGINT)
    assert summary["completed_results"] == len(read_rows(args)) == 1
    # Simulate an out-of-sync / truncated CSV. The journal is authoritative.
    args[4].write_text("broken CSV\nunfinished", encoding="utf-8")
    monkeypatch.setattr(batch, "_ranked_urls_from_api", search)
    batch.run_batch_evaluation(*args, resume=True)
    assert len(calls) == len(read_rows(args)) == 4


@pytest.mark.parametrize("tail", [b'{"type":"res', b'\xf0\x9f', b'{"complete":true}'])
def test_only_unterminated_final_line_is_recovered(job, tail):
    args, calls, _ = job
    batch.run_batch_evaluation(*args)
    path = args[3].with_suffix(".jsonl")
    original = path.read_bytes()
    with path.open("ab") as stream:
        stream.write(tail)
    batch.run_batch_evaluation(*args, resume=True)
    assert path.read_bytes() == original
    assert len(calls) == 4


@pytest.mark.parametrize("line_index", [1, 4])
def test_corrupt_complete_records_are_rejected_without_modification(job, line_index):
    args, calls, _ = job
    batch.run_batch_evaluation(*args)
    path = args[3].with_suffix(".jsonl")
    lines = path.read_bytes().splitlines(keepends=True)
    record = json.loads(lines[line_index])
    record["result"]["ranked_urls"] = []  # Valid JSON, invalid integrity checksum.
    lines[line_index] = (json.dumps(record) + "\n").encode()
    damaged = b"".join(lines)
    path.write_bytes(damaged)
    with pytest.raises(ValueError, match="corrupt checkpoint"):
        batch.run_batch_evaluation(*args, resume=True)
    assert path.read_bytes() == damaged
    assert len(calls) == 4


@pytest.mark.parametrize("change", ["query", "urls", "api", "settings", "ks"])
def test_resume_requires_matching_input_and_search_settings(job, monkeypatch, change):
    args, calls, _ = job
    batch.run_batch_evaluation(*args)
    changed = list(copy.deepcopy(args))
    if change == "query":
        changed[2][0]["query"] = "other query"
    elif change == "urls":
        changed[2][0]["relevant_urls"].reverse()
    elif change == "api":
        changed[1] = "http://other-server:5000"
    elif change == "settings":
        monkeypatch.setattr(batch, "QUORUM_VALUES", (0.9,))
    else:
        monkeypatch.setattr(batch, "BATCH_KS", (1, 10))
    original = args[3].with_suffix(".jsonl").read_bytes()
    with pytest.raises(ValueError, match="does not match"):
        batch.run_batch_evaluation(*changed, resume=True)
    assert args[3].with_suffix(".jsonl").read_bytes() == original
    assert len(calls) == 4


def test_checkpoint_is_protected_even_if_exports_are_missing(job):
    args, calls, _ = job
    batch.run_batch_evaluation(*args)
    args[3].unlink()
    args[4].unlink()
    with pytest.raises(FileExistsError, match="--resume"):
        batch.run_batch_evaluation(*args)
    with output_lock(args[3]):
        with pytest.raises(RuntimeError, match="another batch"):
            batch.run_batch_evaluation(*args, overwrite=True)
    batch.run_batch_evaluation(*args, resume=True)
    assert len(calls) == 4
    assert len(read_rows(args)) == 4


def test_explicit_overwrite_starts_a_fresh_journal(job):
    args, calls, _ = job
    batch.run_batch_evaluation(*args)
    batch.run_batch_evaluation(*args, overwrite=True)
    assert len(calls) == 8
    assert len(args[3].with_suffix(".jsonl").read_bytes().splitlines()) == 5


def test_resume_requires_a_journal_and_cannot_overwrite(job):
    args, _, _ = job
    with pytest.raises(ValueError, match="checkpoint not found"):
        batch.run_batch_evaluation(*args, resume=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        batch.run_batch_evaluation(*args, resume=True, overwrite=True)


def test_interruption_between_journal_and_csv_never_repeats_saved_search(job, monkeypatch):
    args, calls, _ = job
    original = batch._csv_row
    stopped = False

    def interrupt_once(*row_args):
        nonlocal stopped
        if not stopped:
            stopped = True
            raise KeyboardInterrupt()
        return original(*row_args)

    monkeypatch.setattr(batch, "_csv_row", interrupt_once)
    summary = batch.run_batch_evaluation(*args)
    assert summary["completed_results"] == len(read_rows(args)) == 1
    batch.run_batch_evaluation(*args, resume=True)
    assert len(calls) == len(read_rows(args)) == 4


def test_multiple_evaluations_export_in_input_order(job):
    args, calls, _ = job
    args[2].append({**args[2][0], "id": "second"})
    batch.run_batch_evaluation(*args)
    report = read_report(args)
    assert [item["id"] for item in report["evaluations"]] == ["case", "second"]
    assert [len(item["results"]) for item in report["evaluations"]] == [4, 4]
    assert len(calls) == len(read_rows(args)) == 8


def test_sigterm_is_deferred_until_journal_and_csv_commit(job, monkeypatch):
    args, calls, _ = job
    original = batch.ResultJournal.append

    def signal_during_append(self, *append_args):
        if self.completed == 0:
            signal.raise_signal(signal.SIGTERM)
        original(self, *append_args)

    monkeypatch.setattr(batch.ResultJournal, "append", signal_during_append)
    summary = batch.run_batch_evaluation(*args)
    assert summary["status"] == "interrupted"
    assert summary["completed_results"] == len(calls) == len(read_rows(args)) == 1
    batch.run_batch_evaluation(*args, resume=True)
    assert len(calls) == 4


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM, signal.SIGKILL])
def test_real_process_signals_save_progress_and_exit_cleanly(tmp_path, signum):
    code = '''
import json, signal, sys
from pathlib import Path
from services import batch_evaluation as b
b.SEARCH_PRESETS = {"small": {"limit": 4, "top_k": 4}}
b.QUORUM_VALUES = (0.3,)
b.SEED_METHODS = ("louvain", "hits")
b.RANKINGS = ("ppr",)
b._validate_relevant_urls_exist = lambda *a: None
count = 0
resume = len(sys.argv) > 2
def search(*args):
    global count
    count += 1
    if count == 2 and not resume:
        print("WAITING_FOR_SIGNAL", flush=True)
        signal.pause()
    return []
b._ranked_urls_from_api = search
root = Path(sys.argv[1])
summary = b.run_batch_evaluation(None, "http://localhost:5000",
    [{"id": "case", "query": "test", "relevant_urls": ["https://g1.globo.com/a"]}],
    root / "run.json", root / "run.csv", resume=resume)
sys.exit(128 + summary["stop_signal"] if summary["stop_signal"] else 0)
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    try:
        # Wait for explicit readiness, not an arbitrary sleep or server dependency.
        while True:
            line = process.stdout.readline()
            assert line, process.stderr.read()
            if "WAITING_FOR_SIGNAL" in line:
                break
        process.send_signal(signum)
        _, stderr = process.communicate(timeout=10)
        expected_code = -signum if signum == signal.SIGKILL else 128 + signum
        assert process.returncode == expected_code, stderr
        report = json.loads((tmp_path / "run.json").read_text())
        if signum == signal.SIGKILL:
            assert report["status"] == "running"  # Last exported view can be stale.
        else:
            assert report["status"] == "interrupted"
            assert report["completed_results"] == 1
        assert len((tmp_path / "run.jsonl").read_bytes().splitlines()) == 2
        first_record = (tmp_path / "run.jsonl").read_bytes().splitlines()[1]
        restarted = subprocess.run(
            [sys.executable, "-u", "-c", code, str(tmp_path), "resume"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert restarted.returncode == 0, restarted.stderr
        final = json.loads((tmp_path / "run.json").read_text())
        assert final["status"] == "completed"
        assert final["completed_results"] == 2
        assert (tmp_path / "run.jsonl").read_bytes().splitlines()[1] == first_record
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
