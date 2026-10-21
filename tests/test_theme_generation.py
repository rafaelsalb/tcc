import pytest

from services.theme_generation import (
    ThemeSelectionPolicy,
    _candidates,
    select_themes,
)


def test_candidates_count_distinct_articles_with_all_entities():
    articles = {
        "a": {"A": "Alpha", "B": "Beta"},
        "b": {"A": "Alpha", "B": "Beta"},
        "c": {"A": "Alpha", "C": "Gamma"},
    }

    candidates = {tuple(item["entities"]): item["article_count"]
                  for item in _candidates(articles, max_entities=2)}

    assert candidates[("A",)] == 3
    assert candidates[("B",)] == 2
    assert candidates[("A", "B")] == 2
    assert candidates[("A", "C")] == 1


def test_selection_takes_deterministic_top_candidates_per_band():
    candidates = [
        {"entities": ["b"], "labels": ["B"], "article_count": 20},
        {"entities": ["a"], "labels": ["A"], "article_count": 30},
        {"entities": ["c"], "labels": ["C"], "article_count": 80},
        {"entities": ["d"], "labels": ["D"], "article_count": 250},
    ]
    policy = ThemeSelectionPolicy(per_band=1)

    selected = select_themes(candidates, policy)

    assert [(item["entities"], item["article_count"], item["prevalence_band"])
            for item in selected] == [(["a"], 30, 0), (["c"], 80, 1), (["d"], 250, 2)]


@pytest.mark.parametrize("policy", [
    ThemeSelectionPolicy(min_articles=0),
    ThemeSelectionPolicy(min_articles=20, max_articles=10),
    ThemeSelectionPolicy(band_edges=(200, 50)),
    ThemeSelectionPolicy(max_entities=3),
])
def test_invalid_selection_policy_is_rejected(policy):
    with pytest.raises(ValueError):
        policy.validate()
