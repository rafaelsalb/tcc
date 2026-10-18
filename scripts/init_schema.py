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
    "article_entity_extraction_status",
    "g1_relevance_judgments",
)


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in APPLICATION_TABLES],
        checkfirst=True,
    )
    print("Application database schema is ready.")


if __name__ == "__main__":
    main()
