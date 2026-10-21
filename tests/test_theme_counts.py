import json
from datetime import date
import math

import pytest

from sqlalchemy import create_engine, text

from services.theme_counts import (
    _difficulty_score, _eligible_article_snapshot, _matching_article_urls,
    _validate_entity_resolution, attach_theme_counts_file, preview_theme_entities,
    validate_theme_mapping,
)


def test_theme_mapping_requires_unique_nonempty_entity_identities():
    assert validate_theme_mapping({"topic": ["canonical-uri", "surface"]}) == {
        "topic": ["canonical-uri", "surface"],
    }
    for invalid in ({}, {"topic": []}, {"topic": ["x", "x"]}, {"topic": [""]},
                    {"topic": ["1", "2", "3", "4", "5", "6"]}):
        with pytest.raises(ValueError):
            validate_theme_mapping(invalid)


def test_mapping_file_rejects_unknown_schema_before_database_access(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"schema_version": 2, "runs": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version must be 1"):
        attach_theme_counts_file(None, path)


def test_mapping_file_rejects_duplicate_run_ids_before_database_access(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"schema_version": 1, "runs": [
        {"run_id": "same", "themes": {"topic": ["x"]}},
        {"run_id": "same", "themes": {"topic": ["x"]}},
    ]}), encoding="utf-8")

    with pytest.raises(ValueError, match="unique non-empty"):
        attach_theme_counts_file(None, path)


class _StubNer:
    def extract_entities(self, value):
        if value == "Barack Obama":
            return [{"text": value, "label": "PER", "canonical": "http://dbpedia.org/resource/Barack_Obama"}]
        if value == "Paris":
            return [{"text": value, "label": "LOC", "canonical": None}]
        return []


def test_preview_uses_canonical_identity_and_exact_surface_fallback():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE evaluation_runs (run_id TEXT, state TEXT, dataset_snapshot TEXT)"))
        connection.execute(text("""INSERT INTO evaluation_runs VALUES
            ('run-1', '{"status":"completed"}',
             '{"evaluations":[{"id":"topic__query"}]}')"""))

    result = preview_theme_entities(
        engine, "run-1", {"topic": ["Barack Obama", "Paris", "Unknown"]}, _StubNer(),
    )

    matches = result["themes"]["topic"]
    assert matches[0]["matches"][0]["identity"] == "http://dbpedia.org/resource/Barack_Obama"
    assert matches[0]["matches"][0]["resolution"] == "canonical"
    assert matches[1]["matches"][0]["identity"] == "Paris"
    assert matches[1]["matches"][0]["resolution"] == "surface"
    assert matches[2]["matches"][0]["identity"] == "Unknown"
    assert matches[2]["matches"][0]["resolution"] == "not_detected"


def test_preview_falls_back_to_surface_when_ner_is_unavailable():
    class BrokenNer:
        def extract_entities(self, value):
            raise RuntimeError("Spotlight unavailable")

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE evaluation_runs (run_id TEXT, state TEXT, dataset_snapshot TEXT)"))
        connection.execute(text("""INSERT INTO evaluation_runs VALUES
            ('run-1', '{"status":"completed"}',
             '{"evaluations":[{"id":"topic__query"}]}')"""))

    result = preview_theme_entities(engine, "run-1", {"topic": ["Paris"]}, BrokenNer())

    assert result["themes"]["topic"][0]["matches"][0]["identity"] == "Paris"
    assert result["themes"]["topic"][0]["matches"][0]["resolution"] == "ner_unavailable"


def test_difficulty_is_matching_prevalence_and_validates_counts():
    assert _difficulty_score(0, 10) == 0
    assert _difficulty_score(5, 10) == pytest.approx(math.log1p(5) / math.log1p(10))
    assert _difficulty_score(10, 10) == 1
    assert _difficulty_score(0, 0) is None
    assert _difficulty_score(2, 99) < _difficulty_score(9, 99)
    with pytest.raises(ValueError, match="cannot exceed"):
        _difficulty_score(2, 1)


def test_entity_resolution_must_match_the_input_and_resolved_identity_set():
    main_entities = {"topic": ["New York"]}
    themes = {"topic": ["http://dbpedia.org/resource/New_York_City"]}
    preview = {"topic": [{"input": "New York", "matches": [{
        "text": "New York", "label": "LOC",
        "canonical": "http://dbpedia.org/resource/New_York_City",
        "identity": "http://dbpedia.org/resource/New_York_City",
        "resolution": "canonical",
    }]}]}
    assert _validate_entity_resolution(preview, main_entities, themes) == preview
    with pytest.raises(ValueError, match="does not match its input"):
        _validate_entity_resolution({"topic": [{**preview["topic"][0], "input": "Other"}]}, main_entities, themes)


def test_eligibility_snapshot_persists_the_complete_full_text_url_set():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE g1_articles (url TEXT, date_published DATE, text_content TEXT)"))
        connection.execute(text("CREATE TABLE g1_entities (id INTEGER, text TEXT, type TEXT, canonical TEXT, is_junk BOOLEAN)"))
        connection.execute(text("CREATE TABLE article_entities (g1_article_url TEXT, g1_entities_id INTEGER)"))
        connection.execute(text("""INSERT INTO g1_articles VALUES
            ('article-1', '2025-06-01', 'text'), ('article-2', '2025-06-02', 'text'),
            ('no-text', '2025-06-02', NULL), ('outside-window', '2025-07-01', 'text')"""))
        connection.execute(text("""INSERT INTO g1_entities VALUES
            (1, 'Entity A', 'ORG', 'canonical-a', 0), (2, 'Entity B', 'ORG', NULL, 0),
            (3, 'Noise', 'MISC', NULL, 1)"""))
        connection.execute(text("""INSERT INTO article_entities VALUES
            ('article-1', 1), ('article-1', 2), ('article-2', 1), ('article-2', 3)"""))

    snapshot = _eligible_article_snapshot(engine, date(2025, 6, 1), date(2025, 6, 30))
    assert snapshot["eligible_article_urls"] == ["article-1", "article-2"]
    assert snapshot["eligible_articles_count"] == 2
    assert snapshot["entity_indexed_article_urls"] == ["article-1", "article-2"]
    assert _matching_article_urls(engine, ["canonical-a", "Entity B"],
                                  date(2025, 6, 1), date(2025, 6, 30)) == {"article-1"}
