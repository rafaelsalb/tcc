import numpy as np
import hashlib
import json
from time import perf_counter
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

    def search(self, query: str, top_k: int | None = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None, order_by: str = "date_published", quorum_threshold: float = 0.7, candidate_cap: int = 20000, result_unit: str = "chunks", retrieval_stage: str = "hybrid"):
        search_started = perf_counter()
        # augmented_query = self.ollama.generate(model="llama3.2:3b", prompt=f"Esta é uma query de busca para um sistema de busca semântica: \"{query}\". Gere uma query expandida, adicionando sinônimos e termos relacionados, para melhorar a recuperação de informações relevantes. Responda com a nova query, e com a nova query apenas.", options={'max_tokens': 50}).response
        # print("Augmented query:", augmented_query)
        step_started = perf_counter()
        query_embedding = self.vectorizer.embed([query])[0] if retrieval_stage != "lexical" else None
        query_embedding_seconds = perf_counter() - step_started
        # chunks = self.chunk_repository.query_chunks(query_embedding, top_k, limit, offset, date_from, date_to)
        # `limit` configures HNSW breadth; `top_k` limits the chosen result unit.
        # Preserve the API's old behavior when callers omit top_k.
        result_top_k = top_k if top_k is not None else 5
        step_started = perf_counter()
        chunks = self.chunk_repository.query_chunks_hybrid(
            query,
            query_embedding,
            result_top_k,
            limit,
            offset,
            date_from,
            date_to,
            exact=False,
            quorum_threshold=quorum_threshold,
            candidate_cap=candidate_cap,
            result_unit=result_unit,
            retrieval_stage=retrieval_stage,
            include_diagnostics=True,
        )
        hybrid_query_seconds = perf_counter() - step_started
        processing_started = perf_counter()
        diagnostics = chunks.get("diagnostics", {}) if isinstance(chunks, dict) else {}
        lexical_ranked = chunks.get("lexical_ranked", []) if isinstance(chunks, dict) else []
        chunks = chunks["rows"] if isinstance(chunks, dict) else chunks
        if not chunks:
            diagnostics.update(returned_chunks=0, returned_articles=0)
            timings = {
                "query_embedding_seconds": query_embedding_seconds,
                "hybrid_query_seconds": hybrid_query_seconds,
                "result_processing_seconds": perf_counter() - processing_started,
                "article_lookup_seconds": 0.0,
                "search_service_seconds": perf_counter() - search_started,
            }
            return {
                'results': [],
                'articles': [],
                'total': 0,
                'limit': limit,
                'offset': offset,
                'ranked': [], 'lexical_ranked': lexical_ranked,
                'diagnostics': diagnostics, 'result_unit': result_unit,
                'timings': timings,
                'retrieval_id': hashlib.sha256(json.dumps({
                    'query': query, 'unit': result_unit, 'stage': retrieval_stage,
                    'top_k': result_top_k, 'limit': limit, 'offset': offset,
                    'date_from': date_from, 'date_to': date_to, 'quorum': quorum_threshold,
                    'candidate_cap': candidate_cap, 'ranking': [],
                }, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            }
        # results = []
        cosine_distance = lambda a, b: np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        # results = sorted(results, key=lambda x: x["date_published"])
        results = list(
            map(lambda chunk: {
                'article_url': chunk["G1Articles"].url,
                'article_title': chunk["G1Articles"].title,
                'chunk': chunk["G1Chunks"].chunk,
                'distance': float(cosine_distance(query_embedding, chunk["G1Chunks"].embedding)) if query_embedding is not None else None,
                'rrf_score': chunk.get("rrf_score"),
                'vector_rank': chunk.get("article_vector_rank"),
                'text_rank': chunk.get("article_text_rank"),
            }, [chunk for chunk in chunks if retrieval_stage == "lexical" or chunk["G1Chunks"].embedding is not None])
        )
        # guard against duplicated chunk rows (same article + same text)
        seen = set()
        deduped = []
        for result in results:
            key = (result['article_url'], result['chunk'])
            if key not in seen:
                seen.add(key)
                deduped.append(result)
        results = deduped
        unique_articles = set(result['article_url'] for result in results)
        # SQL orders chunks by score. First occurrence is each article's max
        # score, never a sum that rewards articles for having more chunks.
        hybrid_ranked = []
        vector_ranked = []
        lexical_only_ranked = []
        seen_articles = set()
        seen_vector = set()
        seen_lexical = set()
        for result in results:
            if result['article_url'] not in seen_articles:
                seen_articles.add(result['article_url'])
                hybrid_ranked.append({'article': result['article_url'], 'score': float(result['rrf_score'] or 0.0)})
            if result['article_url'] not in seen_vector and result.get('vector_rank') is not None:
                seen_vector.add(result['article_url'])
                vector_ranked.append({'article': result['article_url'], 'score': float(result['vector_rank'])})
            if result['article_url'] not in seen_lexical and result.get('text_rank') is not None:
                seen_lexical.add(result['article_url'])
                lexical_only_ranked.append({'article': result['article_url'], 'score': float(result['text_rank'])})
        # These are rank positions (smaller is better), not relevance scores.
        vector_ranked.sort(key=lambda entry: (entry['score'], entry['article']))
        lexical_only_ranked.sort(key=lambda entry: (entry['score'], entry['article']))
        diagnostics.update(returned_chunks=len(results), returned_articles=len(unique_articles))
        retrieval_id = hashlib.sha256(json.dumps({
            'query': query, 'unit': result_unit, 'stage': retrieval_stage,
            'top_k': result_top_k, 'limit': limit, 'offset': offset,
            'date_from': date_from, 'date_to': date_to,
            'quorum': quorum_threshold, 'candidate_cap': candidate_cap,
            'ranking': hybrid_ranked,
        }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result_processing_seconds = perf_counter() - processing_started
        # The result window is controlled by top_k during retrieval; don't
        # silently truncate the corresponding article records to the repo's
        # general-purpose default page size.
        step_started = perf_counter()
        articles = self.article_repository.get_all(
            in_=list(unique_articles), limit=None
        )
        articles_result = [
            {
                'title': a.title,
                'url': a.url,
                'excerpt': a.excerpt,
                'date_published': a.date_published
            } for a in articles
        ]
        article_lookup_seconds = perf_counter() - step_started
        timings = {
            "query_embedding_seconds": query_embedding_seconds,
            "hybrid_query_seconds": hybrid_query_seconds,
            "result_processing_seconds": result_processing_seconds,
            "article_lookup_seconds": article_lookup_seconds,
            "search_service_seconds": perf_counter() - search_started,
        }
        response = {
            # 'augmented_query': augmented_query,
            'results': results,
            'articles': articles_result,
            'total': len(results),
            'limit': limit,
            'offset': offset,
            'ranked': hybrid_ranked,
            'lexical_ranked': lexical_ranked,
            'vector_ranked': vector_ranked,
            'lexical_only_ranked': lexical_only_ranked,
            'diagnostics': diagnostics,
            'retrieval_id': retrieval_id,
            'result_unit': result_unit,
            'timings': timings,
        }
        return response
