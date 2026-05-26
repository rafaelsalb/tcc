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

    def _get_or_create(self, session: Session, text: str, type_: str) -> int:
        stmt = select(G1Entities.id).where(G1Entities.text_ == text).where(G1Entities.type == type_)
        existing = session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing

    def _create(self, session: Session, text: str, type_: str) -> int:
        stmt = insert(G1Entities).values(text=text, type=type_).returning(G1Entities.id)
        try:
            entity_id = session.execute(stmt).scalar_one()
            return entity_id
        except Exception as e:
            session.rollback()
            raise e

    def batch_create(self, session: Session, texts: list[str], types: list[str]) -> list[G1Entities]:
        pairs = [(text, type_) for text, type_ in zip(texts, types)]
        if not pairs:
            return []
        to_insert = [{'text': text, 'type': type_} for text, type_ in pairs]

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

    def batch_add_entities(self, articles: list[str], texts: list[str], types: list[str]):
        assert len(articles) == len(texts) == len(types), "Length of articles, texts, and types must be the same"
        with Session(self.engine) as session:
            rows = []
            for article, text, type_ in zip(articles, texts, types):
                entity_id = self._get_or_create(session=session, text=text, type_=type_)
                if entity_id is None:
                    entity_id = self._create(session=session, text=text, type_=type_)
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
