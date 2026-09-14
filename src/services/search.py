import numpy as np
from ollama import Client
from repositories.article import ArticleRepository
from repositories.chunk import ChunkRepository
from services.vectorizer import VectorizerService


class SearchService:
    def __init__(self, article_repository: ArticleRepository, chunk_repository: ChunkRepository, vectorizer: VectorizerService, ollama_client: Client):
        self.article_repository = article_repository
        self.chunk_repository = chunk_repository
        self.vectorizer = vectorizer
        self.ollama = ollama_client

    def search(self, query: str, top_k: int = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None, order_by: str = "date_published"):
        # augmented_query = self.ollama.generate(model="llama3.2:3b", prompt=f"Esta é uma query de busca para um sistema de busca semântica: \"{query}\". Gere uma query expandida, adicionando sinônimos e termos relacionados, para melhorar a recuperação de informações relevantes. Responda com a nova query, e com a nova query apenas.", options={'max_tokens': 50}).response
        # print("Augmented query:", augmented_query)
        query_embedding = self.vectorizer.embed([query])[0]
        # chunks = self.chunk_repository.query_chunks(query_embedding, top_k, limit, offset, date_from, date_to)
        chunks = self.chunk_repository.query_chunks_hybrid(query, query_embedding, top_k, limit, offset, date_from, date_to)
        if not chunks:
            return {
                'results': [],
                'articles': [],
                'total': 0,
                'limit': limit,
                'offset': offset
            }
        # results = []
        cosine_distance = lambda a, b: np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        # results = sorted(results, key=lambda x: x["date_published"])
        results = list(
            map(lambda chunk: {
                'article_url': chunk["G1Articles"].url,
                'article_title': chunk["G1Articles"].title,
                'chunk': chunk["G1Chunks"].chunk,
                'distance': cosine_distance(query_embedding, chunk["G1Chunks"].embedding),
                'rrf_score': chunk.get("rrf_score"),
                'text_rank': chunk.get("text_rank")
            }, [chunk for chunk in chunks if chunk["G1Chunks"].embedding is not None])
        )
        unique_articles = set(result['article_url'] for result in results)
        articles = self.article_repository.get_all(in_=list(unique_articles))
        articles_result = [
            {
                'title': a.title,
                'url': a.url,
                'excerpt': a.excerpt,
                'date_published': a.date_published
            } for a in articles
        ]
        response = {
            # 'augmented_query': augmented_query,
            'results': results,
            'articles': articles_result,
            'total': len(chunks),
            'limit': limit,
            'offset': offset
        }
        return response
