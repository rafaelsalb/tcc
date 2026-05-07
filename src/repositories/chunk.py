import numpy as np
from sqlalchemy import DateTime, cast, func, insert, select, update
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

    def query_chunks(self, query_embedding: np.ndarray, top_k: int = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None):
        with Session(self.engine) as session:
            print("Prefiltering articles by date...")
            articles_stmt = select(G1Articles.url).where(func.length(G1Articles.text_content) > 200)
            if date_from:
                articles_stmt = articles_stmt.where(G1Articles.date_published >= date_from)
            if date_to:
                articles_stmt = articles_stmt.where(G1Articles.date_published <= date_to)
            print("Querying chunks with cosine distance...")

            stmt = (
                select(G1Chunks)
                .where(G1Chunks.article.in_(articles_stmt))
                .order_by(G1Chunks.embedding.cosine_distance(query_embedding))
                .join(G1Chunks.g1_articles)
            )
            if top_k:
                stmt = stmt.limit(top_k)
            stmt = stmt.limit(limit).offset(offset)
            stmt = stmt.order_by(cast(G1Articles.date_published, DateTime).desc())
            results = session.scalars(stmt).all()
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
