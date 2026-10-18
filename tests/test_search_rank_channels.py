from types import SimpleNamespace

import numpy as np

from services.search import SearchService


def test_search_preserves_article_rank_channels_and_sorts_best_rank_first():
    articles = {
        url: SimpleNamespace(url=url, title=url, excerpt="", date_published=None)
        for url in ("article-a", "article-b", "article-c")
    }
    chunks = [
        {"G1Articles": articles["article-a"], "G1Chunks": SimpleNamespace(chunk="a1", embedding=np.array([1., 0.])),
         "rrf_score": 0.03, "article_vector_rank": 8, "article_text_rank": 1},
        {"G1Articles": articles["article-b"], "G1Chunks": SimpleNamespace(chunk="b1", embedding=np.array([0., 1.])),
         "rrf_score": 0.02, "article_vector_rank": 1, "article_text_rank": 9},
        {"G1Articles": articles["article-c"], "G1Chunks": SimpleNamespace(chunk="c1", embedding=np.array([1., 1.])),
         "rrf_score": 0.01, "article_vector_rank": 4, "article_text_rank": 3},
    ]

    class ChunkRepository:
        def query_chunks_hybrid(self, *args, **kwargs):
            return {"rows": chunks, "lexical_ranked": [], "diagnostics": {}}

    class ArticleRepository:
        def get_all(self, **kwargs):
            return list(articles.values())

    class Vectorizer:
        def embed(self, texts):
            return [np.array([1., 0.])]

    service = SearchService(ArticleRepository(), ChunkRepository(), Vectorizer(), None)
    response = service.search("query", top_k=3, result_unit="articles")
    assert [row["article"] for row in response["vector_ranked"]] == ["article-b", "article-c", "article-a"]
    assert [row["article"] for row in response["lexical_only_ranked"]] == ["article-a", "article-c", "article-b"]
    assert {row["article"] for row in response["vector_ranked"]} == {row["article"] for row in response["ranked"]}


def test_search_uses_database_cosine_similarity_without_loading_chunk_embedding():
    article = SimpleNamespace(url="article-a", title="A", excerpt="", date_published=None)
    chunk = {"G1Articles": article, "G1Chunks": SimpleNamespace(chunk="content"),
             "cosine_similarity": 0.75, "rrf_score": 1.0,
             "article_vector_rank": 1, "article_text_rank": 1}

    class ChunkRepository:
        def query_chunks_hybrid(self, *args, **kwargs):
            return {"rows": [chunk], "lexical_ranked": [], "diagnostics": {}}

    class ArticleRepository:
        def get_all(self, **kwargs):
            return [article]

    class Vectorizer:
        def embed(self, texts):
            return [np.array([1.0, 0.0])]

    response = SearchService(ArticleRepository(), ChunkRepository(), Vectorizer(), None).search("query")

    assert response["results"][0]["distance"] == 0.75
