"""Post-hoc article-prevalence counts attached to completed dashboard runs."""

from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from models.models import ArticleEntities, G1Articles, G1Entities


ARTIFACT_KEY = "theme_article_counts_v1"
ELIGIBILITY_RULE = "full_text_articles_in_inclusive_date_window_v1"
DIFFICULTY_METRIC_VERSION = 3


def ensure_theme_metric_tables(engine):
    """Create additive persistence tables for auditable theme metrics."""
    statements = (
        """CREATE TABLE IF NOT EXISTS evaluation_article_eligibility_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            date_from DATE NOT NULL, date_to DATE NOT NULL,
            eligibility_rule TEXT NOT NULL,
            eligible_articles_count INTEGER NOT NULL,
            eligible_article_urls JSONB NOT NULL,
            entity_indexed_articles_count INTEGER NOT NULL,
            entity_indexed_article_urls JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE IF NOT EXISTS evaluation_theme_difficulty_metrics (
            metric_id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
            theme_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            metric_version INTEGER NOT NULL,
            main_entities JSONB NOT NULL,
            resolved_entities JSONB NOT NULL,
            eligibility_snapshot_id TEXT NOT NULL REFERENCES evaluation_article_eligibility_snapshots(snapshot_id),
            eligible_articles_count INTEGER NOT NULL,
            matching_articles_count INTEGER NOT NULL,
            matching_article_urls JSONB NOT NULL,
            difficulty_score DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (run_id, theme_id, revision))""",
        """CREATE INDEX IF NOT EXISTS idx_theme_difficulty_run_theme_revision
            ON evaluation_theme_difficulty_metrics (run_id, theme_id, revision DESC)""",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _iso_date(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc


def validate_theme_mapping(themes, max_entities=5):
    if not isinstance(themes, dict) or not themes:
        raise ValueError("themes must be a non-empty object mapping theme IDs to entity arrays")
    normalized = {}
    for theme, entities in themes.items():
        if not isinstance(theme, str) or not theme.strip():
            raise ValueError("theme IDs must be non-empty strings")
        if not isinstance(entities, list) or not 1 <= len(entities) <= max_entities:
            raise ValueError(f"themes[{theme!r}] must contain between one and {max_entities} entity identities")
        if any(not isinstance(entity, str) or not entity.strip() for entity in entities):
            raise ValueError(f"themes[{theme!r}] must contain non-empty entity identity strings")
        values = [entity.strip() for entity in entities]
        if len(set(values)) != len(values):
            raise ValueError(f"themes[{theme!r}] contains duplicate entities")
        normalized[theme.strip()] = values
    return normalized


def _matching_article_urls(engine, entities, date_from, date_to):
    """Return distinct full-text article URLs matching every entity identity.

    An identity matches either ``g1_entities.canonical`` or the exact stored
    surface text. Junk entities are ignored. A canonical URI therefore works
    across aliases, while a surface string remains an exact-text fallback.
    """
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    article_sets = []
    with Session(engine) as session:
        for identity in entities:
            stmt = (
                select(G1Articles.url)
                .join(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
                .join(G1Entities, G1Entities.id == ArticleEntities.g1_entities_id)
                .where(G1Articles.date_published >= date_from)
                .where(G1Articles.date_published <= date_to)
                .where(G1Articles.text_content.is_not(None))
                .where(G1Entities.is_junk.is_(False))
                .where(or_(G1Entities.canonical == identity, G1Entities.text_ == identity))
                .distinct()
            )
            article_sets.append(set(session.scalars(stmt)))
    return set.intersection(*article_sets) if article_sets else set()


def count_articles_for_entities(engine, entities, date_from, date_to):
    return len(_matching_article_urls(engine, entities, date_from, date_to))


def _difficulty_score(matching_articles_count, eligible_articles_count):
    if matching_articles_count < 0 or eligible_articles_count < 0:
        raise ValueError("article counts must be nonnegative")
    if matching_articles_count > eligible_articles_count:
        raise ValueError("matching_articles_count cannot exceed eligible_articles_count")
    if eligible_articles_count == 0:
        return None
    return math.log1p(matching_articles_count) / math.log1p(eligible_articles_count)


def _eligible_article_snapshot(engine, date_from, date_to):
    with Session(engine) as session:
        eligible = set(session.scalars(
            select(G1Articles.url)
            .where(G1Articles.date_published >= date_from)
            .where(G1Articles.date_published <= date_to)
            .where(G1Articles.text_content.is_not(None))
        ))
        indexed = set(session.scalars(
            select(G1Articles.url)
            .join(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
            .join(G1Entities, G1Entities.id == ArticleEntities.g1_entities_id)
            .where(G1Articles.date_published >= date_from)
            .where(G1Articles.date_published <= date_to)
            .where(G1Articles.text_content.is_not(None))
            .where(G1Entities.is_junk.is_(False))
            .distinct()
        ))
    eligible_urls = sorted(eligible)
    indexed_urls = sorted(indexed & eligible)
    snapshot_seed = json.dumps({
        "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "eligibility_rule": ELIGIBILITY_RULE,
        "eligible_article_urls": eligible_urls,
        "entity_indexed_article_urls": indexed_urls,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot_id = hashlib.sha256(snapshot_seed.encode("utf-8")).hexdigest()
    return {
        "snapshot_id": snapshot_id,
        "date_from": date_from,
        "date_to": date_to,
        "eligibility_rule": ELIGIBILITY_RULE,
        "eligible_article_urls": eligible_urls,
        "eligible_articles_count": len(eligible_urls),
        "entity_indexed_article_urls": indexed_urls,
        "entity_indexed_articles_count": len(indexed_urls),
    }


def preview_theme_entities(engine, run_id, themes, ner_service):
    """Resolve user-entered entity names before the user confirms a count."""
    themes = validate_theme_mapping(themes)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT state, dataset_snapshot FROM evaluation_runs WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).mappings().first()
    if row is None:
        raise LookupError("dashboard run not found")
    state = _decode_json(row["state"])
    if state.get("status") != "completed":
        raise RuntimeError("theme entities can only be previewed for completed runs")
    snapshot = _decode_json(row["dataset_snapshot"])
    known_themes = {
        item.get("id", "").split("__", 1)[0]
        for item in snapshot.get("evaluations", []) if item.get("id")
    }
    unknown = sorted(set(themes) - known_themes) if known_themes else []
    if unknown:
        raise ValueError(f"unknown theme IDs for this run: {unknown}")

    preview = {}
    for theme, entities in themes.items():
        resolved = []
        for value in entities:
            try:
                mentions = ner_service.extract_entities(value)
            except Exception:
                # Spotlight is optional; retain the exact entered string so
                # the user can still proceed with exact-surface matching.
                mentions = None
            if mentions is None:
                resolved.append({
                    "input": value,
                    "matches": [{
                        "text": value, "label": None, "canonical": None,
                        "identity": value, "resolution": "ner_unavailable",
                    }],
                })
            elif mentions:
                resolved.append({
                    "input": value,
                    "matches": [
                        {
                            "text": mention["text"],
                            "label": mention.get("label"),
                            "canonical": mention.get("canonical"),
                            "identity": mention.get("canonical") or mention["text"],
                            "resolution": "canonical" if mention.get("canonical") else "surface",
                        }
                        for mention in mentions
                    ],
                })
            else:
                resolved.append({
                    "input": value,
                    "matches": [{
                        "text": value, "label": None, "canonical": None,
                        "identity": value, "resolution": "not_detected",
                    }],
                })
        preview[theme] = resolved
    return {"themes": preview}


def _decode_json(value):
    return json.loads(value) if isinstance(value, str) else value


def _validate_entity_resolution(entity_resolution, main_entities, themes):
    if entity_resolution is None:
        return {
            theme: [{"input": main_entities[theme][index] if index < len(main_entities[theme]) else identity,
                     "matches": [{
                "text": main_entities[theme][index] if index < len(main_entities[theme]) else identity,
                "label": None, "canonical": None,
                "identity": identity, "resolution": "surface",
            }]} for index, identity in enumerate(themes[theme])]
            for theme in themes
        }
    if not isinstance(entity_resolution, dict) or set(entity_resolution) != set(themes):
        raise ValueError("entity_resolution must provide a preview for every theme")
    normalized = {}
    for theme, entries in entity_resolution.items():
        if not isinstance(entries, list) or len(entries) != len(main_entities[theme]):
            raise ValueError(f"entity_resolution[{theme!r}] must match the main entity inputs")
        identities = []
        clean_entries = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("input") != main_entities[theme][index]:
                raise ValueError(f"entity_resolution[{theme!r}][{index}] does not match its input")
            matches = entry.get("matches")
            if not isinstance(matches, list) or not matches:
                raise ValueError(f"entity_resolution[{theme!r}][{index}] must contain matches")
            clean_matches = []
            for match in matches:
                if not isinstance(match, dict) or not isinstance(match.get("identity"), str) or not match["identity"].strip():
                    raise ValueError(f"entity_resolution[{theme!r}][{index}] contains an invalid identity")
                identity = match["identity"].strip()
                identities.append(identity)
                clean_matches.append({
                    "text": str(match.get("text") or entry["input"]),
                    "label": match.get("label"),
                    "canonical": match.get("canonical"),
                    "identity": identity,
                    "resolution": str(match.get("resolution") or "surface"),
                })
            clean_entries.append({"input": entry["input"], "matches": clean_matches})
        if set(identities) != set(themes[theme]):
            raise ValueError(f"entity_resolution[{theme!r}] identities do not match themes[{theme!r}]")
        normalized[theme] = clean_entries
    return normalized


def attach_theme_counts(engine, run_id, themes, date_range=None, *, main_entities=None,
                        entity_resolution=None):
    """Calculate counts and persist an auditable per-theme difficulty metric."""
    ensure_theme_metric_tables(engine)
    themes = validate_theme_mapping(themes, max_entities=25)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT state, dataset_snapshot FROM evaluation_runs WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).mappings().first()
    if row is None:
        raise LookupError("dashboard run not found")
    state = _decode_json(row["state"])
    snapshot = _decode_json(row["dataset_snapshot"])
    if state.get("status") != "completed":
        raise RuntimeError("theme article counts can only be attached to completed runs")

    known_themes = {
        item.get("id", "").split("__", 1)[0]
        for item in snapshot.get("evaluations", []) if item.get("id")
    }
    if known_themes:
        unknown = sorted(set(themes) - known_themes)
    else:
        unknown = []
    if unknown:
        raise ValueError(f"unknown theme IDs for this run: {unknown}")

    snapshot_entities = snapshot.get("themes", {})
    if main_entities is None:
        main_entities = {}
        for theme, entities in themes.items():
            configured = snapshot_entities.get(theme)
            if isinstance(configured, dict):
                configured = configured.get("main_entities")
            main_entities[theme] = configured or entities
    main_entities = validate_theme_mapping(main_entities)
    if set(main_entities) != set(themes):
        raise ValueError("main_entities must contain exactly the themes being counted")
    resolved_entities = _validate_entity_resolution(entity_resolution, main_entities, themes)

    stored_range = (state.get("settings") or {}).get("search_window") or {}
    if date_range is None:
        date_range = {}
    if not isinstance(date_range, dict) or set(date_range) - {"from", "to"}:
        raise ValueError("date_range must contain only optional from and to fields")
    start_value = date_range.get("from", stored_range.get("date_from"))
    end_value = date_range.get("to", stored_range.get("date_to"))
    if start_value is None or end_value is None:
        raise ValueError("date_range.from and date_range.to are required when the run has no saved search window")
    date_from = _iso_date(start_value, "date_range.from")
    date_to = _iso_date(end_value, "date_range.to")
    if date_from > date_to:
        raise ValueError("date_range.from must be on or before date_range.to")

    eligibility = _eligible_article_snapshot(engine, date_from, date_to)
    # Membership is checked per matched URL; build the lookup set once for all
    # themes instead of once per URL (the snapshot can hold every article in
    # the window, so re-evaluating set(...) per URL is quadratic).
    eligible_urls = set(eligibility["eligible_article_urls"])
    result_themes = {}
    metric_rows = []
    for theme, entities in themes.items():
        matched_urls = sorted(_matching_article_urls(engine, entities, date_from, date_to))
        matched_urls = [url for url in matched_urls if url in eligible_urls]
        eligible_count = eligibility["eligible_articles_count"]
        difficulty_score = _difficulty_score(len(matched_urls), eligible_count)
        result_themes[theme] = {
            "entities": entities,
            "main_entities": main_entities[theme],
            "entity_match": "all",
            "article_count": len(matched_urls),
            "matching_articles_count": len(matched_urls),
            "eligible_articles_count": eligible_count,
            "entity_indexed_articles_count": eligibility["entity_indexed_articles_count"],
            "difficulty_score": difficulty_score,
            "difficulty_metric_version": DIFFICULTY_METRIC_VERSION,
            "eligibility_snapshot_id": eligibility["snapshot_id"],
            "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        }
        metric_rows.append({
            "theme": theme, "entities": entities, "matching_urls": matched_urls,
            "difficulty_score": difficulty_score,
        })
    artifact = {
        "schema_version": 2,
        "run_id": run_id,
        "count_unit": "distinct_articles",
        "entity_identity": "canonical_uri_or_exact_surface_text",
        "entity_filter": "is_junk=false",
        "eligibility_rule": ELIGIBILITY_RULE,
        "eligibility_snapshot_id": eligibility["snapshot_id"],
        "eligible_articles_count": eligibility["eligible_articles_count"],
        "entity_indexed_articles_count": eligibility["entity_indexed_articles_count"],
        "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "themes": result_themes,
    }
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO evaluation_article_eligibility_snapshots
            (snapshot_id, date_from, date_to, eligibility_rule, eligible_articles_count,
             eligible_article_urls, entity_indexed_articles_count, entity_indexed_article_urls)
            VALUES (:snapshot_id, :date_from, :date_to, :rule, :eligible_count,
                    CAST(:eligible_urls AS jsonb), :indexed_count, CAST(:indexed_urls AS jsonb))
            ON CONFLICT (snapshot_id) DO NOTHING"""), {
                "snapshot_id": eligibility["snapshot_id"],
                "date_from": date_from, "date_to": date_to,
                "rule": eligibility["eligibility_rule"],
                "eligible_count": eligibility["eligible_articles_count"],
                "eligible_urls": json.dumps(eligibility["eligible_article_urls"], ensure_ascii=False),
                "indexed_count": eligibility["entity_indexed_articles_count"],
                "indexed_urls": json.dumps(eligibility["entity_indexed_article_urls"], ensure_ascii=False),
            })
        for metric in metric_rows:
            theme = metric["theme"]
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {
                "key": f"theme-difficulty:{run_id}:{theme}",
            })
            revision = connection.execute(text("""SELECT COALESCE(MAX(revision), 0) + 1
                FROM evaluation_theme_difficulty_metrics WHERE run_id=:run_id AND theme_id=:theme"""), {
                    "run_id": run_id, "theme": theme,
                }).scalar_one()
            connection.execute(text("""INSERT INTO evaluation_theme_difficulty_metrics
                (run_id, theme_id, revision, metric_version, main_entities, resolved_entities,
                 eligibility_snapshot_id, eligible_articles_count, matching_articles_count,
                 matching_article_urls, difficulty_score)
                VALUES (:run_id, :theme, :revision, :metric_version, CAST(:main_entities AS jsonb),
                        CAST(:resolved_entities AS jsonb), :snapshot_id, :eligible_count,
                        :matching_count, CAST(:matching_urls AS jsonb), :difficulty_score)"""), {
                    "run_id": run_id, "theme": theme, "revision": revision,
                    "metric_version": DIFFICULTY_METRIC_VERSION,
                    "main_entities": json.dumps(main_entities[theme], ensure_ascii=False),
                    "resolved_entities": json.dumps(resolved_entities[theme], ensure_ascii=False),
                    "snapshot_id": eligibility["snapshot_id"],
                    "eligible_count": eligibility["eligible_articles_count"],
                    "matching_count": len(metric["matching_urls"]),
                    "matching_urls": json.dumps(metric["matching_urls"], ensure_ascii=False),
                    "difficulty_score": metric["difficulty_score"],
                })
        existing = connection.execute(
            text("""SELECT payload FROM evaluation_run_artifacts
                WHERE run_id=:run_id AND artifact_key=:key FOR UPDATE"""),
            {"run_id": run_id, "key": ARTIFACT_KEY},
        ).scalar_one_or_none()
        if existing is not None:
            previous = _decode_json(existing)
            artifact["themes"] = {**previous.get("themes", {}), **artifact["themes"]}
        snapshot_ids = {item.get("eligibility_snapshot_id") for item in artifact["themes"].values()}
        artifact["eligibility_snapshot_id"] = next(iter(snapshot_ids)) if len(snapshot_ids) == 1 else None
        eligible_counts = {item.get("eligible_articles_count") for item in artifact["themes"].values()}
        artifact["eligible_articles_count"] = next(iter(eligible_counts)) if len(eligible_counts) == 1 else None
        indexed_counts = {item.get("entity_indexed_articles_count") for item in artifact["themes"].values()}
        artifact["entity_indexed_articles_count"] = next(iter(indexed_counts)) if len(indexed_counts) == 1 else None
        versions = {item.get("difficulty_metric_version", 1) for item in artifact["themes"].values()}
        artifact["difficulty_metric_version"] = min(versions) if versions else DIFFICULTY_METRIC_VERSION
        artifact["difficulty_definition"] = (
            "log1p(matching_articles_count)/log1p(eligible_articles_count)"
            if artifact["difficulty_metric_version"] >= 2
            else "mixed_metric_versions; see per-theme difficulty_metric_version"
        )
        ranges = {json.dumps(item["date_range"], sort_keys=True)
                  for item in artifact["themes"].values()}
        artifact["date_range"] = next(iter(artifact["themes"].values()))["date_range"] if len(ranges) == 1 else None
        connection.execute(
            text("""INSERT INTO evaluation_run_artifacts
                (run_id, artifact_key, payload) VALUES (:run_id, :key, CAST(:payload AS jsonb))
                ON CONFLICT (run_id, artifact_key) DO UPDATE SET payload=EXCLUDED.payload,
                    created_at=now()"""),
            {"run_id": run_id, "key": ARTIFACT_KEY,
             "payload": json.dumps(artifact, ensure_ascii=False)},
        )
    return artifact


def get_theme_count_artifact(engine, run_id):
    with engine.connect() as connection:
        row = connection.execute(
            text("""SELECT payload FROM evaluation_run_artifacts
                WHERE run_id=:run_id AND artifact_key=:key"""),
            {"run_id": run_id, "key": ARTIFACT_KEY},
        ).scalar_one_or_none()
    artifact = _decode_json(row) if row is not None else None
    if artifact is not None:
        metrics = get_theme_difficulty_metrics(engine, run_id)
        for metric in metrics:
            result = artifact.get("themes", {}).get(metric["theme_id"])
            if result is None:
                continue
            result.update({
                "matching_articles_count": metric["matching_articles_count"],
                "article_count": metric["matching_articles_count"],
                "eligible_articles_count": metric["eligible_articles_count"],
                "difficulty_score": metric["difficulty_score"],
                "difficulty_metric_version": metric["metric_version"],
                "eligibility_snapshot_id": metric["eligibility_snapshot_id"],
                "main_entities": metric["main_entities"],
            })
        if metrics and all(metric["metric_version"] >= DIFFICULTY_METRIC_VERSION for metric in metrics):
            artifact["difficulty_metric_version"] = DIFFICULTY_METRIC_VERSION
            artifact["difficulty_definition"] = "log1p(matching_articles_count)/log1p(eligible_articles_count)"
    return artifact


def get_theme_difficulty_metrics(engine, run_id):
    with engine.connect() as connection:
        rows = connection.execute(text("""SELECT DISTINCT ON (metric.theme_id)
                metric.theme_id, metric.revision, metric.metric_version,
                metric.main_entities, metric.resolved_entities,
                metric.eligibility_snapshot_id, metric.eligible_articles_count,
                metric.matching_articles_count, metric.matching_article_urls,
                metric.difficulty_score, metric.created_at,
                snapshot.date_from, snapshot.date_to, snapshot.eligibility_rule,
                snapshot.entity_indexed_articles_count
            FROM evaluation_theme_difficulty_metrics AS metric
            JOIN evaluation_article_eligibility_snapshots AS snapshot
              ON snapshot.snapshot_id=metric.eligibility_snapshot_id
            WHERE metric.run_id=:run_id
            ORDER BY metric.theme_id, metric.revision DESC"""), {"run_id": run_id}).mappings().all()
    return [{
        "theme_id": row["theme_id"],
        "revision": row["revision"],
        "metric_version": row["metric_version"],
        "main_entities": _decode_json(row["main_entities"]),
        "resolved_entities": _decode_json(row["resolved_entities"]),
        "eligibility_snapshot_id": row["eligibility_snapshot_id"],
        "eligible_articles_count": row["eligible_articles_count"],
        "entity_indexed_articles_count": row["entity_indexed_articles_count"],
        "matching_articles_count": row["matching_articles_count"],
        "difficulty_score": row["difficulty_score"],
        "date_range": {"from": row["date_from"].isoformat(), "to": row["date_to"].isoformat()},
        "eligibility_rule": row["eligibility_rule"],
        "computed_at": row["created_at"].isoformat() if row["created_at"] else None,
    } for row in rows]


def backfill_theme_difficulty_metrics(engine):
    """Append current difficulty scores from stored counts without recounting."""
    ensure_theme_metric_tables(engine)
    with engine.connect() as connection:
        rows = connection.execute(text("""SELECT DISTINCT ON (run_id, theme_id)
                run_id, theme_id, revision, metric_version, main_entities, resolved_entities,
                eligibility_snapshot_id, eligible_articles_count, matching_articles_count,
                matching_article_urls
            FROM evaluation_theme_difficulty_metrics
            ORDER BY run_id, theme_id, revision DESC""")).mappings().all()
    outdated = [row for row in rows if row["metric_version"] < DIFFICULTY_METRIC_VERSION]
    if not outdated:
        return {"metrics_upgraded": 0, "runs_updated": []}

    upgraded_by_run = {}
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as connection:
        for row in outdated:
            run_id, theme = row["run_id"], row["theme_id"]
            matching_count = row["matching_articles_count"]
            eligible_count = row["eligible_articles_count"]
            score = _difficulty_score(matching_count, eligible_count)
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {
                "key": f"theme-difficulty:{run_id}:{theme}",
            })
            revision = connection.execute(text("""SELECT COALESCE(MAX(revision), 0) + 1
                FROM evaluation_theme_difficulty_metrics WHERE run_id=:run_id AND theme_id=:theme"""), {
                    "run_id": run_id, "theme": theme,
                }).scalar_one()
            connection.execute(text("""INSERT INTO evaluation_theme_difficulty_metrics
                (run_id, theme_id, revision, metric_version, main_entities, resolved_entities,
                 eligibility_snapshot_id, eligible_articles_count, matching_articles_count,
                 matching_article_urls, difficulty_score)
                VALUES (:run_id, :theme, :revision, :metric_version, CAST(:main_entities AS jsonb),
                        CAST(:resolved_entities AS jsonb), :snapshot_id, :eligible_count,
                        :matching_count, CAST(:matching_urls AS jsonb), :difficulty_score)"""), {
                    "run_id": run_id, "theme": theme, "revision": revision,
                    "metric_version": DIFFICULTY_METRIC_VERSION,
                    "main_entities": json.dumps(_decode_json(row["main_entities"]), ensure_ascii=False),
                    "resolved_entities": json.dumps(_decode_json(row["resolved_entities"]), ensure_ascii=False),
                    "snapshot_id": row["eligibility_snapshot_id"],
                    "eligible_count": eligible_count,
                    "matching_count": matching_count,
                    "matching_urls": json.dumps(_decode_json(row["matching_article_urls"]), ensure_ascii=False),
                    "difficulty_score": score,
                })
            upgraded_by_run.setdefault(run_id, {})[theme] = {
                "revision": revision,
                "metric_version": DIFFICULTY_METRIC_VERSION,
                "matching_articles_count": matching_count,
                "eligible_articles_count": eligible_count,
                "difficulty_score": score,
                "main_entities": _decode_json(row["main_entities"]),
                "resolved_entities": _decode_json(row["resolved_entities"]),
                "eligibility_snapshot_id": row["eligibility_snapshot_id"],
            }

        for run_id, themes in upgraded_by_run.items():
            existing = connection.execute(text("""SELECT payload FROM evaluation_run_artifacts
                WHERE run_id=:run_id AND artifact_key=:key FOR UPDATE"""), {
                    "run_id": run_id, "key": ARTIFACT_KEY,
                }).scalar_one_or_none()
            artifact = _decode_json(existing) if existing is not None else None
            if not artifact:
                continue
            for theme, metric in themes.items():
                result = artifact.setdefault("themes", {}).get(theme)
                if result is None:
                    continue
                result.update({
                    "matching_articles_count": metric["matching_articles_count"],
                    "article_count": metric["matching_articles_count"],
                    "eligible_articles_count": metric["eligible_articles_count"],
                    "difficulty_score": metric["difficulty_score"],
                    "difficulty_metric_version": DIFFICULTY_METRIC_VERSION,
                    "eligibility_snapshot_id": metric["eligibility_snapshot_id"],
                    "main_entities": metric["main_entities"],
                })
            artifact["schema_version"] = 2
            versions = {item.get("difficulty_metric_version", 1)
                        for item in artifact.get("themes", {}).values()}
            artifact["difficulty_metric_version"] = min(versions) if versions else DIFFICULTY_METRIC_VERSION
            artifact["difficulty_definition"] = (
                "log1p(matching_articles_count)/log1p(eligible_articles_count)"
                if artifact["difficulty_metric_version"] >= 2
                else "mixed_metric_versions; see per-theme difficulty_metric_version"
            )
            artifact["difficulty_revised_at"] = now
            connection.execute(text("""UPDATE evaluation_run_artifacts
                SET payload=CAST(:payload AS jsonb), created_at=now()
                WHERE run_id=:run_id AND artifact_key=:key"""), {
                    "run_id": run_id, "key": ARTIFACT_KEY,
                    "payload": json.dumps(artifact, ensure_ascii=False),
                })
    return {"metrics_upgraded": len(outdated), "runs_updated": sorted(upgraded_by_run)}


def get_theme_eligibility_snapshot(engine, run_id, snapshot_id):
    with engine.connect() as connection:
        row = connection.execute(text("""SELECT snapshot.snapshot_id, snapshot.date_from,
                snapshot.date_to, snapshot.eligibility_rule, snapshot.eligible_articles_count,
                snapshot.eligible_article_urls, snapshot.entity_indexed_articles_count,
                snapshot.entity_indexed_article_urls
            FROM evaluation_article_eligibility_snapshots AS snapshot
            WHERE snapshot.snapshot_id=:snapshot_id
              AND EXISTS (SELECT 1 FROM evaluation_theme_difficulty_metrics AS metric
                WHERE metric.run_id=:run_id AND metric.eligibility_snapshot_id=snapshot.snapshot_id)"""), {
                    "run_id": run_id, "snapshot_id": snapshot_id,
                }).mappings().first()
    if row is None:
        return None
    with engine.connect() as connection:
        metrics = connection.execute(text("""SELECT theme_id, matching_article_urls,
                matching_articles_count FROM evaluation_theme_difficulty_metrics
            WHERE run_id=:run_id AND eligibility_snapshot_id=:snapshot_id
            ORDER BY theme_id, revision DESC"""), {
                "run_id": run_id, "snapshot_id": snapshot_id,
            }).mappings().all()
    matching_by_theme = {}
    for metric in metrics:
        matching_by_theme.setdefault(metric["theme_id"], {
            "matching_articles_count": metric["matching_articles_count"],
            "matching_article_urls": _decode_json(metric["matching_article_urls"]),
        })
    return {
        "snapshot_id": row["snapshot_id"],
        "date_range": {"from": row["date_from"].isoformat(), "to": row["date_to"].isoformat()},
        "eligibility_rule": row["eligibility_rule"],
        "eligible_articles_count": row["eligible_articles_count"],
        "eligible_article_urls": _decode_json(row["eligible_article_urls"]),
        "entity_indexed_articles_count": row["entity_indexed_articles_count"],
        "entity_indexed_article_urls": _decode_json(row["entity_indexed_article_urls"]),
        "matching_articles_by_theme": matching_by_theme,
    }


def attach_theme_counts_file(engine, path):
    """Apply a versioned JSON mapping file to one or more finished runs."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read theme-count mapping file {path}: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "runs"}:
        raise ValueError("mapping file keys must be exactly schema_version and runs")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("mapping file schema_version must be 1")
    runs = document["runs"]
    if not isinstance(runs, list) or not runs:
        raise ValueError("runs must be a non-empty array")
    seen = set()
    pending = []
    for index, item in enumerate(runs):
        if not isinstance(item, dict) or set(item) - {"run_id", "themes", "date_range"}:
            raise ValueError(f"runs[{index}] must contain run_id, themes, and optional date_range")
        run_id = item.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip() or run_id in seen:
            raise ValueError(f"runs[{index}].run_id must be a unique non-empty string")
        seen.add(run_id)
        if "date_range" in item and not isinstance(item["date_range"], dict):
            raise ValueError(f"runs[{index}].date_range must be an object")
        themes = validate_theme_mapping(item.get("themes"))
        pending.append((run_id, themes, item.get("date_range")))
    return [attach_theme_counts(engine, run_id, themes, date_range, main_entities=themes)
            for run_id, themes, date_range in pending]
