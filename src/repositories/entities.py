from sqlalchemy import insert, select, tuple_
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
        assert len(articles) == len(texts) == len(types), "Length of articles, texts, and types must be the same"
        if canonicals is None:
            canonicals = [None] * len(texts)
        assert len(canonicals) == len(texts), "Length of canonicals must match texts"
        with Session(self.engine) as session:
            rows = []
            for article, text, type_, canonical in zip(articles, texts, types, canonicals):
                entity_id = self._get_or_create(session=session, text=text, type_=type_, canonical=canonical)
                if entity_id is None:
                    entity_id = self._create(session=session, text=text, type_=type_, canonical=canonical)
                rows.append({'g1_article_url': article, 'g1_entities_id': entity_id})
            if rows:
                try:
                    stmt = (
                        insert(ArticleEntities)
                        .values(rows)
                        .returning(ArticleEntities)
                    )
                    session.execute(stmt)
                except IntegrityError as e:
                    print("IntegrityError during batch_add_entities:", e)
                    session.rollback()
                    raise e
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
