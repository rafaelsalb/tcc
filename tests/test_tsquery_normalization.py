"""Read-only PostgreSQL regressions for already-normalized Portuguese lexemes."""

import os
from pathlib import Path
import re

from dotenv import load_dotenv
import psycopg
import pytest

from repositories import chunk


@pytest.fixture
def connection():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    dsn = os.getenv('POSTGRES_DSN')
    if not dsn:
        pytest.skip('POSTGRES_DSN is required for PostgreSQL text-search regressions')
    dsn = dsn.replace('postgresql+psycopg2://', 'postgresql://').replace('postgresql+psycopg://', 'postgresql://')
    with psycopg.connect(dsn, options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        yield conn


def test_benicio_normalized_query_matches_itself_without_second_stemming(connection):
    query = 'Benício adrenalina'
    lexemes = connection.execute("SELECT tsvector_to_array(to_tsvector('portuguese', %s))", (query,)).fetchone()[0]
    subset, exact = chunk._subset_tsquery(lexemes, 0.7)
    assert exact
    original, fixed, changed_term = connection.execute('''SELECT
        to_tsvector('portuguese', %s) @@ to_tsquery('portuguese', %s),
        to_tsvector('portuguese', %s) @@ CAST(%s AS tsquery),
        to_tsquery('portuguese', %s)::text <> CAST(%s AS tsquery)::text''',
        (query, subset, query, subset, subset, subset)).fetchone()
    assert not original and fixed and changed_term


@pytest.mark.parametrize('fallback', [False, True])
def test_actual_templates_preserve_normalized_filter_and_scoring_terms(connection, monkeypatch, fallback):
    # Synthetic SELECT-only CTEs shadow the production tables: no corpus writes.
    query = 'Benício adrenalina hospital Manaus' if fallback else 'Benício adrenalina'
    good = 'Benício recebeu adrenalina no hospital em Manaus'
    lexemes = connection.execute("SELECT tsvector_to_array(to_tsvector('portuguese', %s))", (query,)).fetchone()[0]
    if fallback:
        monkeypatch.setattr(chunk, 'MAX_SUBSET_COMBINATIONS', 1)
    subset, exact = chunk._subset_tsquery(lexemes, 0.7)
    assert exact is not fallback
    or_query = ' | '.join(chunk._quote_lexeme(term) for term in lexemes)
    template = chunk.CANDIDATES_FALLBACK_TEMPLATE if fallback else chunk.CANDIDATES_FAST_TEMPLATE
    sql = template.format(language='portuguese').replace('WITH query_prep AS', '''WITH
        g1_articles AS (SELECT 'a'::text AS url, DATE '2025-06-01' AS date_published),
        g1_chunks AS (SELECT 1::bigint AS id, 'a'::text AS article, %(good)s::text AS chunk
                     UNION ALL SELECT 2, 'a', 'adrenalina no parque'),
        query_prep AS''', 1)
    sql = re.sub(r'(?<!:):([a-z_]+)', r'%(\1)s', sql)
    rows = connection.execute(sql, {
        'subset_query': subset, 'or_query': or_query, 'query_text': query,
        'candidate_cap': 100, 'date_from': None, 'date_to': None,
        'quorum_threshold': 0.7, 'good': good,
    }).fetchall()
    assert [row[0] for row in rows] == [1]
    expected = connection.execute("SELECT ts_rank(to_tsvector('portuguese', %s), CAST(%s AS tsquery))", (good, or_query)).fetchone()[0]
    assert rows[0][2] == pytest.approx(expected)


def test_quoted_lexemes_are_literals_not_operators_and_preserve_backslashes(connection):
    terms = ["beníci", "d'água", r'a\b', 'a&b', 'x|y']
    query = ' & '.join(chunk._quote_lexeme(term) for term in terms)
    matches, nodes = connection.execute('''SELECT
        array_to_tsvector(%s::text[]) @@ CAST(%s AS tsquery),
        numnode(CAST(%s AS tsquery))''', (terms, query, query)).fetchone()
    assert matches
    assert nodes == 2 * len(terms) - 1
