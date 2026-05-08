from models.models import ArticleEntities
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import G1Articles, G1Chunks


class ArticleRepository:
    def __init__(self, engine):
        self.engine = engine

    def get_by_id(self, url: str):
        with Session(self.engine) as session:
            stmt = select(G1Articles).where(G1Articles.url == url)
            result = session.execute(stmt).scalar_one_or_none()
            return result

    def get_all(self, limit: int = 100, offset: int = 0):
        with Session(self.engine) as session:
            stmt = select(G1Articles).limit(limit).offset(offset)
            results = session.execute(stmt).fetchall()
            return results

    def get_all_with_no_chunks(self, limit: int = 50, offset: int = 0) -> list[G1Articles]:
        with Session(self.engine) as session:
            stmt = select(G1Articles).where(G1Articles.text_content.is_not(None)).where(G1Articles.is_chunked.is_not(True)).limit(limit).offset(offset)
            results = session.execute(stmt).fetchall()
            results = results[0]
            return results

    def get_all_with_no_entities(self, limit: int = 50, offset: int = 0) -> list[G1Articles]:
        with Session(self.engine) as session:
            stmt = (
                select(G1Articles)
                .outerjoin(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
                .where(ArticleEntities.g1_article_url.is_(None))
                .limit(limit)
                .offset(offset)
            )
            results = session.scalars(stmt).all()
            print(results)
            return results
