"""Create the application tables in an initialized PostgreSQL database."""

from sqlalchemy import text

from db import engine
from models.models import Base


APPLICATION_TABLES = (
    "g1_sitemaps",
    "g1_articles",
    "g1_entities",
    "g1_chunks",
    "article_entities",
    "g1_relevance_judgments",
)

# Expression/functional indexes and extensions have no declarative path for
# pre-existing tables (create_all only emits DDL when creating the table), and
# the hardest ones used to exist only ad hoc on the dev machine. Without them,
# a fresh database seq-scans g1_chunks/g1_articles on every search — notably
# the GIN tsvector index that repositories/chunk.py writes its lexical
# candidate SQL against, and the pg_trgm index behind the /articles ILIKE.
INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_g1_chunks_text_search ON g1_chunks USING gin (to_tsvector('portuguese'::regconfig, chunk))",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_g1_chunks_article_chunk_md5 ON g1_chunks (article, md5(chunk))",
    "CREATE INDEX IF NOT EXISTS ix_g1_chunks_article ON g1_chunks (article)",
    "CREATE INDEX IF NOT EXISTS ix_entities_text_type ON g1_entities (text, type)",
    "CREATE INDEX IF NOT EXISTS idx_g1_entities_type ON g1_entities (type)",
    "CREATE INDEX IF NOT EXISTS idx_article_g1_entities_entity_id ON article_entities (g1_entities_id)",
)

TRGM_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS ix_g1_articles_title_trgm ON g1_articles USING gin (title gin_trgm_ops)",
)


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in APPLICATION_TABLES],
        checkfirst=True,
    )
    with engine.begin() as connection:
        for statement in (*INDEX_STATEMENTS, *TRGM_STATEMENTS):
            try:
                connection.execute(text(statement))
            except Exception as exc:  # e.g. pg_trgm contrib unavailable in the image
                print(f"WARN: skipped statement ({statement.rsplit(' ', 2)[0]}...): {exc}")
    print("Application database schema is ready.")


if __name__ == "__main__":
    main()
