import pytest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("aggregate_evaluations", Path(__file__).resolve().parents[1] / "aggregate_evaluations.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
aggregate = module.aggregate


def item(id="tema", count=20, query="consulta", style=None):
    value = {"id": id, "query": query, "relevant_urls": [f"https://g1.globo.com/{i}.ghtml" for i in range(count)]}
    if style is not None:
        value["query_formulation"] = style
    return value


def doc(*items):
    return {"schema_version": 1, "evaluations": list(items)}


def test_deduplicate_baseline_preserve_explicit_formulation_and_exclude_short_cases():
    result, provenance = aggregate([
        ("old", doc(item(), item("short", 10))),
        ("variants", doc(item("tema__baseline", style="baseline"),
                         item("tema__keyword", query="palavra", style="keyword"))),
    ])
    assert [row["id"] for row in result["evaluations"]] == ["tema__keyword", "tema__baseline"]
    assert provenance["duplicate_cases_removed"] == 1
    assert provenance["sources"][0]["excluded_below_20"] == 1
    assert len(provenance["cases"][1]["sources"]) == 2


def test_different_reference_order_is_not_deduplicated_or_reordered():
    first = item("one")
    second = item("two")
    second["relevant_urls"].reverse()
    result, _ = aggregate([("source", doc(first, second))])
    assert len(result["evaluations"]) == 2
    assert result["evaluations"][1]["relevant_urls"] == second["relevant_urls"]


def test_conflicting_ids_are_rejected():
    with pytest.raises(ValueError, match="Conflicting evaluation ID"):
        aggregate([("first", doc(item())), ("second", doc(item(query="different")))])
