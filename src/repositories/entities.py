from sqlalchemy import func, insert, select, tuple_
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.models import ArticleEntities, G1Entities


class EntityRepository:
    def __init__(self, engine):
        self.engine = engine
        self._article_entities_unique_index: bool | None = None

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
        except IntegrityError as e:
            # Concurrent writers may win the unique (text, type) race between
            # the SELECT-less upsert inference; report empty instead of crashing
            # the caller with an implicit None.
            session.rollback()
            print("IntegrityError during batch_create:", e)
            return []

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
        # Resolve every unique (text, type) identity with a single SELECT and a
        # single upsert instead of two round trips per mention (the previous
        # _get_or_create/_create N+1 also rolled back the entire transaction
        # on any failure, discarding the entities created so far).
        unique_pairs = sorted(set(zip(texts, types)))
        if not unique_pairs:
            return
        canonical_by_pair: dict[tuple[str, str], str | None] = {pair: None for pair in unique_pairs}
        for text_, type_, canonical in zip(texts, types, canonicals):
            if canonical and canonical_by_pair[(text_, type_)] is None:
                canonical_by_pair[(text_, type_)] = canonical
        with Session(self.engine) as session:
            existing = session.execute(
                select(G1Entities).where(tuple_(G1Entities.text_, G1Entities.type).in_(unique_pairs))
            ).scalars().all()
            entities_by_pair = {(row.text_, row.type): row for row in existing}
            missing = [
                {'text': text_, 'type': type_, 'canonical': canonical_by_pair[(text_, type_)]}
                for (text_, type_) in unique_pairs
                if (text_, type_) not in entities_by_pair
            ]
            if missing:
                insert_stmt = pg_insert(G1Entities).values(missing)
                # ON CONFLICT DO UPDATE (not DO NOTHING) also returns the row
                # when a concurrent writer inserted it first, and coalesce
                # lets an already-set canonical win over an empty one.
                stmt = insert_stmt.on_conflict_do_update(
                    index_elements=[G1Entities.text_, G1Entities.type],
                    set_={"canonical": func.coalesce(G1Entities.canonical, insert_stmt.excluded.canonical)},
                ).returning(G1Entities)
                for row in session.scalars(stmt).all():
                    entities_by_pair[(row.text_, row.type)] = row
            # Backfill canonical on pre-existing rows without one.
            for text_, type_ in unique_pairs:
                row = entities_by_pair[(text_, type_)]
                canonical = canonical_by_pair[(text_, type_)]
                if canonical and not row.canonical:
                    row.canonical = canonical
            rows = []
            seen_pairs = set()
            for article, text_, type_ in zip(articles, texts, types):
                entity_id = entities_by_pair[(text_, type_)].id
                pair = (article, entity_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                rows.append({'g1_article_url': article, 'g1_entities_id': entity_id})
            if rows:
                # pg_insert without a conflict clause renders a plain INSERT,
                # so it is safe for the pre-migration path too.
                mention_stmt = pg_insert(ArticleEntities).values(rows)
                if self.has_article_entities_unique_index():
                    # scripts/migrate_article_entities.py installs the unique
                    # index; ignore duplicate mentions from concurrent writers.
                    mention_stmt = mention_stmt.on_conflict_do_nothing(
                        index_elements=[ArticleEntities.g1_article_url, ArticleEntities.g1_entities_id]
                    )
                session.execute(mention_stmt)
            session.commit()

    def has_article_entities_unique_index(self) -> bool:
        """Whether (g1_article_url, g1_entities_id) is unique — installed by
        scripts/migrate_article_entities.py. Detection is cached per instance."""
        if self._article_entities_unique_index is None:
            with Session(self.engine) as session:
                exists = session.execute(
                    sql_text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_article_entities_article_entity')")
                ).scalar()
            self._article_entities_unique_index = bool(exists)
        return self._article_entities_unique_index

    def get_entities_by_article(self, article: str):
        with Session(self.engine) as session:
            stmt = (
                select(G1Entities)
                .join(ArticleEntities, ArticleEntities.g1_entities_id == G1Entities.id)
                .where(ArticleEntities.g1_article_url == article)
            )
            results = session.execute(stmt).fetchall()
            return results
