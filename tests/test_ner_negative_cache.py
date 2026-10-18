from types import SimpleNamespace

from services import ner as ner_module


class _Rows:
    def fetchall(self):
        return []


class _Session:
    def __init__(self, engine, article):
        self.article = article

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def scalars(self, statement):
        return SimpleNamespace(all=lambda: [self.article])

    def execute(self, statement):
        return _Rows()


def test_unchanged_zero_entity_article_is_not_reprocessed(monkeypatch):
    article = SimpleNamespace(url="article-1", text_content="text with no named entity")
    monkeypatch.setattr(ner_module, "Session", lambda engine: _Session(engine, article))
    marked = []
    service = object.__new__(ner_module.NERService)
    service.entity_repository = SimpleNamespace(
        engine=object(),
        mark_empty_extractions=lambda urls, version: marked.append((list(urls), version)),
        batch_add_entities=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("empty extraction should not persist empty associations")
        ),
    )
    service._empty_entity_fingerprints = ner_module.OrderedDict()
    service._empty_entity_lock = ner_module.threading.Lock()
    calls = []
    service.extract_entities = lambda text: calls.append(text) or []

    service.batch_get_or_extract_entities_and_store_for_articles([article.url])
    service.batch_get_or_extract_entities_and_store_for_articles([article.url])

    assert calls == [article.text_content]
    assert len(marked) == 2
    assert all(urls == [article.url] for urls, _ in marked)


def test_changed_article_text_invalidates_zero_entity_cache(monkeypatch):
    article = SimpleNamespace(url="article-1", text_content="first text")
    monkeypatch.setattr(ner_module, "Session", lambda engine: _Session(engine, article))
    service = object.__new__(ner_module.NERService)
    service.entity_repository = SimpleNamespace(
        engine=object(), batch_add_entities=lambda **kwargs: None,
        mark_empty_extractions=lambda *args: None,
    )
    service._empty_entity_fingerprints = ner_module.OrderedDict()
    service._empty_entity_lock = ner_module.threading.Lock()
    calls = []
    service.extract_entities = lambda text: calls.append(text) or []

    service.batch_get_or_extract_entities_and_store_for_articles([article.url])
    article.text_content = "updated text"
    service.batch_get_or_extract_entities_and_store_for_articles([article.url])

    assert calls == ["first text", "updated text"]
