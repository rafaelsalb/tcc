"""Durable, incremental batch runs used by the browser evaluation dashboard."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import threading
import time
from uuid import uuid4

from sqlalchemy import text

from services.batch_search import evaluate_request
from services.batch_evaluation import (
    BATCH_KS, QUERY_SEED_FALLBACKS, RANKINGS, SEARCH_PRESETS, SEED_METHODS,
    SEARCH_WINDOW, SHARED_SEARCH_SETTINGS, _coverage, _metrics_at_ks,
    _ranking_metrics, _select_methods, _validate_relevant_urls_exist,
    load_evaluation_file, validate_document,
)
from services.batch_summary import LiveSummary
from services.search_pipeline import ENSEMBLE_COMPONENT_RANKINGS, ENSEMBLE_RANKINGS
from services.search_pipeline import SEARCH_VERSION
import platform
import sys


def available_evaluation_sets(directory):
    """List theme-level sets from valid bundled JSON files."""
    root = Path(directory).resolve()
    available = []
    for path in sorted(root.glob("evals*.json")):
        try:
            evaluations = load_evaluation_file(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        grouped = {}
        for item in evaluations:
            theme = item["id"].split("__", 1)[0]
            grouped.setdefault(theme, []).append(item)
        for theme, items in grouped.items():
            set_id = f"{path.name}::{theme}"
            available.append({"id": set_id, "label": theme, "source": path.name,
                              "count": len(items), "articles": len(items[0]["relevant_urls"])})
    return available


def _snapshot_version(snapshot):
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


class DashboardRunManager:
    """Dashboard run manager; PostgreSQL is the only persistent run store."""

    def __init__(self, searcher, ranker, engine, evaluations_directory, *, recover_interrupted=True):
        self.searcher = searcher
        self.ranker = ranker
        self.engine = engine
        self.evaluations_directory = Path(evaluations_directory).resolve()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashboard-run")
        self._runs = {}
        self._lock = threading.RLock()
        self._db_enabled = engine is not None
        self.recover_interrupted = recover_interrupted
        # Used only by isolated unit tests that deliberately construct the manager
        # without a database. Production never persists run data in process memory.
        self._memory_runs = {}
        self._memory_results = {}
        self._memory_artifacts = {}
        self._memory_sets = {}
        if self._db_enabled:
            self._initialize_database()
            self._sync_evaluation_sets()
        self._load_existing_runs()

    def _initialize_database(self):
        """Create additive evaluation tables without touching the application schema."""
        statements = (
            """CREATE TABLE IF NOT EXISTS evaluation_sets (
                set_id TEXT NOT NULL, version TEXT NOT NULL, label TEXT NOT NULL,
                source_file TEXT NOT NULL, snapshot JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (set_id, version))""",
            """CREATE TABLE IF NOT EXISTS evaluation_set_queries (
                set_id TEXT NOT NULL, version TEXT NOT NULL, evaluation_id TEXT NOT NULL,
                query TEXT NOT NULL, query_formulation TEXT NOT NULL,
                PRIMARY KEY (set_id, version, evaluation_id),
                FOREIGN KEY (set_id, version) REFERENCES evaluation_sets(set_id, version))""",
            """CREATE TABLE IF NOT EXISTS evaluation_set_articles (
                set_id TEXT NOT NULL, version TEXT NOT NULL, position INTEGER NOT NULL,
                article_url TEXT NOT NULL REFERENCES g1_articles(url),
                PRIMARY KEY (set_id, version, position),
                UNIQUE (set_id, version, article_url),
                FOREIGN KEY (set_id, version) REFERENCES evaluation_sets(set_id, version))""",
            """CREATE TABLE IF NOT EXISTS evaluation_runs (
                run_id TEXT PRIMARY KEY, set_id TEXT NOT NULL, set_version TEXT NOT NULL,
                dataset TEXT NOT NULL, dataset_snapshot JSONB NOT NULL,
                settings JSONB NOT NULL, state JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS evaluation_run_results (
                run_id TEXT NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
                seq INTEGER NOT NULL, evaluation_id TEXT NOT NULL,
                payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, seq))""",
            """CREATE TABLE IF NOT EXISTS evaluation_run_artifacts (
                run_id TEXT NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
                artifact_key TEXT NOT NULL, payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, artifact_key))""",
        )
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    @staticmethod
    def _theme_snapshot(items):
        return {"schema_version": 1, "evaluations": items}

    def _sync_evaluation_sets(self):
        for info in available_evaluation_sets(self.evaluations_directory):
            filename, theme = info["id"].split("::", 1)
            evaluations = load_evaluation_file(self.evaluations_directory / filename)
            subset = [item for item in evaluations if item["id"].split("__", 1)[0] == theme]
            snapshot = self._theme_snapshot(subset)
            encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            version = _snapshot_version(snapshot)
            with self.engine.begin() as connection:
                connection.execute(text("""INSERT INTO evaluation_sets
                    (set_id, version, label, source_file, snapshot)
                    VALUES (:set_id, :version, :label, :source_file, CAST(:snapshot AS jsonb))
                    ON CONFLICT (set_id, version) DO NOTHING"""), {
                        "set_id": info["id"], "version": version, "label": theme,
                        "source_file": filename, "snapshot": encoded,
                    })
                connection.execute(text("""INSERT INTO evaluation_set_queries
                    (set_id, version, evaluation_id, query, query_formulation)
                    VALUES (:set_id, :version, :evaluation_id, :query, :formulation)
                    ON CONFLICT (set_id, version, evaluation_id) DO NOTHING"""), [
                        {"set_id": info["id"], "version": version, "evaluation_id": item["id"],
                         "query": item["query"], "formulation": item.get("query_formulation", "unspecified")}
                        for item in subset
                    ])
                if subset:
                    connection.execute(text("""INSERT INTO evaluation_set_articles
                        (set_id, version, position, article_url)
                        VALUES (:set_id, :version, :position, :url)
                        ON CONFLICT (set_id, version, position) DO NOTHING"""), [
                            {"set_id": info["id"], "version": version, "position": position, "url": url}
                            for position, url in enumerate(subset[0]["relevant_urls"])
                        ])

    def available_sets(self):
        sets = available_evaluation_sets(self.evaluations_directory)
        current_versions = {}
        for info in sets:
            filename, theme = info["id"].split("::", 1)
            evaluations = load_evaluation_file(self.evaluations_directory / filename)
            snapshot = self._theme_snapshot([
                item for item in evaluations if item["id"].split("__", 1)[0] == theme
            ])
            current_versions[(info["id"], _snapshot_version(snapshot))] = True
        if not self._db_enabled:
            for info in sets:
                filename, theme = info["id"].split("::", 1)
                evaluations = load_evaluation_file(self.evaluations_directory / filename)
                snapshot = self._theme_snapshot([
                    item for item in evaluations if item["id"].split("__", 1)[0] == theme
                ])
                version = _snapshot_version(snapshot)
                info["version"] = version
                info["id"] = f"{info['id']}::{version}"
                info["is_current"] = True
                info["version_label"] = "Atual"
                self._memory_sets[(info["id"].rsplit("::", 1)[0], version)] = snapshot
            return sets
        with self.engine.connect() as connection:
            rows = connection.execute(text("""SELECT set_id, version, label, source_file,
                jsonb_array_length(snapshot->'evaluations') AS count,
                jsonb_array_length(snapshot->'evaluations'->0->'relevant_urls') AS articles,
                created_at
                FROM evaluation_sets ORDER BY label, version""")).mappings().all()
        result = []
        for row in rows:
            is_current = (row["set_id"], row["version"]) in current_versions
            created_at = row["created_at"]
            version_label = "Atual" if is_current else (
                f"Snapshot de {created_at.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}"
                if created_at else "Snapshot anterior")
            result.append({"id": f"{row['set_id']}::{row['version']}", "version": row["version"],
                           "label": row["label"], "source": row["source_file"],
                           "count": row["count"], "articles": row["articles"],
                           "is_current": is_current, "version_label": version_label})
        return result

    def _dataset_snapshot(self, dataset_id):
        if "::" in dataset_id:
            parts = dataset_id.split("::")
            version = parts[-1] if len(parts) == 3 else None
            filename, theme = parts[0], parts[1]
            set_id = f"{filename}::{theme}"
            if version and self._db_enabled:
                with self.engine.connect() as connection:
                    value = connection.execute(text("""SELECT snapshot FROM evaluation_sets
                        WHERE set_id=:set_id AND version=:version"""),
                        {"set_id": set_id, "version": version}).scalar_one_or_none()
                if value is not None:
                    return value, set_id
            if version and (set_id, version) in self._memory_sets:
                return self._memory_sets[(set_id, version)], set_id
            if Path(filename).name != filename:
                raise ValueError("unknown evaluation set")
            evaluations = load_evaluation_file(self.evaluations_directory / filename)
            subset = [item for item in evaluations if item["id"].split("__", 1)[0] == theme]
            if not subset:
                raise ValueError("unknown evaluation theme")
            return self._theme_snapshot(subset), set_id
        # Legacy clients may still submit a whole file identifier.
        evaluations = load_evaluation_file(self.evaluations_directory / dataset_id)
        return {"schema_version": 1, "evaluations": evaluations}, dataset_id

    def _persist_run(self, run_id):
        record = self._record(run_id)
        if record is None:
            return
        state = record["state"]
        if not self._db_enabled:
            self._memory_runs[run_id] = deepcopy(state)
            return
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO evaluation_runs
                (run_id, set_id, set_version, dataset, dataset_snapshot, settings, state)
                VALUES (:run_id, :set_id, :version, :dataset, CAST(:snapshot AS jsonb),
                        CAST(:settings AS jsonb), CAST(:state AS jsonb))
                ON CONFLICT (run_id) DO UPDATE SET state=EXCLUDED.state,
                    updated_at=now()"""), {
                    "run_id": run_id, "set_id": record["set_id"], "version": record["set_version"],
                    "dataset": state["dataset"],
                    "snapshot": json.dumps(record["dataset_snapshot"], ensure_ascii=False),
                    "settings": json.dumps(state["settings"], ensure_ascii=False),
                    "state": json.dumps(state, ensure_ascii=False),
                })

    def _load_existing_runs(self):
        if not self._db_enabled:
            for run_id, state in self._memory_runs.items():
                self._runs[run_id] = {"state": deepcopy(state), "dataset_snapshot": {},
                                      "set_id": state.get("dataset", "legacy"), "set_version": "memory",
                                      "future": None}
            return
        with self.engine.connect() as connection:
            rows = connection.execute(text("""SELECT run_id, state, dataset_snapshot,
                set_id, set_version FROM evaluation_runs""")).mappings().all()
        for row in rows:
            state = row["state"]
            if isinstance(state, str):
                state = json.loads(state)
            if not isinstance(state, dict):
                continue
            legacy_path_fields = "results_path" in state or "summary_path" in state
            state.setdefault("storage_schema_version", 1)
            state.pop("results_path", None)
            state.pop("summary_path", None)
            self._runs[row["run_id"]] = {
                "state": state, "dataset_snapshot": row["dataset_snapshot"],
                "set_id": row["set_id"], "set_version": row["set_version"], "future": None,
            }
            if self.recover_interrupted and state.get("status") in ("queued", "running"):
                state["status"] = "interrupted"
                state["error"] = "API process restarted while this run was active"
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                state.setdefault("completed_at", state["updated_at"])
                legacy_path_fields = True
            if legacy_path_fields:
                self._persist_run(row["run_id"])

    def import_legacy_runs(self, source_directory):
        """Copy legacy JSONL run folders into PostgreSQL without changing source files.

        The import is idempotent by run ID and sequence number. A malformed file
        or conflicting row is reported and left untouched for manual inspection.
        """
        if not self._db_enabled:
            raise RuntimeError("legacy dashboard import requires PostgreSQL")
        source = Path(source_directory).resolve()
        if not source.is_dir():
            raise ValueError(f"legacy run directory does not exist: {source}")
        report = {"imported": [], "already_present": [], "errors": []}
        for folder in sorted(path for path in source.iterdir() if path.is_dir()):
            state_path = folder / "state.json"
            if not state_path.is_file():
                continue
            try:
                state_bytes = state_path.read_bytes()
                imported_state = json.loads(state_bytes)
                run_id = imported_state.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ValueError("state.json has no valid run_id")
                result_name = imported_state.get("results_path", "results.jsonl")
                if not isinstance(result_name, str) or Path(result_name).name != result_name:
                    raise ValueError("results_path must be a filename within its run folder")
                results_path = folder / result_name
                if not results_path.is_file():
                    raise ValueError(f"missing legacy result file: {result_name}")

                digest = hashlib.sha256(state_bytes)
                row_count = 0
                with results_path.open("rb") as stream:
                    for line_number, raw_line in enumerate(stream, start=1):
                        if not raw_line.endswith(b"\n"):
                            raise ValueError(f"incomplete JSONL record at line {line_number}")
                        try:
                            event = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise ValueError(f"invalid JSONL record at line {line_number}") from exc
                        if event.get("seq") != row_count + 1 or not isinstance(event.get("result"), dict):
                            raise ValueError(f"invalid or non-contiguous result sequence at line {line_number}")
                        digest.update(raw_line)
                        row_count += 1

                dataset_id = imported_state.get("dataset", "legacy-unknown")
                try:
                    dataset_snapshot, set_id = self._dataset_snapshot(dataset_id)
                except (OSError, ValueError, FileNotFoundError):
                    # Results and metrics remain fully viewable; missing source
                    # relevance data is recorded rather than invented.
                    dataset_snapshot = {"schema_version": 1, "evaluations": [],
                                        "legacy_source_unavailable": dataset_id}
                    set_id = f"legacy::{dataset_id}"
                set_version = hashlib.sha256(json.dumps(
                    dataset_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest()[:16]
                imported_state.pop("results_path", None)
                imported_state.pop("summary_path", None)
                imported_state.setdefault("storage_schema_version", 1)
                imported_state.setdefault("settings", {})
                progress = imported_state.setdefault("progress", {})
                total = int(progress.get("total", row_count))
                progress["completed"] = row_count
                progress.setdefault("total", total)
                if imported_state.get("status") == "completed" and row_count != total:
                    imported_state["status"] = "interrupted"
                    imported_state["error"] = (
                        f"Legacy file has {row_count} complete results; expected {total}. "
                        "Imported complete records only."
                    )
                imported_state["legacy_import"] = {
                    "source_folder": folder.name,
                    "result_rows": row_count,
                    "sha256": digest.hexdigest(),
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }

                with self.engine.begin() as connection:
                    existing = connection.execute(text("""SELECT state, dataset_snapshot,
                        set_id, set_version FROM evaluation_runs WHERE run_id=:run_id FOR UPDATE"""),
                        {"run_id": run_id}).mappings().first()
                    if existing is None:
                        connection.execute(text("""INSERT INTO evaluation_runs
                            (run_id, set_id, set_version, dataset, dataset_snapshot, settings, state)
                            VALUES (:run_id, :set_id, :set_version, :dataset,
                                CAST(:snapshot AS jsonb), CAST(:settings AS jsonb), CAST(:state AS jsonb))"""), {
                                "run_id": run_id, "set_id": set_id, "set_version": set_version,
                                "dataset": dataset_id,
                                "snapshot": json.dumps(dataset_snapshot, ensure_ascii=False),
                                "settings": json.dumps(imported_state["settings"], ensure_ascii=False),
                                "state": json.dumps(imported_state, ensure_ascii=False),
                            })
                        state_to_store = imported_state
                    else:
                        db_state = existing["state"]
                        if isinstance(db_state, str):
                            db_state = json.loads(db_state)
                        state_to_store = db_state

                    insert_result = text("""INSERT INTO evaluation_run_results
                        (run_id, seq, evaluation_id, payload)
                        VALUES (:run_id, :seq, :evaluation_id, CAST(:payload AS jsonb))
                        ON CONFLICT (run_id, seq) DO UPDATE
                            SET evaluation_id=EXCLUDED.evaluation_id
                            WHERE evaluation_run_results.evaluation_id=EXCLUDED.evaluation_id
                              AND evaluation_run_results.payload=EXCLUDED.payload
                        RETURNING seq""")
                    with results_path.open("rb") as stream:
                        for raw_line in stream:
                            event = json.loads(raw_line.decode("utf-8"))
                            inserted = connection.execute(insert_result, {
                                "run_id": run_id, "seq": event["seq"],
                                "evaluation_id": event["evaluation_id"],
                                "payload": json.dumps(event, ensure_ascii=False, separators=(",", ":")),
                            }).scalar_one_or_none()
                            if inserted is None:
                                raise ValueError(f"database has a conflicting payload at sequence {event['seq']}")

                    db_count = connection.execute(text("""SELECT count(*) FROM evaluation_run_results
                        WHERE run_id=:run_id"""), {"run_id": run_id}).scalar_one()
                    if db_count < row_count:
                        raise ValueError(f"database verification failed: {db_count} of {row_count} result rows")
                    state_to_store.setdefault("legacy_import", imported_state["legacy_import"])
                    state_to_store.setdefault("storage_schema_version", 1)
                    state_to_store.pop("results_path", None)
                    state_to_store.pop("summary_path", None)
                    connection.execute(text("""UPDATE evaluation_runs SET state=CAST(:state AS jsonb),
                        updated_at=now() WHERE run_id=:run_id"""), {
                            "run_id": run_id,
                            "state": json.dumps(state_to_store, ensure_ascii=False, default=str),
                        })

                    # Preserve existing JSON/Markdown summaries as database artifacts.
                    summary_name = state_bytes and json.loads(state_bytes).get("summary_path", "run.summary.json")
                    if isinstance(summary_name, str) and Path(summary_name).name == summary_name:
                        summary_file = folder / summary_name
                        if summary_file.is_file():
                            try:
                                summary_payload = json.loads(summary_file.read_text(encoding="utf-8"))
                                connection.execute(text("""INSERT INTO evaluation_run_artifacts
                                    (run_id, artifact_key, payload) VALUES (:run_id, :key, CAST(:payload AS jsonb))
                                    ON CONFLICT (run_id, artifact_key) DO NOTHING"""), {
                                        "run_id": run_id, "key": '"legacy-summary-json"',
                                        "payload": json.dumps(summary_payload, ensure_ascii=False),
                                    })
                            except (OSError, ValueError):
                                pass
                            markdown_file = summary_file.with_suffix(".md")
                            if markdown_file.is_file():
                                connection.execute(text("""INSERT INTO evaluation_run_artifacts
                                    (run_id, artifact_key, payload) VALUES (:run_id, :key, CAST(:payload AS jsonb))
                                    ON CONFLICT (run_id, artifact_key) DO NOTHING"""), {
                                        "run_id": run_id, "key": '"legacy-summary-markdown"',
                                        "payload": json.dumps({"markdown": markdown_file.read_text(encoding="utf-8")},
                                                              ensure_ascii=False),
                                    })
                report["already_present" if existing is not None else "imported"].append(
                    {"run_id": run_id, "rows": row_count, "sha256": digest.hexdigest()})
            except Exception as exc:
                report["errors"].append({"folder": folder.name, "error": str(exc)})
        return report

    def _resolve_dataset_selection(self, selection):
        if isinstance(selection, str):
            selections = [selection]
        elif isinstance(selection, (list, tuple)):
            selections = list(selection)
        else:
            raise ValueError("datasets must be a theme ID or a non-empty list of theme IDs")
        if not selections or any(not isinstance(item, str) or not item for item in selections):
            raise ValueError("select at least one valid theme snapshot")
        if len(set(selections)) != len(selections):
            raise ValueError("the same theme snapshot cannot be selected more than once")

        catalogue = {row["id"]: row for row in self.available_sets()}
        selected_evaluations = []
        selected_labels = []
        seen_evaluation_ids = {}
        for selection_id in selections:
            if selection_id in catalogue:
                snapshot, _ = self._dataset_snapshot(selection_id)
                info = catalogue[selection_id]
                evaluations = validate_document(snapshot)
                selected_labels.append(
                    f"{info['source']} · {info['version_label']} · {info['label']}"
                )
            elif Path(selection_id).name == selection_id and (self.evaluations_directory / selection_id).is_file():
                # Backward-compatible API support for old clients that pass a whole file.
                snapshot, _ = self._dataset_snapshot(selection_id)
                evaluations = validate_document(snapshot)
                selected_labels.append(f"{selection_id} · todos os temas")
            else:
                raise ValueError(f"unknown theme snapshot: {selection_id}")
            for evaluation in evaluations:
                previous = seen_evaluation_ids.get(evaluation["id"])
                if previous is not None:
                    if previous != evaluation:
                        raise ValueError(
                            f"selected theme snapshots contain conflicting versions of query "
                            f"{evaluation['id']}; select only one version of that query"
                        )
                    continue
                seen_evaluation_ids[evaluation["id"]] = evaluation
                selected_evaluations.append(evaluation)

        dataset_snapshot = {"schema_version": 1, "evaluations": selected_evaluations}
        encoded_snapshot = json.dumps(dataset_snapshot, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"))
        snapshot_version = hashlib.sha256(encoded_snapshot.encode("utf-8")).hexdigest()[:16]
        selection_key = hashlib.sha256(json.dumps(sorted(selections), separators=(",", ":"))
                                       .encode("utf-8")).hexdigest()[:16]
        return selections, selected_evaluations, dataset_snapshot, f"selection:{selection_key}", \
            snapshot_version, "; ".join(selected_labels)

    def start(self, dataset_selection, options):
        dataset_ids, evaluations, dataset_snapshot, set_id, set_version, dataset_label = \
            self._resolve_dataset_selection(dataset_selection)
        if not isinstance(options, dict):
            raise ValueError("settings must be an object")
        raw_presets = options.get("presets") or ("rapido",)
        if not isinstance(raw_presets, (list, tuple)):
            raise ValueError("presets must be a list")
        preset_names = tuple(raw_presets)
        if not preset_names or any(name not in SEARCH_PRESETS for name in preset_names) or len(set(preset_names)) != len(preset_names):
            raise ValueError("invalid or repeated presets")
        raw_quorums = options.get("quorums") or (0.3,)
        if not isinstance(raw_quorums, (list, tuple)):
            raise ValueError("quorums must be a list")
        try:
            quorums = tuple(float(value) for value in raw_quorums)
        except (TypeError, ValueError) as exc:
            raise ValueError("quorums must contain numbers") from exc
        if not quorums or any(not 0 <= value <= 1 for value in quorums) or len(set(quorums)) != len(quorums):
            raise ValueError("invalid or repeated quorums")
        seed_methods = _select_methods(SEED_METHODS, options.get("seed_methods"),
                                       options.get("exclude_seed_methods"), "seed methods")
        rankings = _select_methods(RANKINGS, options.get("rankings"),
                                   options.get("exclude_rankings"), "rankings")
        result_unit = options.get("result_unit", "articles")
        if result_unit not in ("articles", "chunks"):
            raise ValueError("result_unit must be articles or chunks")
        fallback = options.get("query_seed_fallback", "hits")
        if fallback not in QUERY_SEED_FALLBACKS:
            raise ValueError(f"query_seed_fallback must be one of {QUERY_SEED_FALLBACKS}")
        raw_ensemble = options.get("ensemble_rankings") or ENSEMBLE_RANKINGS
        if not isinstance(raw_ensemble, (list, tuple)):
            raise ValueError("ensemble_rankings must be a list")
        ensemble = tuple(raw_ensemble)
        if (not ensemble or len(set(ensemble)) != len(ensemble)
                or any(method not in ENSEMBLE_COMPONENT_RANKINGS for method in ensemble)):
            raise ValueError("invalid or repeated ensemble components")

        settings = {
            "datasets": dataset_ids,
            "presets": {name: SEARCH_PRESETS[name] for name in preset_names},
            "quorums": list(quorums), "seed_methods": list(seed_methods),
            "rankings": list(rankings), "result_unit": result_unit,
            "query_seed_fallback": fallback, "ensemble_rankings": list(ensemble),
            "search_window": SEARCH_WINDOW,
            "search_version": SEARCH_VERSION,
            "runtime": {"python": sys.version, "platform": platform.platform()},
            "embedding_model": getattr(getattr(self.searcher, "vectorizer", None), "model", None),
            "embedding_dimensions": getattr(getattr(self.searcher, "vectorizer", None), "dimensions", None),
        }
        total = len(evaluations) * len(preset_names) * len(quorums) * len(seed_methods) * len(rankings)
        run_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "run_id": run_id, "status": "queued", "created_at": now, "updated_at": now,
            "dataset": dataset_label,
            "datasets": dataset_ids,
            "storage_schema_version": 1,
            "dataset_snapshot_version": set_version,
            "dataset_label": dataset_label,
            "settings": settings,
            "progress": {"completed": 0, "total": total, "phase": "queued", "current": None},
            "groups_completed": 0, "group_count": len(evaluations) * len(preset_names) * len(quorums),
            "group_timings": [],
            "error": None,
        }
        record = {"state": state, "dataset_snapshot": dataset_snapshot,
                  "set_id": set_id, "set_version": set_version, "future": None}
        with self._lock:
            self._runs[run_id] = record
        self._persist_run(run_id)
        future = self._executor.submit(self._run, run_id, evaluations, settings)
        with self._lock:
            record["future"] = future
        return self.get(run_id)

    def _run(self, run_id, evaluations, settings):
        total = self._state(run_id)["progress"]["total"]
        live_summary = LiveSummary(BATCH_KS)
        try:
            _validate_relevant_urls_exist(self.engine, evaluations)
            for item in evaluations:
                for preset_name, preset in settings["presets"].items():
                    for quorum in settings["quorums"]:
                        configurations = [
                            {"mode": "ranking", "stage": "ppr", "ranking": ranking,
                             "seed_method": seed}
                            for seed in settings["seed_methods"]
                            for ranking in settings["rankings"]
                        ]
                        search = {
                            "query": item["query"], "limit": preset["limit"], "top_k": preset["top_k"],
                            "quorum": quorum, "result_unit": settings["result_unit"],
                            "query_seed_fallback": settings["query_seed_fallback"],
                            "ensemble_rankings": settings["ensemble_rankings"],
                            **SHARED_SEARCH_SETTINGS, **SEARCH_WINDOW,
                        }
                        group_started = time.monotonic()
                        self._update(run_id, status="running", progress={
                            "completed": self._state(run_id)["progress"]["completed"], "total": total,
                            "phase": "retrieval", "current": {
                                "evaluation_id": item["id"], "preset": preset_name,
                                "quorum": quorum, "ranking": None, "seed_method": None,
                            },
                        })

                        def on_progress(event):
                            if event.get("activity") != "ranking" or not event.get("entry"):
                                self._update(run_id, progress={
                                    "completed": self._state(run_id)["progress"]["completed"],
                                    "total": total, "phase": event.get("activity", "ranking"),
                                    "current": {"evaluation_id": item["id"], "preset": preset_name,
                                                "quorum": quorum, **(event.get("configuration") or {})},
                                })
                                return
                            entry = event["entry"]
                            configuration = event["configuration"]
                            ranked_urls = list(dict.fromkeys(
                                row["article"] for row in entry.get("ranked", [])
                                if isinstance(row, dict) and isinstance(row.get("article"), str)
                            ))
                            result = {
                                **configuration, "preset": preset_name, "quorum": quorum,
                                "limit": preset["limit"], "top_k": preset["top_k"],
                                "result_unit": settings["result_unit"], "stage": "ppr", "mode": "ranking",
                                "ranked_urls": ranked_urls,
                                # Preserve complete result rows and scores for later inspection.
                                "ranked_results": deepcopy(entry.get("ranked", [])),
                                "metrics": _metrics_at_ks(ranked_urls, item["relevant_urls"]),
                                "ranking_metrics": _ranking_metrics(ranked_urls, item["relevant_urls"]),
                                "coverage": _coverage(ranked_urls, item["relevant_urls"]),
                                "diagnostics": entry.get("diagnostics", {}),
                                "retrieval_id": entry.get("retrieval_id"),
                                "computation_reused": entry.get("computation_reused", False),
                                "computation_seconds": entry.get("computation_seconds"),
                                "step_timings": entry.get("step_timings", {}),
                                "retrieval_steps": event.get("retrieval_steps", {}),
                                "retrieval_seconds": event.get("retrieval_seconds"),
                                "group_elapsed_seconds": event.get("group_elapsed_seconds"),
                                "completed_at": datetime.now(timezone.utc).isoformat(),
                            }
                            if event.get("retrieval_snapshot") is not None:
                                self._persist_artifact(run_id, {
                                    "evaluation_id": item["id"], "preset": preset_name,
                                    "quorum": quorum,
                                }, "retrieval", event["retrieval_snapshot"])
                            self._append_result(run_id, item, result, live_summary, total)
                            current = {"evaluation_id": item["id"], "preset": preset_name,
                                       "quorum": quorum, **configuration}
                            self._update(run_id, progress={
                                "completed": self._state(run_id)["progress"]["completed"],
                                "total": total, "phase": "ranking", "current": current,
                            })

                        report = evaluate_request(self.searcher, self.ranker, {
                            "search": search, "configurations": configurations, "benchmark": False,
                        }, progress_callback=on_progress, include_completed_entries=True)
                        artifact_context = {"evaluation_id": item["id"], "preset": preset_name,
                                            "quorum": quorum}
                        # Ranked result rows are stored once in evaluation_run_results;
                        # keep only group-level report metadata here to avoid duplicating
                        # every ranked URL in an artifact as well.
                        report_metadata = {key: value for key, value in report.items() if key != "results"}
                        self._persist_artifact(run_id, artifact_context, "evaluation_report", report_metadata)
                        self._persist_artifact(run_id, artifact_context, "search_request", search)
                        optimized = report["performance"]["optimized"]
                        group_summary = {
                            "evaluation_id": item["id"], "preset": preset_name, "quorum": quorum,
                            "group_wall_seconds": time.monotonic() - group_started,
                            **optimized,
                        }
                        self._update(run_id, group_completed=group_summary)
                        completed = self._state(run_id)["progress"]["completed"]
                        self._persist_artifact(run_id, {"scope": "run"}, "summary",
                                               live_summary.snapshot(completed, total, "running"))
            self._update(run_id, status="completed", progress={
                "completed": total, "total": total, "phase": "completed", "current": None,
            })
            self._persist_artifact(run_id, {"scope": "run"}, "summary",
                                   live_summary.snapshot(total, total, "completed"))
        except Exception as exc:
            self._update(run_id, status="failed", error=str(exc))
            completed = self._state(run_id)["progress"]["completed"]
            self._persist_artifact(run_id, {"scope": "run"}, "summary",
                                   live_summary.snapshot(completed, total, "failed"))
            return
        self._persist_state(run_id)

    def _record(self, run_id):
        with self._lock:
            return self._runs.get(run_id)

    def _state(self, run_id):
        record = self._record(run_id)
        if record is None:
            raise KeyError(run_id)
        return record["state"]

    def _update(self, run_id, **changes):
        record = self._record(run_id)
        if record is None:
            return
        with self._lock:
            state = record["state"]
            group_completed = changes.pop("group_completed", None)
            state.update(changes)
            if group_completed is not None:
                state["groups_completed"] += 1
                state["group_timings"].append(group_completed)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            if state.get("status") in ("completed", "failed", "interrupted"):
                state.setdefault("completed_at", state["updated_at"])
            self._persist_state_locked(record)

    def _persist_state_locked(self, record):
        self._persist_run(record["state"]["run_id"])

    def _persist_artifact(self, run_id, context, artifact_type, payload):
        key = json.dumps([context.get("evaluation_id"), context.get("preset"),
                          context.get("quorum"), artifact_type], separators=(",", ":"))
        if self._db_enabled:
            with self.engine.begin() as connection:
                connection.execute(text("""INSERT INTO evaluation_run_artifacts
                    (run_id, artifact_key, payload) VALUES (:run_id, :key, CAST(:payload AS jsonb))
                    ON CONFLICT (run_id, artifact_key) DO UPDATE SET payload=EXCLUDED.payload,
                        created_at=now()"""), {
                        "run_id": run_id, "key": key,
                        "payload": json.dumps(payload, ensure_ascii=False, default=str),
                    })
        else:
            self._memory_artifacts[(run_id, key)] = deepcopy(payload)

    def _persist_state(self, run_id):
        record = self._record(run_id)
        if record:
            with self._lock:
                self._persist_state_locked(record)

    def _append_result(self, run_id, item, result, live_summary, total):
        record = self._record(run_id)
        if record is None:
            return
        with self._lock:
            state = record["state"]
            seq = state["progress"]["completed"] + 1
            event = {"seq": seq, "evaluation_id": item["id"],
                     "query": item["query"], "query_formulation": item.get("query_formulation", "unspecified"),
                     "result": result}
            next_state = deepcopy(state)
            next_state["progress"]["completed"] = seq
            next_state["updated_at"] = datetime.now(timezone.utc).isoformat()
            if self._db_enabled:
                with self.engine.begin() as connection:
                    connection.execute(text("""INSERT INTO evaluation_run_results
                        (run_id, seq, evaluation_id, payload)
                        VALUES (:run_id, :seq, :evaluation_id, CAST(:payload AS jsonb))
                        ON CONFLICT (run_id, seq) DO NOTHING"""), {
                             "run_id": run_id, "seq": seq, "evaluation_id": item["id"],
                             "payload": json.dumps(event, ensure_ascii=False, default=str),
                         })
                    connection.execute(text("""UPDATE evaluation_runs
                        SET state=CAST(:state AS jsonb), updated_at=now() WHERE run_id=:run_id"""), {
                            "run_id": run_id,
                            "state": json.dumps(next_state, ensure_ascii=False, default=str),
                        })
            else:
                self._memory_results.setdefault(run_id, []).append(deepcopy(event))
                self._memory_runs[run_id] = deepcopy(next_state)
            state.clear()
            state.update(next_state)
            live_summary.add(item, result)

    def _public_state(self, record):
        with self._lock:
            # Avoid resending growing group timing history on every poll.
            state = {key: deepcopy(value) for key, value in record["state"].items()
                     if key != "group_timings"}
        return state

    def get(self, run_id):
        record = self._record(run_id)
        return self._public_state(record) if record else None

    def list(self):
        with self._lock:
            records = list(self._runs.values())
        states = []
        for record in records:
            state = self._public_state(record)
            states.append({key: state.get(key) for key in (
                "run_id", "status", "created_at", "updated_at", "dataset", "dataset_label", "progress", "error")})
        return sorted(states,
                      key=lambda state: state.get("created_at", ""), reverse=True)

    def results(self, run_id, after=0, limit=100):
        record = self._record(run_id)
        if record is None:
            return None
        after = max(0, int(after))
        limit = min(500, max(1, int(limit)))
        events = []
        if self._db_enabled:
            with self.engine.connect() as connection:
                payloads = connection.execute(text("""SELECT payload FROM evaluation_run_results
                    WHERE run_id=:run_id AND seq>:after ORDER BY seq LIMIT :limit"""),
                    {"run_id": run_id, "after": after, "limit": limit + 1}).scalars().all()
            has_more = len(payloads) > limit
            for event in payloads[:limit]:
                if isinstance(event, str):
                    event = json.loads(event)
                public = {key: value for key, value in event.items() if key != "result"}
                public["result"] = {key: value for key, value in event["result"].items()
                                     if key not in ("ranked_urls", "ranked_results")}
                events.append(public)
            state = self.get(run_id)
            return {"events": events, "cursor": events[-1]["seq"] if events else after,
                    "has_more": has_more, "progress": deepcopy(state["progress"])}
        events = []
        for event in self._memory_results.get(run_id, []):
            if event["seq"] <= after:
                continue
            if len(events) >= limit:
                break
            public = {key: value for key, value in event.items() if key != "result"}
            public["result"] = {key: value for key, value in event["result"].items()
                                if key not in ("ranked_urls", "ranked_results")}
            events.append(public)
        total_after = sum(event["seq"] > after for event in self._memory_results.get(run_id, []))
        state = self.get(run_id)
        return {"events": events, "cursor": events[-1]["seq"] if events else after,
                "has_more": total_after > limit, "progress": deepcopy(state["progress"])}

    def result(self, run_id, seq):
        record = self._record(run_id)
        if record is None:
            return None
        if self._db_enabled:
            with self.engine.connect() as connection:
                payload = connection.execute(text("""SELECT payload FROM evaluation_run_results
                    WHERE run_id=:run_id AND seq=:seq"""),
                    {"run_id": run_id, "seq": seq}).scalar_one_or_none()
            return json.loads(payload) if isinstance(payload, str) else payload
        return next((deepcopy(event) for event in self._memory_results.get(run_id, [])
                     if event["seq"] == seq), None)

    def shutdown(self, wait=True):
        self._executor.shutdown(wait=wait)
