"""One-time migration: collapse duplicate (article, entity) mention rows and
install the unique index that prevents them from recurring.

The live database accumulated ~239k duplicate (g1_article_url, g1_entities_id)
groups out of 1.6M rows because re-extraction ran without any uniqueness
guarantee. Run this with populate/API jobs that write article_entities paused
(CREATE UNIQUE INDEX fails while duplicates remain):

    uv run python scripts/migrate_article_entities.py            # dry run
    uv run python scripts/migrate_article_entities.py --apply    # perform it
"""

import argparse
import sys

from sqlalchemy import text

from db import engine

UNIQUE_INDEX = "uq_article_entities_article_entity"


def main(apply: bool) -> int:
    with engine.begin() as connection:
        duplicate_groups = connection.execute(text("""
            SELECT count(*) FROM (
                SELECT g1_article_url, g1_entities_id, count(*) AS mentions
                FROM article_entities
                GROUP BY 1, 2
                HAVING count(*) > 1
            ) d
        """)).scalar_one()
        print(f"Duplicate (g1_article_url, g1_entities_id) groups: {duplicate_groups}")
        if not apply:
            print("Dry run: nothing changed. Pass --apply to migrate.")
            return 0
        if duplicate_groups:
            result = connection.execute(text("""
                DELETE FROM article_entities a
                USING article_entities b
                WHERE a.g1_article_url = b.g1_article_url
                  AND a.g1_entities_id = b.g1_entities_id
                  AND a.id > b.id
            """))
            print(f"Deleted {result.rowcount} duplicate row(s).")
        connection.execute(text(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX}
            ON article_entities (g1_article_url, g1_entities_id)
        """))
        print(f"Unique index {UNIQUE_INDEX} is in place; duplicate mentions are now impossible.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Perform the dedupe and create the unique index.")
    sys.exit(main(parser.parse_args().apply))
