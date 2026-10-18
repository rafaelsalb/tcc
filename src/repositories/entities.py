from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.models import ArticleEntities, G1Entities


class EntityRepository:
    def __init__(self, engine):
        self.engine = engine

    def get_by_id(self, entity_id: int):
        with Session(self.engine) as session:
            stmt = select(G1Entities).where(G1Entities.id == entity_id)
            result = session.execute(stmt).scalar_one_or_none()
            return result

    def get_all(self, limit: int = 100, offset: int = 0):
        with Session(self.engine) as session:
            stmt = select(G1Entities).limit(limit).offset(offset)
            results = session.execute(stmt).fetchall()
            return results

    def _get_or_create(self, session: Session, text: str, type_: str, canonical: str | None = None) -> int | None:
        stmt = select(G1Entities).where(G1Entities.text_ == text).where(G1Entities.type == type_)
        existing = session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            if canonical and not existing.canonical:
                existing.canonical = canonical
                session.flush()
            return existing.id
        return None

    def _create(self, session: Session, text: str, type_: str, canonical: str | None = None) -> int:
        stmt = insert(G1Entities).values(text=text, type=type_, canonical=canonical).returning(G1Entities.id)
        try:
            entity_id = session.execute(stmt).scalar_one()
            return entity_id
        except Exception as e:
            session.rollback()
            raise e

    def batch_create(self, session: Session, texts: list[str], types: list[str], canonicals: list[str | None] = None) -> list[G1Entities]:
        canonicals = canonicals if canonicals is not None else [None] * len(texts)
        pairs = [(text, type_, canonical) for text, type_, canonical in zip(texts, types, canonicals)]
        if not pairs:
            return []
        to_insert = [{'text': text, 'type': type_, 'canonical': canonical} for text, type_, canonical in pairs]

        stmt = (
            pg_insert(G1Entities)
            .values(to_insert)
            .on_conflict_do_nothing(index_elements=[G1Entities.text_, G1Entities.type])
            .returning(G1Entities)
        )
        try:
            result = session.scalars(stmt).all()
            return result
            # return entity_ids
        except IntegrityError as e:
            print("IntegrityError during batch_create:", e)
            session.rollback()
            print("IntegrityError during batch_create:", e)

    def add_entity_to_article(self, article: str, entity_id: int):
        with Session(self.engine) as session:
            stmt = insert(ArticleEntities).values(g1_article_url=article, g1_entities_id=entity_id)
            session.execute(stmt)
            session.commit()

    def add_entity(self, article: str, text: str, type_: str):
        with Session(self.engine) as session:
            entity_id = self._get_or_create(session=session, text=text, type_=type_)
            stmt = insert(ArticleEntities).values(g1_article_url=article, g1_entities_id=entity_id)
            session.execute(stmt)
            session.commit()

    def batch_add_entities(self, articles: list[str], texts: list[str], types: list[str], canonicals: list[str | None] = None):
        if not (len(articles) == len(texts) == len(types)):
            raise ValueError("articles, texts, and types must have the same length")
        if canonicals is None:
            canonicals = [None] * len(texts)
        if len(canonicals) != len(texts):
            raise ValueError("canonicals must have the same length as texts")
        if not texts:
            return

        # Deduplicate before ON CONFLICT: PostgreSQL rejects a single upsert
        # statement that would affect the same unique entity more than once.
        entity_values = {}
        association_values = set()
        for article, text_, type_, canonical in zip(articles, texts, types, canonicals):
            key = (text_, type_)
            if key not in entity_values or (entity_values[key]["canonical"] is None and canonical):
                entity_values[key] = {"text": text_, "type": type_, "canonical": canonical}
            association_values.add((article, text_, type_))

        with Session(self.engine) as session:
            entity_insert = pg_insert(G1Entities).values(list(entity_values.values()))
            excluded = entity_insert.excluded
            entity_stmt = entity_insert.on_conflict_do_update(
                index_elements=[G1Entities.text_, G1Entities.type],
                set_={"canonical": func.coalesce(G1Entities.canonical, excluded.canonical)},
            ).returning(G1Entities.id, G1Entities.text_, G1Entities.type)
            entity_ids = {
                (row.text, row.type): row.id
                for row in session.execute(entity_stmt).all()
            }

            existing = set()
            article_urls = {article for article, _, _ in association_values}
            if article_urls:
                existing_stmt = (
                    select(ArticleEntities.g1_article_url, G1Entities.text_, G1Entities.type)
                    .join(G1Entities, ArticleEntities.g1_entities_id == G1Entities.id)
                    .where(ArticleEntities.g1_article_url.in_(article_urls))
                )
                existing = {tuple(row) for row in session.execute(existing_stmt).all()}

            rows = [
                {"g1_article_url": article, "g1_entities_id": entity_ids[(text_, type_)]}
                for article, text_, type_ in association_values
                if (article, text_, type_) not in existing
            ]
            if rows:
                session.execute(insert(ArticleEntities), rows)
            session.commit()

    def mark_empty_extractions(self, article_urls: list[str], extractor_version: str):
        """Remember successful NER passes that found no entity mentions."""
        urls = list(dict.fromkeys(article_urls))
        if not urls:
            return
        from models.models import ArticleEntityExtractionStatus

        stmt = pg_insert(ArticleEntityExtractionStatus).values([
            {"article_url": url, "extractor_version": extractor_version}
            for url in urls
        ]).on_conflict_do_update(
            index_elements=[ArticleEntityExtractionStatus.article_url],
            set_={"extractor_version": extractor_version, "processed_at": func.now()},
        )
        with Session(self.engine) as session:
            session.execute(stmt)
            session.commit()

    def get_entities_by_article(self, article: str):
        with Session(self.engine) as session:
            stmt = (
                select(G1Entities)
                .join(ArticleEntities, ArticleEntities.g1_entities_id == G1Entities.id)
                .where(ArticleEntities.g1_article_url == article)
            )
            results = session.execute(stmt).fetchall()
            return results
