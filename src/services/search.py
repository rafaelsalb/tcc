import numpy as np
from repositories.article import ArticleRepository
from repositories.chunk import ChunkRepository
from services.vectorizer import VectorizerService


class SearchService:
    def __init__(self, article_repository: ArticleRepository, chunk_repository: ChunkRepository, vectorizer: VectorizerService):
        self.article_repository = article_repository
        self.chunk_repository = chunk_repository
        self.vectorizer = vectorizer

    def search(self, query: str, top_k: int = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None, order_by: str = "date_published"):
        query_embedding = self.vectorizer.embed([query])[0]
        chunks = self.chunk_repository.query_chunks(query_embedding, top_k, limit, offset, date_from, date_to)
        results = []
        cosine_distance = lambda a, b: np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        articles = []
        for chunk in chunks:
            article = self.article_repository.get_by_id(chunk.article)
            if article.title not in [article['title'] for article in articles]:
                articles.append(
                    {
                        'title': article.title,
                        'url': article.url,
                        'date_published': article.date_published
                    }
                )
            results.append({
                'article_title': article.title,
                'article_url': article.url,
                'article_date_published': article.date_published,
                'chunk': chunk.chunk,
                'similarity': cosine_distance(chunk.embedding, query_embedding)
            })
        results = sorted(results, key=lambda x: x['article_date_published'])
        articles = sorted(articles, key=lambda x: x['date_published'])
        response = {
            'results': results,
            'articles': articles,
            'total': len(results),
            'limit': limit,
            'offset': offset
        }
        return response
