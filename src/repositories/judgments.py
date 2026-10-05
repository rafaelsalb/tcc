import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from models.models import G1Articles, G1RelevanceJudgments


class JudgmentRepository:
    def __init__(self, engine):
        self.engine = engine
        self._ensure_table()

    def _ensure_table(self):
        """Idempotent DDL — the project has no migration tooling, so the table
        is created on first use without touching any existing schema."""
        with Session(self.engine) as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS g1_relevance_judgments (
                    id BIGSERIAL PRIMARY KEY,
                    label TEXT NOT NULL,
                    article_url TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT fk_g1_relevance_judgments_article
                        FOREIGN KEY (article_url) REFERENCES g1_articles (url),
                    CONSTRAINT uq_g1_relevance_judgments_label_article
                        UNIQUE (label, article_url)
                )
            """))
            session.commit()

    def replace_all(self, label: str, urls: list[str]):
        """Make the stored set for `label` exactly equal to `urls`."""
        unique_urls = list(dict.fromkeys(urls))
        with Session(self.engine) as session:
            if unique_urls:
                existing = set(
                    session.execute(select(G1Articles.url).where(G1Articles.url.in_(unique_urls))).scalars()
                )
                missing = [url for url in unique_urls if url not in existing]
                if missing:
                    raise ValueError(f"unknown article urls: {missing[:5]}")
            session.execute(delete(G1RelevanceJudgments).where(G1RelevanceJudgments.label == label))
            if unique_urls:
                session.execute(
                    G1RelevanceJudgments.__table__.insert(),
                    [{"label": label, "article_url": url} for url in unique_urls],
                )
            session.commit()

    def list_by_label(self, label: str) -> list[str]:
        with Session(self.engine) as session:
            stmt = select(G1RelevanceJudgments.article_url).where(G1RelevanceJudgments.label == label)
            return list(session.execute(stmt).scalars())

    def list_labels(self) -> list[dict]:
        with Session(self.engine) as session:
            stmt = (
                select(
                    G1RelevanceJudgments.label,
                    func.count().label("article_count"),
                    func.max(G1RelevanceJudgments.created_at).label("updated_at"),
                )
                .group_by(G1RelevanceJudgments.label)
                .order_by(func.max(G1RelevanceJudgments.created_at).desc())
            )
            rows = session.execute(stmt).all()
            return [{"label": row.label, "article_count": row.article_count, "updated_at": row.updated_at} for row in rows]
