import numpy as np
from sqlalchemy import DateTime, cast, func, insert, literal, select, update
from sqlalchemy.orm import Session

from models.models import G1Articles, G1Chunks


class ChunkRepository:
    def __init__(self, engine):
        self.engine = engine

    def add_chunk(self, article: str, chunk: str, embedding: np.ndarray):
        new_chunk = G1Chunks.insert().values(article=article, chunk=chunk, embedding=embedding)
        with Session(self.engine) as session:
            session.execute(new_chunk)
            session.commit()

    def batch_add_chunk(self, articles: list[str], chunks: list[str], embeddings: list[np.ndarray]):
        new_chunks = []
        for article, chunk, embedding in zip(articles, chunks, embeddings):
            new_chunks.append({'article': article, 'chunk': chunk, 'embedding': embedding})
        with Session(self.engine) as session:
            stmt = insert(G1Chunks).values(new_chunks)
            session.execute(stmt)
            session.commit()
            stmt = update(G1Articles).where(G1Articles.url.in_(articles)).values(is_chunked=True)
            session.execute(stmt)
            session.commit()

    def query_chunks(self, query_embedding: np.ndarray, top_k: int = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None, exact: bool = False) -> list[dict[str, G1Chunks | G1Articles]]:
        with Session(self.engine) as session:
            if exact:
                session.execute(func.set_config("enable_indexscan", "off", True))
                session.execute(func.set_config("enable_bitmapscan", "off", True))
                session.execute(func.set_config("enable_seqscan", "on", True))
            else:
                session.execute(func.set_config("hnsw.ef_search", str(max(40, min(limit, 1000))), True))
            print("Prefiltering articles by date...")
            articles_stmt = select(G1Articles.url) #.where(func.length(G1Articles.text_content) > 200)
            if date_from:
                articles_stmt = articles_stmt.where(G1Articles.date_published >= date_from)
            if date_to:
                articles_stmt = articles_stmt.where(G1Articles.date_published <= date_to)
            print("Querying chunks with cosine distance...")

            stmt = (
                select(G1Chunks, G1Articles)
                .where(G1Chunks.article.in_(articles_stmt))
                .order_by(G1Chunks.embedding.cosine_distance(query_embedding))
                .join(G1Chunks.g1_articles)
            )
            if top_k:
                stmt = stmt.limit(top_k)
            stmt = stmt.limit(limit).offset(offset)
            stmt = stmt.order_by(G1Articles.date_published)
            results = session.execute(stmt).mappings().all()
            print("first result:", results[0])
            return results

    def query_chunks_hybrid(
        self,
        query_text: str,
        query_embedding: np.ndarray,
        top_k: int = 5,
        limit: int = 100,
        offset: int = 0,
        date_from: str = None,
        date_to: str = None,
        alpha: float = 0.5,
        language: str = "portuguese",
        rrf_k: int = 60,
        exact: bool = True,
    ) -> list[dict[str, G1Chunks | G1Articles]]:
        with Session(self.engine) as session:
            if exact:
                session.execute(func.set_config("enable_indexscan", "off", True))
                session.execute(func.set_config("enable_bitmapscan", "off", True))
                session.execute(func.set_config("enable_seqscan", "on", True))
            else:
                session.execute(func.set_config("hnsw.ef_search", str(max(40, min(limit, 1000))), True))
            print("Prefiltering articles by date...")
            articles_stmt = select(G1Articles.url)
            if date_from:
                articles_stmt = articles_stmt.where(G1Articles.date_published >= date_from)
            if date_to:
                articles_stmt = articles_stmt.where(G1Articles.date_published <= date_to)

            print("Querying chunks with hybrid search (tsvector + cosine distance)...")

            vector_distance = G1Chunks.embedding.cosine_distance(query_embedding)

            tsvector_expr = func.to_tsvector(language, G1Chunks.chunk)
            tsquery_expr = func.plainto_tsquery(language, query_text)
            text_rank = func.ts_rank_cd(tsvector_expr, tsquery_expr)

            vector_score = 1 - vector_distance
            hybrid_score = (alpha * vector_score) + ((1 - alpha) * text_rank)

            vector_rank = func.rank().over(order_by=vector_distance)
            text_rank_position = func.rank().over(order_by=text_rank.desc())

            rrf_score = (literal(1.0) / (rrf_k + vector_rank)) + (literal(1.0) / (rrf_k + text_rank_position))

            stmt = (
                select(
                    G1Chunks,
                    G1Articles,
                    hybrid_score.label("hybrid_score"),
                    rrf_score.label("rrf_score"),
                    vector_rank.label("vector_rank"),
                    text_rank_position.label("text_rank")
                )
                .where(G1Chunks.article.in_(articles_stmt))
                .where(tsvector_expr.op("@@")(tsquery_expr))
                .order_by(rrf_score.desc())
                .join(G1Chunks.g1_articles)
            )
            if top_k:
                stmt = stmt.limit(top_k)
            stmt = stmt.limit(limit).offset(offset)
            results = session.execute(stmt).mappings().all()
            if results:
                print("first result:", results[0])
                return results

    def get_chunks_by_article(self, article: str):
        with Session(self.engine) as session:
            stmt = select(G1Chunks).where(G1Chunks.article == article)
            results = session.execute(stmt).fetchall()
            return results

    def get_all_with_no_embeddings(self, limit: int = 100, offset: int = 0):
        with Session(self.engine) as session:
            stmt = select(G1Chunks.id, G1Chunks.chunk).where(G1Chunks.embedding.is_(None)).limit(limit).offset(offset)
            results = session.execute(stmt).fetchall()
            return results

    def update_embedding(self, chunk_id: int, embedding: np.ndarray):
        with Session(self.engine) as session:
            stmt = update(G1Chunks).where(G1Chunks.id == chunk_id).values(embedding=embedding)
            session.execute(stmt)
            session.commit()

    def batch_update_embeddings(self, chunk_ids: list[int], embeddings: list[np.ndarray]):
        with Session(self.engine) as session:
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                stmt = update(G1Chunks).where(G1Chunks.id == chunk_id).values(embedding=embedding)
                session.execute(stmt)
            session.commit()
