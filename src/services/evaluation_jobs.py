"""In-process background jobs for long-running batch evaluations."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
from uuid import uuid4

from services.batch_search import _validate, evaluate_request


class EvaluationJobManager:
    """Run evaluations off-request and expose thread-safe progress snapshots.

    Jobs are intentionally serialized by default to avoid making expensive
    retrieval/ranking requests compete for database, model, and Spotlight
    resources. State is process-local and expires after ``retention_seconds``.
    """

    def __init__(self, max_workers=1, retention_seconds=24 * 60 * 60):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="evaluation-job")
        self._retention_seconds = retention_seconds
        self._jobs = {}
        self._lock = threading.Lock()

    def submit(self, searcher, ranker, body):
        configurations = _validate(body)
        job_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "progress": {"phase": "queued", "activity": "queued", "completed": 0,
                         "total": len(configurations), "configuration": None},
            "result": None,
            "error": None,
            "_updated_monotonic": time.monotonic(),
        }
        with self._lock:
            self._remove_expired_locked()
            self._jobs[job_id] = state
        future = self._executor.submit(self._run, job_id, searcher, ranker, deepcopy(body))
        with self._lock:
            self._jobs[job_id]["_future"] = future
        return job_id

    def _run(self, job_id, searcher, ranker, body):
        self._update(job_id, status="running", progress={
            "phase": "optimized", "activity": "starting", "completed": 0,
            "total": len(body["configurations"]) * (2 if body.get("benchmark", False) else 1),
            "configuration": None,
        })

        def progress_callback(progress):
            self._update(job_id, status="running", progress=progress)

        try:
            result = evaluate_request(searcher, ranker, body, progress_callback=progress_callback)
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
            return
        self._update(job_id, status="completed", result=result, progress={
            "phase": "completed", "activity": "completed",
            "completed": len(body["configurations"]) * (2 if body.get("benchmark", False) else 1),
            "total": len(body["configurations"]) * (2 if body.get("benchmark", False) else 1),
            "configuration": None,
        })

    def _update(self, job_id, **updates):
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            state.update(updates)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            state["_updated_monotonic"] = time.monotonic()

    def get(self, job_id):
        with self._lock:
            self._remove_expired_locked()
            state = self._jobs.get(job_id)
            if state is None:
                return None
            return {key: deepcopy(value) for key, value in state.items() if not key.startswith("_")}

    def _remove_expired_locked(self):
        now = time.monotonic()
        expired = [job_id for job_id, state in self._jobs.items()
                   if state["status"] in ("completed", "failed")
                   and now - state["_updated_monotonic"] > self._retention_seconds]
        for job_id in expired:
            del self._jobs[job_id]

    def shutdown(self, wait=True):
        self._executor.shutdown(wait=wait)
