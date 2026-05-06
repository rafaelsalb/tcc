import numpy as np
from sqlalchemy import insert, select, update
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

    def query_chunks(self, query_embedding: np.ndarray, top_k: int = 5):
        with Session(self.engine) as session:
            stmt = select(G1Chunks).order_by(G1Chunks.embedding.cosine_distance(query_embedding)).limit(top_k)
            results = session.execute(stmt).fetchall()
            return results

    def get_chunks_by_article(self, article: str):
        with Session(self.engine) as session:
            stmt = select(G1Chunks).where(G1Chunks.article == article)
            results = session.execute(stmt).fetchall()
            return results
