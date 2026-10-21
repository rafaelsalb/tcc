"""In-process background jobs that invoke the persisted-run figure pipeline."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import subprocess
import sys
import threading
import time
from uuid import uuid4
import zipfile


RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SUPPORTED_FORMATS = {"pdf", "png", "svg"}
SUPPORTED_RANKINGS = {
    "ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr",
    "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion",
    "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf",
}
SEED_INDEPENDENT_RANKINGS = {"hybrid_max", "rrf", "cross_encoder", "lexical", "vector"}
GRAPH_RANKINGS = SUPPORTED_RANKINGS - SEED_INDEPENDENT_RANKINGS
SUPPORTED_SEED_METHODS = {"louvain", "hits", "ppr_top10", "query_entities"}
SUPPORTED_FIGURE_FAMILIES = {
    "overview", "comparisons", "graph", "cutoff", "tail", "theme", "runtime", "overlap",
}
DEFAULT_FIGURE_FAMILIES = SUPPORTED_FIGURE_FAMILIES - {"overlap"}
FILTER_KEYS = {"themes", "formulations", "presets", "quorums", "evaluation_ids"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROGRESS_PREFIX = "FIGURE_PROGRESS "


class FigureJobManager:
    """Run the figure CLI off-request and expose progress and a ZIP artifact.

    Job state is process-local, like the existing evaluation-job manager. Figure
    output files remain under the configured output directory after job state
    expires. Only one figure process runs at a time to bound database pressure.
    """

    def __init__(self, output_directory, run_exists, retention_seconds=24 * 60 * 60,
                 max_queued_jobs=4):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.run_exists = run_exists
        self.retention_seconds = retention_seconds
        self.max_queued_jobs = max_queued_jobs
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evaluation-figures")
        self._jobs = {}
        self._lock = threading.Lock()

    def submit(self, run_ids, formats=None, baselines=None, include_partial=False,
               include_ranking_overlap=False, rankings=None, seed_methods=None,
               filters=None, figure_families=None):
        if not isinstance(run_ids, list) or not run_ids:
            raise ValueError("Select at least one saved evaluation run.")
        if len(run_ids) > 12:
            raise ValueError("Select no more than 12 runs per figure job.")
        if any(not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id) for run_id in run_ids):
            raise ValueError("One or more run IDs are invalid.")
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("A run may only be selected once.")
        missing = [run_id for run_id in run_ids if self.run_exists(run_id) is None]
        if missing:
            raise ValueError(f"Unknown saved run(s): {', '.join(missing)}")

        formats = formats if formats is not None else ["pdf", "png", "svg"]
        if (not isinstance(formats, list) or not formats or len(set(formats)) != len(formats)
                or any(fmt not in SUPPORTED_FORMATS for fmt in formats)):
            raise ValueError("Formats must be a non-empty subset of pdf, png, and svg.")
        baselines = baselines if baselines is not None else ["hybrid_max"]
        if (not isinstance(baselines, list)
                or any(not isinstance(name, str) or name not in SUPPORTED_RANKINGS
                       for name in baselines)
                or len(set(baselines)) != len(baselines)):
            raise ValueError("Select valid paired-comparison reference rankings.")
        if not isinstance(include_partial, bool) or not isinstance(include_ranking_overlap, bool):
            raise ValueError("Partial and overlap options must be boolean values.")
        rankings = rankings if rankings is not None else sorted(SUPPORTED_RANKINGS)
        if (not isinstance(rankings, list) or not rankings
                or any(not isinstance(name, str) for name in rankings)
                or len(set(rankings)) != len(rankings)
                or any(name not in SUPPORTED_RANKINGS for name in rankings)):
            raise ValueError("Select one or more valid ranking methods.")
        seed_methods = seed_methods if seed_methods is not None else sorted(SUPPORTED_SEED_METHODS)
        if (not isinstance(seed_methods, list)
                or any(not isinstance(name, str) for name in seed_methods)
                or len(set(seed_methods)) != len(seed_methods)
                or any(name not in SUPPORTED_SEED_METHODS for name in seed_methods)):
            raise ValueError("Select valid graph seeding methods.")
        if (set(rankings) | set(baselines)) & GRAPH_RANKINGS and not seed_methods:
            raise ValueError("Select at least one seed method for the selected graph rankings.")
        figure_families = figure_families if figure_families is not None else sorted(DEFAULT_FIGURE_FAMILIES)
        if (not isinstance(figure_families, list) or not figure_families
                or any(not isinstance(name, str) for name in figure_families)
                or len(set(figure_families)) != len(figure_families)
                or any(name not in SUPPORTED_FIGURE_FAMILIES for name in figure_families)):
            raise ValueError("Select one or more valid figure families.")
        if include_ranking_overlap and "overlap" not in figure_families:
            figure_families.append("overlap")
        filters = filters if filters is not None else {}
        if not isinstance(filters, dict) or set(filters) - FILTER_KEYS:
            raise ValueError("One or more figure filters are invalid.")
        normalized_filters = {}
        for key in FILTER_KEYS:
            values = filters.get(key, [])
            if key == "quorums":
                if (not isinstance(values, list) or any(isinstance(value, bool) for value in values)):
                    raise ValueError("Quorum filters must be a list of numbers.")
                try:
                    values = [float(value) for value in values]
                except (TypeError, ValueError) as exc:
                    raise ValueError("Quorum filters must be a list of numbers.") from exc
                if any(value < 0 or value > 1 for value in values):
                    raise ValueError("Quorum filters must be between 0 and 1.")
            else:
                if (not isinstance(values, list)
                        or any(not isinstance(value, str) for value in values)):
                    raise ValueError(f"{key} figure filters must be a list of strings.")
                values = [value.strip() for value in values]
                if any(not value or len(value) > 256 for value in values):
                    raise ValueError(f"{key} figure filter values must be 1–256 characters.")
            if len(values) > 500 or len(set(values)) != len(values):
                raise ValueError(f"{key} figure filters must contain at most 500 unique values.")
            normalized_filters[key] = values

        with self._lock:
            self._remove_expired_locked()
            active = sum(job["status"] in ("queued", "running") for job in self._jobs.values())
            if active >= self.max_queued_jobs:
                raise ValueError("The figure-generation queue is full; try again later.")
            job_id = uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            state = {
                "job_id": job_id,
                "status": "queued",
                "created_at": now,
                "started_at": None,
                "updated_at": now,
                "run_ids": list(run_ids),
                "formats": list(formats),
                "baselines": list(baselines),
                "rankings": list(rankings),
                "seed_methods": list(seed_methods),
                "figure_families": list(figure_families),
                "filters": normalized_filters,
                "include_partial": bool(include_partial),
                "include_ranking_overlap": bool(include_ranking_overlap),
                "progress": {"phase": "queued", "run_index": 0, "run_total": len(run_ids),
                             "completed_runs": 0, "current_run_id": None,
                             "loaded_rows": 0, "total_rows": None,
                             "completed_tasks": 0, "total_tasks": None,
                             "current_task": None, "subtask_completed": None,
                             "subtask_total": None, "current_subtask": None,
                             "package_files_done": 0,
                             "package_files_total": None, "current_file": None},
                "error": None,
                "_updated_monotonic": time.monotonic(),
                "_directory": str(self.output_directory / job_id),
                "_download_path": None,
            }
            self._jobs[job_id] = state
            self._executor.submit(self._run, job_id)
        return self.get(job_id)

    def _run(self, job_id):
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            state["status"] = "running"
            now = datetime.now(timezone.utc).isoformat()
            state["started_at"] = now
            state["updated_at"] = now
            state["progress"]["phase"] = "starting"
            state["_updated_monotonic"] = time.monotonic()
            options = deepcopy(state)

        job_directory = self.output_directory / job_id
        output_directory = job_directory / "figures"
        output_tail = deque(maxlen=40)
        current_run_index = 0
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, "-u", "scripts/generate_evaluation_figures.py",
                       "--output-dir", str(output_directory), "--format", *options["formats"],
                       "--progress-jsonl"]
            for run_id in options["run_ids"]:
                command.extend(("--run-id", run_id))
            for baseline in options["baselines"]:
                command.extend(("--baseline-ranking", baseline))
            for ranking in options["rankings"]:
                command.extend(("--ranking", ranking))
            for seed_method in options["seed_methods"]:
                command.extend(("--seed-method", seed_method))
            for figure_family in options["figure_families"]:
                command.extend(("--figure-family", figure_family))
            filter_flags = {
                "themes": "--filter-theme", "formulations": "--filter-formulation",
                "presets": "--filter-preset", "quorums": "--filter-quorum",
                "evaluation_ids": "--filter-evaluation-id",
            }
            for key, flag in filter_flags.items():
                for value in options["filters"][key]:
                    command.extend((flag, str(value)))
            if options["include_partial"]:
                command.append("--include-partial")
            if options["include_ranking_overlap"]:
                command.append("--include-ranking-overlap")

            process = subprocess.Popen(
                command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(PROGRESS_PREFIX):
                    try:
                        event = json.loads(line[len(PROGRESS_PREFIX):])
                    except json.JSONDecodeError:
                        output_tail.append(line)
                    else:
                        current_run_index = max(current_run_index, int(event.get("run_index") or 0))
                        self._update_progress(job_id, event)
                else:
                    output_tail.append(line)

            return_code = process.wait()
            if return_code != 0:
                details = "\n".join(output_tail)
                raise RuntimeError(f"Figure generation failed (exit {return_code}).\n{details}")

            archive_path = job_directory / "figures.zip"
            files = sorted(path for path in output_directory.rglob("*") if path.is_file())
            package_started = time.monotonic()
            self._update_progress(job_id, {"phase": "packaging", "current_run_id": None,
                                           "current_task": None, "package_files_done": 0,
                                           "package_files_total": len(files), "current_file": None})
            # PNG/PDF are already compressed; level 1 keeps SVG compression
            # useful while avoiding spending excessive CPU on the archive.
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=1) as archive:
                for file_index, path in enumerate(files, start=1):
                    relative_path = path.relative_to(output_directory).as_posix()
                    self._update_progress(job_id, {"phase": "packaging", "current_run_id": None,
                                                   "current_task": None,
                                                   "package_files_done": file_index - 1,
                                                   "package_files_total": len(files),
                                                   "current_file": relative_path})
                    archive.write(path, relative_path)
                    self._update_progress(job_id, {"phase": "packaging", "current_run_id": None,
                                                   "current_task": None,
                                                   "package_files_done": file_index,
                                                   "package_files_total": len(files),
                                                   "current_file": None})
            packaging_seconds = time.monotonic() - package_started
            self._update(job_id, status="completed", progress={
                "phase": "completed", "run_index": len(options["run_ids"]),
                "run_total": len(options["run_ids"]), "completed_runs": len(options["run_ids"]),
                "current_run_id": None, "current_task": None, "current_file": None,
                "package_files_done": len(files), "package_files_total": len(files),
                "package_seconds": packaging_seconds,
            }, _download_path=str(archive_path))
        except Exception as exc:
            last_progress = self.get(job_id) or {}
            failed_phase = (last_progress.get("progress") or {}).get("phase")
            self._update(job_id, status="failed", error=str(exc), progress={
                "phase": "failed", "failed_phase": failed_phase,
                "run_index": current_run_index,
                "run_total": len(options["run_ids"]), "current_run_id": None,
                "current_task": None,
            })

    def _update_progress(self, job_id, event):
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            event = dict(event)
            event_run_id = event.pop("run_id", None)
            if event.get("phase") == "run_complete":
                event["current_run_id"] = None
            elif event_run_id:
                event["current_run_id"] = event_run_id
            progress = state.setdefault("progress", {})
            progress.update(event)
            run_index = int(progress.get("run_index") or 0)
            progress["completed_runs"] = max(int(progress.get("completed_runs") or 0), run_index - 1)
            if progress.get("phase") == "run_complete":
                progress["completed_runs"] = max(int(progress.get("completed_runs") or 0), run_index)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            state["_updated_monotonic"] = time.monotonic()

    def _update(self, job_id, **updates):
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            if "progress" in updates:
                progress = {**state.get("progress", {}), **updates["progress"]}
                updates["progress"] = progress
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

    def download_path(self, job_id):
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None or state.get("status") != "completed":
                return None
            path = state.get("_download_path")
        if not path:
            return None
        archive = self.output_directory / job_id / "figures.zip"
        return archive if archive.is_file() and str(archive) == path else None

    def _remove_expired_locked(self):
        now = time.monotonic()
        expired = [job_id for job_id, state in self._jobs.items()
                   if state["status"] in ("completed", "failed")
                   and now - state["_updated_monotonic"] > self.retention_seconds]
        for job_id in expired:
            del self._jobs[job_id]

    def shutdown(self, wait=True):
        self._executor.shutdown(wait=wait)
