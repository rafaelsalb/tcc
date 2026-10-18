import numpy as np
from sqlalchemy import create_engine, literal, select, union_all
from sqlalchemy.dialects import postgresql
from types import SimpleNamespace

from repositories.article import ArticleRepository
from repositories.chunk import _apply_result_window, _hnsw_ef_search, _ranked_chunk_window
from services.search import SearchService


def test_frontend_limits_control_hnsw_breadth():
    assert _hnsw_ef_search(25, 50) == 50
    assert _hnsw_ef_search(30, 200) == 200
    assert _hnsw_ef_search(40, 400) == 400


def test_top_k_is_the_single_sql_result_limit():
    statement = _apply_result_window(select(literal(1)), top_k=25, offset=0)
    sql = str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))

    assert "LIMIT 25" in sql
    assert "LIMIT 50" not in sql


def test_offset_is_applied_without_replacing_top_k():
    statement = _apply_result_window(select(literal(1)), top_k=30, offset=7)
    sql = str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))

    assert "LIMIT 30 OFFSET 7" in sql


def test_article_window_scores_all_chunks_then_limits_distinct_articles():
    # The best chunk is deliberately last; the first two chunks belong to A.
    values = [(1, "a", .9), (2, "a", .8), (3, "b", .7), (4, "c", .6), (5, "d", .99)]
    scored = union_all(*[
        select(literal(i).label("chunk_id"), literal(u).label("article"), literal(s).label("score"))
        for i, u, s in values
    ]).cte("scored")
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            rows = connection.execute(select(_ranked_chunk_window(scored, 2, 0, "articles"))).mappings().all()
            assert {r["article"] for r in rows} == {"d", "a"}
            assert {r["chunk_id"] for r in rows} == {5, 1}
            rows = connection.execute(select(_ranked_chunk_window(scored, 2, 1, "articles"))).mappings().all()
            assert {r["article"] for r in rows} == {"a", "b"}
    finally:
        engine.dispose()


def test_lexical_search_does_not_call_vectorizer_and_reports_empty_results():
    class NoEmbedding:
        def embed(self, *args):
            raise AssertionError("Lexical stage must not generate embeddings")

    class Repository:
        def query_chunks_hybrid(self, *args, **kwargs):
            assert args[1] is None
            assert kwargs["retrieval_stage"] == "lexical"
            return {"rows": [], "lexical_ranked": [], "diagnostics": {}}

    service = SearchService(None, Repository(), NoEmbedding(), None)
    result = service.search("short", retrieval_stage="lexical", result_unit="articles")
    assert result["ranked"] == []
    assert result["diagnostics"]["returned_articles"] == 0
    assert result["retrieval_id"]


def test_search_service_passes_hnsw_limit_and_top_k_separately():
    class FakeVectorizer:
        def embed(self, texts):
            return [[0.0]]

    class FakeChunkRepository:
        call = None

        def query_chunks_hybrid(self, *args, **kwargs):
            self.call = (args, kwargs)
            return []

    chunk_repository = FakeChunkRepository()
    service = SearchService(None, chunk_repository, FakeVectorizer(), None)

    service.search("query", top_k=25, limit=50)

    args, kwargs = chunk_repository.call
    assert args[2] == 25  # top_k controls the final search result cap
    assert args[3] == 50  # limit controls HNSW search breadth
    assert kwargs["exact"] is False


def test_search_service_uses_default_top_k_when_api_parameter_is_omitted():
    class FakeVectorizer:
        def embed(self, texts):
            return [[0.0]]

    class FakeChunkRepository:
        call = None

        def query_chunks_hybrid(self, *args, **kwargs):
            self.call = (args, kwargs)
            return []

    chunk_repository = FakeChunkRepository()
    service = SearchService(None, chunk_repository, FakeVectorizer(), None)

    service.search("query", top_k=None, limit=400)

    args, _ = chunk_repository.call
    assert args[2] == 5
    assert args[3] == 400


def test_search_service_fetches_all_articles_for_retrieved_chunks():
    class FakeVectorizer:
        def embed(self, texts):
            return [[1.0]]

    class FakeChunkRepository:
        def query_chunks_hybrid(self, *args, **kwargs):
            return [{
                "G1Articles": SimpleNamespace(
                    url="https://g1.globo.com/article", title="title"
                ),
                "G1Chunks": SimpleNamespace(chunk="text", embedding=np.array([1.0])),
            }]

    class FakeArticleRepository:
        call = None

        def get_all(self, **kwargs):
            self.call = kwargs
            return [SimpleNamespace(
                title="title",
                url="https://g1.globo.com/article",
                excerpt="excerpt",
                date_published=None,
            )]

    article_repository = FakeArticleRepository()
    service = SearchService(
        article_repository,
        FakeChunkRepository(),
        FakeVectorizer(),
        None,
    )

    result = service.search("query", top_k=300, limit=1600)

    assert article_repository.call["limit"] is None
    assert len(result["articles"]) == 1


def test_article_repository_omits_limit_when_none_is_requested(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalars(self, statement):
            captured["statement"] = statement
            return self

        def all(self):
            return []

    monkeypatch.setattr("repositories.article.Session", FakeSession)

    ArticleRepository(None).get_all(in_=["https://g1.globo.com/article"], limit=None)

    sql = str(captured["statement"].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "LIMIT" not in sql
