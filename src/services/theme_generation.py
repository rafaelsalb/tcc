"""Generate reproducible theme candidates from stored article entities."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.models import ArticleEntities, G1Articles, G1Entities


@dataclass(frozen=True)
class ThemeSelectionPolicy:
    """Selection parameters; band edges are exclusive upper bounds."""

    min_articles: int = 10
    max_articles: int = 1000
    band_edges: tuple[int, ...] = (50, 200)
    per_band: int = 5
    max_entities: int = 2

    def validate(self):
        if self.min_articles < 1:
            raise ValueError("min_articles must be positive")
        if self.max_articles < self.min_articles:
            raise ValueError("max_articles must be >= min_articles")
        if self.per_band < 1:
            raise ValueError("per_band must be positive")
        if self.max_entities not in (1, 2):
            raise ValueError("max_entities must be 1 or 2")
        if tuple(sorted(set(self.band_edges))) != self.band_edges:
            raise ValueError("band_edges must be strictly increasing")
        if any(edge <= self.min_articles or edge >= self.max_articles for edge in self.band_edges):
            raise ValueError("band edges must be greater than min_articles and less than max_articles")

    @property
    def bands(self):
        bounds = (self.min_articles, *self.band_edges, self.max_articles + 1)
        return tuple(zip(bounds, bounds[1:]))


def _candidates(article_entities, max_entities):
    """Return counts for entity sets whose members co-occur in distinct articles.

    ``article_entities`` maps article URL to identity -> display label. An
    identity is a canonical URI when available, otherwise the entity surface.
    """
    counts = defaultdict(int)
    displays = {}
    for entities in article_entities.values():
        identities = sorted(entities)
        for identity in identities:
            displays.setdefault(identity, entities[identity])
        for size in range(1, min(max_entities, len(identities)) + 1):
            for entity_set in combinations(identities, size):
                counts[entity_set] += 1
    return [
        {"entities": list(entity_set), "labels": [displays[key] for key in entity_set],
         "article_count": count}
        for entity_set, count in counts.items()
    ]


def select_themes(candidates, policy: ThemeSelectionPolicy):
    """Select a stable, count-stratified subset of entity-set candidates."""
    policy.validate()
    selected = []
    for band_index, (lower, upper) in enumerate(policy.bands):
        eligible = [
            item for item in candidates
            if lower <= item["article_count"] < upper
        ]
        eligible.sort(key=lambda item: (-item["article_count"], tuple(item["entities"])))
        for item in eligible[:policy.per_band]:
            selected.append({**item, "prevalence_band": band_index})
    return selected


def generate_themes(engine, date_from: date, date_to: date,
                    policy: ThemeSelectionPolicy | None = None):
    """Count entity sets in the selected article window and select themes."""
    policy = policy or ThemeSelectionPolicy()
    policy.validate()
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to")

    stmt = (
        select(G1Articles.url, G1Entities.canonical, G1Entities.text_)
        .join(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
        .join(G1Entities, G1Entities.id == ArticleEntities.g1_entities_id)
        .where(G1Articles.date_published >= date_from)
        .where(G1Articles.date_published <= date_to)
        .where(G1Entities.is_junk.is_(False))
        .order_by(G1Articles.url, G1Entities.id)
    )
    article_entities = defaultdict(dict)
    with Session(engine) as session:
        for url, canonical, surface in session.execute(stmt):
            identity = canonical or surface
            # Multiple surfaces for one canonical identity in an article count once.
            article_entities[url].setdefault(identity, surface)

    candidates = _candidates(article_entities, policy.max_entities)
    candidates = [item for item in candidates
                 if policy.min_articles <= item["article_count"] <= policy.max_articles]
    themes = select_themes(candidates, policy)
    themes.sort(key=lambda item: (item["prevalence_band"], -item["article_count"], item["entities"]))
    for index, theme in enumerate(themes, start=1):
        theme["id"] = f"theme_{index:03d}"
        theme["label"] = " + ".join(theme["labels"])
    return {
        "schema_version": 1,
        "generation_algorithm": "entity_cooccurrence_stratified_v1",
        "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "entity_match": "all",
        "entity_identity": "canonical_uri_or_exact_surface_text",
        "entity_filter": "is_junk=false",
        "count_unit": "distinct_articles",
        "selection_policy": {
            "min_articles": policy.min_articles,
            "max_articles": policy.max_articles,
            "band_edges": list(policy.band_edges),
            "per_band": policy.per_band,
            "max_entities": policy.max_entities,
            "bands": [{"min_inclusive": lower, "max_inclusive": upper - 1}
                      for lower, upper in policy.bands],
        },
        "themes": themes,
    }
