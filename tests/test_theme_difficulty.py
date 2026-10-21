import json

from services.dashboard_runs import DashboardRunManager, available_evaluation_sets
from services.batch_evaluation import load_evaluation_document


def test_v2_theme_metadata_survives_set_snapshots_and_run_selection(tmp_path):
    document = {
        "schema_version": 2,
        "themes": {"topic": ["Main Entity", "Second Entity"]},
        "evaluations": [{
            "id": "topic__query",
            "query": "topic query",
            "relevant_urls": ["https://g1.globo.com/topic/article.ghtml"],
        }],
    }
    path = tmp_path / "evals_topic.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded = load_evaluation_document(path)
    assert loaded["themes"] == document["themes"]
    assert available_evaluation_sets(tmp_path)[0]["main_entities"] == ["Main Entity", "Second Entity"]

    manager = DashboardRunManager(None, None, None, tmp_path)
    selected = manager.available_sets()[0]
    _, evaluations, snapshot, *_ = manager._resolve_dataset_selection(selected["id"])
    assert evaluations == loaded["evaluations"]
    assert snapshot["themes"] == document["themes"]
