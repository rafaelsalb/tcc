from models.models import ArticleEntities
from sqlalchemy import func, select
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

    def get_all(self, limit: int | None = 100, offset: int = 0, in_: list[str] = None, order_by: str = "date_published") -> list[G1Articles]:
        with Session(self.engine) as session:
            stmt = select(G1Articles)
            if in_:
                stmt = stmt.where(G1Articles.url.in_(in_))
            if limit is not None:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)
            if order_by:
                stmt = stmt.order_by(getattr(G1Articles, order_by))
            return session.scalars(stmt).all()

    def get_all_with_no_chunks(self, limit: int = 50, offset: int = 0) -> list[G1Articles]:
        with Session(self.engine) as session:
            stmt = select(G1Articles).where(G1Articles.text_content.is_not(None)).where(G1Articles.is_chunked.is_not(True)).limit(limit).offset(offset)
            # fetchall()[0] used to collapse the batch into a single Row, so
            # only the first article was processed per 50-row fetch.
            return session.scalars(stmt).all()

    def get_all_with_no_entities(self, limit: int = 50, offset: int = 0,
                                 worker_i: int = 0, total_workers: int = 1) -> list[G1Articles]:
        """Articles with no mention rows yet. With `total_workers > 1`, the list
        is partitioned deterministically by url hash so concurrent populate
        daemons never pick the same articles ((hashtext(url) & 0x7fffffff)
        % N == i)."""
        with Session(self.engine) as session:
            stmt = (
                select(G1Articles)
                .outerjoin(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
                .where(ArticleEntities.g1_article_url.is_(None))
                .where(G1Articles.text_content.is_not(None))
                # & runs before % in SQLAlchemy's expression tree, unlike raw SQL
                # operator precedence; masking hashtext to positive int avoids
                # int4 abs() overflow and negative-modulo drift.
                .where((func.hashtext(G1Articles.url).op("&")(2147483647) % total_workers) == worker_i)
                .limit(limit)
                .offset(offset)
            )
            results = session.scalars(stmt).all()
            return results

    def search_by_title(self, q: str, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """Paginated title search over the whole article database (evaluation tab).

        Empty q browses the most recent articles with at least one embedded chunk.
        Never selects text_content.
        """
        with Session(self.engine) as session:
            has_embedded_chunk = (
                select(G1Chunks.id)
                .where(
                    G1Chunks.article == G1Articles.url,
                    G1Chunks.embedding.is_not(None),
                )
                .exists()
            )
            base = (
                select(G1Articles.url, G1Articles.title, G1Articles.excerpt, G1Articles.date_published)
                .where(has_embedded_chunk)
            )
            if q:
                base = base.where(G1Articles.title.ilike(f"%{q}%"))
            count_stmt = select(func.count()).select_from(base.subquery())
            total = session.execute(count_stmt).scalar_one()
            stmt = base.order_by(G1Articles.date_published.desc().nullslast(), G1Articles.url).limit(limit).offset(offset)
            rows = session.execute(stmt).all()
            articles = [
                {"url": row.url, "title": row.title, "excerpt": row.excerpt, "date_published": row.date_published}
                for row in rows
            ]
            return articles, total
