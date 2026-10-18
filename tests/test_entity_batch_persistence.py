from types import SimpleNamespace

import pytest

from repositories import entities as entities_module
from repositories.entities import EntityRepository


class _Result:
    def __init__(self, rows=()):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, engine):
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        if len(self.calls) == 1:
            return _Result([
                SimpleNamespace(id=1, text="Pessoa", type="PER"),
                SimpleNamespace(id=2, text="Empresa", type="ORG"),
            ])
        if len(self.calls) == 2:
            return _Result([("article-1", "Pessoa", "PER")])
        return _Result()

    def commit(self):
        self.committed = True


def test_entity_batch_uses_bulk_upsert_and_bulk_association_insert(monkeypatch):
    sessions = []

    def make_session(engine):
        session = _Session(engine)
        sessions.append(session)
        return session

    monkeypatch.setattr(entities_module, "Session", make_session)
    EntityRepository(object()).batch_add_entities(
        articles=["article-1", "article-1", "article-2"],
        texts=["Pessoa", "Empresa", "Pessoa"],
        types=["PER", "ORG", "PER"],
        canonicals=["http://dbpedia.org/resource/Pessoa", None, None],
    )

    session = sessions[0]
    assert len(session.calls) == 3  # upsert, existing-association lookup, bulk insert
    inserted = session.calls[2][1]
    assert {(row["g1_article_url"], row["g1_entities_id"]) for row in inserted} == {
        ("article-2", 1), ("article-1", 2),
    }
    assert session.committed


@pytest.mark.parametrize("articles,texts,types,canonicals", [
    (["a"], [], ["PER"], None),
    (["a"], ["Pessoa"], ["PER"], [None, None]),
])
def test_entity_batch_validates_lengths_before_database_access(
    monkeypatch, articles, texts, types, canonicals,
):
    monkeypatch.setattr(
        entities_module, "Session",
        lambda engine: pytest.fail("invalid input must fail before database access"),
    )

    with pytest.raises(ValueError):
        EntityRepository(object()).batch_add_entities(articles, texts, types, canonicals)
