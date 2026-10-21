import itertools
import math

import numpy as np
from sqlalchemy import BigInteger, DateTime, Float, bindparam, cast, delete, func, insert, literal, select, text, update
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Session

from models.models import G1Articles, G1Chunks

# The tsquery language must be inlined as a literal (not a bind parameter) so
# that to_tsvector(:language, chunk) matches the expression indexed by
# idx_g1_chunks_text_search. Only whitelisted values are accepted.
ALLOWED_TSQUERY_LANGUAGES = {"portuguese"}

# Above this many k-subset combinations the OR-of-k-ANDs tsquery stops being
# worth building and the fallback (pair filter + per-row quorum) takes over.
MAX_SUBSET_COMBINATIONS = 5000

# Simulated WAND candidate generation (minimum_should_match in SQL):
#   Phase 1 — GIN-resolved quorum: OR over all k-way ANDs of the query lexemes
#     (k = ceil(len * threshold)). A chunk matches iff it shares >= k lexemes
#     with the query, resolved inside the index (no per-row work).
#   Fallback — when C(len, k) explodes: pairwise-AND filter (>= 2 lexemes,
#     also index-resolved) followed by a per-row quorum count in SQL.
#   Scoring — BM25 approximated by ts_rank against the full OR query, applied
#     only to quorum survivors, then capped.
CANDIDATES_FAST_TEMPLATE = """
    WITH query_prep AS (
        SELECT
            CAST(:subset_query AS tsquery) AS subset_query,
            CAST(:or_query AS tsquery) AS or_query
    ),
    candidates AS (
        SELECT c.id, to_tsvector('{language}', c.chunk) AS doc_tsv
        FROM g1_chunks c
        JOIN g1_articles a ON a.url = c.article
        CROSS JOIN query_prep qp
        WHERE to_tsvector('{language}', c.chunk) @@ qp.subset_query
          AND (CAST(:date_from AS date) IS NULL OR a.date_published >= CAST(:date_from AS date))
          AND (CAST(:date_to AS date) IS NULL OR a.date_published <= CAST(:date_to AS date))
    ),
    scored AS (
        SELECT ca.id, ca.doc_tsv, ts_rank(ca.doc_tsv, qp.or_query) AS bm25
        FROM candidates ca CROSS JOIN query_prep qp
    )
    SELECT id, doc_tsv, bm25
    FROM scored
    ORDER BY bm25 DESC, id
    LIMIT :candidate_cap
"""

CANDIDATES_FALLBACK_TEMPLATE = """
    WITH query_prep AS (
        SELECT
            CAST(:subset_query AS tsquery) AS subset_query,
            CAST(:or_query AS tsquery) AS or_query,
            tsvector_to_array(to_tsvector('{language}', :query_text)) AS query_lexemes,
            coalesce(array_length(tsvector_to_array(to_tsvector('{language}', :query_text)), 1), 0) AS lexeme_count
    ),
    candidates AS (
        SELECT c.id, to_tsvector('{language}', c.chunk) AS doc_tsv
        FROM g1_chunks c
        JOIN g1_articles a ON a.url = c.article
        CROSS JOIN query_prep qp
        WHERE to_tsvector('{language}', c.chunk) @@ qp.subset_query
          AND (CAST(:date_from AS date) IS NULL OR a.date_published >= CAST(:date_from AS date))
          AND (CAST(:date_to AS date) IS NULL OR a.date_published <= CAST(:date_to AS date))
    ),
    quorum AS (
        SELECT ca.id, ca.doc_tsv,
               (SELECT count(*) FROM unnest(tsvector_to_array(ca.doc_tsv)) AS doc_lex
                 WHERE doc_lex = ANY (qp.query_lexemes)) AS matched_lexemes,
               qp.lexeme_count
        FROM candidates ca CROSS JOIN query_prep qp
    ),
    scored AS (
        SELECT q.id, q.doc_tsv, ts_rank(q.doc_tsv, qp.or_query) AS bm25
        FROM quorum q CROSS JOIN query_prep qp
        WHERE q.matched_lexemes >= q.lexeme_count * :quorum_threshold
    )
    SELECT id, doc_tsv, bm25
    FROM scored
    ORDER BY bm25 DESC, id
    LIMIT :candidate_cap
"""


def _quote_lexeme(lexeme: str) -> str:
    return "'" + lexeme.replace("\\", "\\\\").replace("'", "''") + "'"


def _hnsw_ef_search(top_k: int | None, limit: int) -> int:
    """Use `limit` as HNSW search breadth, never as the result-row limit."""
    return max(40, int(top_k or 0), min(int(limit), 1000))


def _apply_result_window(stmt, top_k: int | None, offset: int):
    """Apply the search result count and pagination exactly once."""
    if top_k is not None:
        stmt = stmt.limit(top_k)
    if offset:
        stmt = stmt.offset(offset)
    return stmt


def _ranked_chunk_window(scored, top_k, offset, result_unit):
    """Score all candidates first; article mode limits groups, not chunk rows."""
    if result_unit == "chunks":
        return _apply_result_window(
            select(scored).order_by(scored.c.score.desc(), scored.c.chunk_id), top_k, offset
        ).cte("selected_chunks")
    articles = _apply_result_window(
        select(scored.c.article, func.max(scored.c.score).label("article_score"))
        .group_by(scored.c.article)
        .order_by(func.max(scored.c.score).desc(), scored.c.article), top_k, offset,
    ).cte("selected_articles")
    representatives = select(
        scored,
        func.row_number().over(
            partition_by=scored.c.article,
            order_by=(scored.c.score.desc(), scored.c.chunk_id),
        ).label("article_position"),
    ).cte("representative_chunks")
    return select(representatives).join(
        articles, representatives.c.article == articles.c.article
    ).where(representatives.c.article_position == 1).cte("selected_chunks")


def _subset_tsquery(lexemes: list[str], quorum_threshold: float) -> tuple[str | None, bool]:
    """Build the Phase-1 tsquery text and report whether the index filter
    already enforces the full quorum (exact) or only a lower bound (fallback).

    Returns (tsquery_text, exact). None means the query has no valid lexemes.
    These lexemes are already normalized: CAST the result to tsquery; do not
    feed it to a language-specific to_tsquery and stem it a second time.
    """
    n = len(lexemes)
    if n == 0:
        return None, True
    k = max(1, math.ceil(n * quorum_threshold))
    k_fast = k
    while k_fast > 1 and math.comb(n, k_fast) > MAX_SUBSET_COMBINATIONS:
        k_fast -= 1
    ands = [
        " & ".join(_quote_lexeme(lexeme) for lexeme in combination)
        for combination in itertools.combinations(lexemes, k_fast)
    ]
    # exact when the index resolves the full quorum (k_fast == k) or when a
    # single lexeme suffices (k == 1: matching the lexeme IS the quorum)
    exact = k_fast == k or k == 1
    return " | ".join(ands), exact


class ChunkRepository:
    def __init__(self, engine):
        self.engine = engine

    def add_chunk(self, article: str, chunk: str, embedding: np.ndarray):
        new_chunk = G1Chunks.insert().values(article=article, chunk=chunk, embedding=embedding)
        with Session(self.engine) as session:
            session.execute(new_chunk)
            session.commit()

    def batch_add_chunk(self, articles: list[str], chunks: list[str], embeddings: list[np.ndarray]):
        # single transaction: re-chunking an article replaces its previous
        # chunks, and a crash rolls everything back (no orphan rows without
        # the is_chunked flag, which previously caused duplicate chunks)
        new_chunks = [
            {'article': article, 'chunk': chunk, 'embedding': embedding}
            for article, chunk, embedding in zip(articles, chunks, embeddings)
        ]
        with Session(self.engine) as session:
            session.execute(delete(G1Chunks).where(G1Chunks.article.in_(set(articles))))
            if new_chunks:
                session.execute(insert(G1Chunks).values(new_chunks))
            session.execute(update(G1Articles).where(G1Articles.url.in_(set(articles))).values(is_chunked=True))
            session.commit()

    def query_chunks(self, query_embedding: np.ndarray, top_k: int = 5, limit: int = 100, offset: int = 0, date_from: str = None, date_to: str = None, exact: bool = False) -> list[dict[str, G1Chunks | G1Articles]]:
        with Session(self.engine) as session:
            if exact:
                session.execute(func.set_config("enable_indexscan", "off", True))
                session.execute(func.set_config("enable_bitmapscan", "off", True))
                session.execute(func.set_config("enable_seqscan", "on", True))
            else:
                ef_search = _hnsw_ef_search(top_k, limit)
                session.execute(func.set_config("hnsw.ef_search", str(ef_search), True))
            print("Prefiltering articles by date...")
            articles_stmt = select(G1Articles.url) #.where(func.length(G1Articles.text_content) > 200)
            if date_from:
                articles_stmt = articles_stmt.where(G1Articles.date_published >= date_from)
            if date_to:
                articles_stmt = articles_stmt.where(G1Articles.date_published <= date_to)
            print("Querying chunks with cosine distance...")

            stmt = (
                select(G1Chunks, G1Articles)
                .where(G1Chunks.article.in_(articles_stmt))
                .order_by(G1Chunks.embedding.cosine_distance(query_embedding))
                .join(G1Chunks.g1_articles)
            )
            stmt = _apply_result_window(stmt, top_k, offset)
            stmt = stmt.order_by(G1Articles.date_published)
            results = session.execute(stmt).mappings().all()
            print("first result:", results[0])
            return results

    def query_chunks_hybrid(
        self,
        query_text: str,
        query_embedding: np.ndarray,
        top_k: int = 5,
        limit: int = 100,
        offset: int = 0,
        date_from: str = None,
        date_to: str = None,
        alpha: float = 0.5,
        language: str = "portuguese",
        rrf_k: int = 60,
        exact: bool = False,
        quorum_threshold: float = 0.7,
        candidate_cap: int = 20000,
        result_unit: str = "chunks",
        retrieval_stage: str = "hybrid",
        include_diagnostics: bool = False,
    ) -> list[dict[str, G1Chunks | G1Articles]]:
        if language not in ALLOWED_TSQUERY_LANGUAGES:
            raise ValueError(f"language must be one of {sorted(ALLOWED_TSQUERY_LANGUAGES)}, got {language!r}")
        if not 0 <= quorum_threshold <= 1:
            raise ValueError(f"quorum_threshold must be in the interval [0, 1], got {quorum_threshold}")
        if candidate_cap < 1:
            raise ValueError(f"candidate_cap must be >= 1, got {candidate_cap}")
        if result_unit not in ("chunks", "articles"):
            raise ValueError("result_unit must be 'chunks' or 'articles'")
        if retrieval_stage not in ("lexical", "hybrid"):
            raise ValueError("retrieval_stage must be 'lexical' or 'hybrid'")
        if (top_k is not None and top_k < 1) or offset < 0:
            raise ValueError("top_k must be positive and offset non-negative")
        with Session(self.engine) as session:
            # All three diagnostic/baseline queries must see the same corpus.
            session.connection(execution_options={
                "isolation_level": "REPEATABLE READ", "postgresql_readonly": True,
            })
            if exact:
                session.execute(func.set_config("enable_indexscan", "off", True))
                session.execute(func.set_config("enable_bitmapscan", "off", True))
                session.execute(func.set_config("enable_seqscan", "on", True))
            else:
                ef_search = _hnsw_ef_search(top_k, limit)
                session.execute(func.set_config("hnsw.ef_search", str(ef_search), True))

            # lexeme extraction: stopwords stripped and the true lexeme set of
            # the query (one tiny roundtrip; drives the k-subset construction)
            lexemes = session.execute(
                text("SELECT tsvector_to_array(to_tsvector(:language, :query_text))"),
                {"language": language, "query_text": query_text},
            ).scalar() or []
            lexemes = [lexeme for lexeme in lexemes if lexeme]
            if not lexemes:
                # stopword-only query: nothing can match the text half
                print("Query has no valid lexemes after stopword removal; skipping BM25 candidates.")
                return {"rows": [], "diagnostics": {
                    "query_lexemes": [], "effective_quorum": 0,
                    "lexical_candidate_chunks": 0, "lexical_candidate_articles": 0,
                    "embedded_candidate_chunks": 0, "hybrid_eligible_articles": 0,
                    "lexical_candidate_article_urls": [], "lexical_returned_chunks": 0,
                    "hybrid_eligible_article_urls": [],
                    "candidate_cap": candidate_cap, "candidate_cap_hit": False,
                    "candidate_counts_are_capped": True,
                }, "lexical_ranked": []} if include_diagnostics else []

            subset_query, exact_quorum = _subset_tsquery(lexemes, quorum_threshold)
            template = CANDIDATES_FAST_TEMPLATE if exact_quorum else CANDIDATES_FALLBACK_TEMPLATE
            k = max(1, math.ceil(len(lexemes) * quorum_threshold))
            print(f"BM25 quorum: {len(lexemes)} lexemes, k>={k} "
                  f"({'index-resolved' if exact_quorum else 'pair filter + per-row quorum'})")

            binds = [
                bindparam("subset_query", subset_query),
                # Build operators outside the quoted lexemes. Replacing '&'
                # in serialized tsquery text could also corrupt a literal term.
                bindparam("or_query", " | ".join(_quote_lexeme(lexeme) for lexeme in lexemes)),
                bindparam("candidate_cap", candidate_cap),
                bindparam("date_from", date_from),
                bindparam("date_to", date_to),
            ]
            if not exact_quorum:
                binds.append(bindparam("query_text", query_text))
                binds.append(bindparam("quorum_threshold", quorum_threshold))
            candidates_sql = text(template.format(language=language)).bindparams(*binds)
            candidates_cte = candidates_sql.columns(
                id=BigInteger,
                doc_tsv=TSVECTOR,
                bm25=Float,
            ).cte("quorum_candidates")

            # Diagnostics describe the capped lexical pool, not the whole corpus.
            pool = []
            if include_diagnostics:
                pool = session.execute(select(
                    G1Chunks.article,
                    func.count().label("chunks"),
                    func.count().filter(G1Chunks.embedding.is_not(None)).label("embedded"),
                ).join(candidates_cte, G1Chunks.id == candidates_cte.c.id)
                    .group_by(G1Chunks.article).order_by(G1Chunks.article)).mappings().all()

            def fetch(stage):
                if stage == "lexical":
                    score = candidates_cte.c.bm25
                    vector_rank = literal(None)
                    text_rank_position = func.rank().over(order_by=score.desc())
                else:
                    distance = G1Chunks.embedding.cosine_distance(query_embedding)
                    vector_rank = func.rank().over(order_by=distance)
                    text_rank_position = func.rank().over(order_by=candidates_cte.c.bm25.desc())
                    score = (literal(1.0) / (rrf_k + vector_rank)) + (literal(1.0) / (rrf_k + text_rank_position))
                base = select(
                    G1Chunks.id.label("chunk_id"), G1Chunks.article,
                    score.label("score"), vector_rank.label("vector_rank"),
                    text_rank_position.label("text_rank"),
                ).join(candidates_cte, G1Chunks.id == candidates_cte.c.id)
                if stage != "lexical":
                    base = base.where(G1Chunks.embedding.is_not(None))
                scored = base.cte("scored_chunks")
                chosen = _ranked_chunk_window(scored, top_k, offset, result_unit)
                article_ranks = select(
                    scored.c.article,
                    func.min(scored.c.vector_rank).label("article_vector_rank"),
                    func.min(scored.c.text_rank).label("article_text_rank"),
                ).group_by(scored.c.article).cte("article_ranks")
                stmt = select(
                    G1Chunks, G1Articles, chosen.c.score.label("rrf_score"),
                    article_ranks.c.article_vector_rank, article_ranks.c.article_text_rank,
                ).join(chosen, G1Chunks.id == chosen.c.chunk_id)
                stmt = stmt.join(article_ranks, chosen.c.article == article_ranks.c.article).join(G1Chunks.g1_articles)
                return session.execute(stmt.order_by(
                    chosen.c.score.desc(), G1Articles.url, G1Chunks.id,
                )).mappings().all()

            results = fetch(retrieval_stage)
            if not include_diagnostics:
                return results
            lexical_rows = results if retrieval_stage == "lexical" else fetch("lexical")
            lexical_ranked = []
            seen = set()
            for row in lexical_rows:
                url = row["G1Articles"].url
                if url not in seen:
                    seen.add(url)
                    lexical_ranked.append({"article": url, "score": float(row["rrf_score"])})
            chunk_count = sum(row["chunks"] for row in pool)
            return {
                "rows": results,
                "lexical_ranked": lexical_ranked,
                "diagnostics": {
                    "query_lexemes": lexemes, "effective_quorum": k,
                    "lexical_candidate_chunks": chunk_count,
                    "lexical_candidate_articles": len(pool),
                    "embedded_candidate_chunks": sum(row["embedded"] for row in pool),
                    "hybrid_eligible_articles": sum(row["embedded"] > 0 for row in pool),
                    "lexical_candidate_article_urls": [row["article"] for row in pool],
                    "hybrid_eligible_article_urls": [row["article"] for row in pool if row["embedded"] > 0],
                    "candidate_cap": candidate_cap, "candidate_cap_hit": chunk_count >= candidate_cap,
                    "candidate_counts_are_capped": True,
                    "lexical_returned_chunks": len(lexical_rows),
                },
            }

    def get_chunks_by_article(self, article: str):
        with Session(self.engine) as session:
            stmt = select(G1Chunks).where(G1Chunks.article == article)
            results = session.execute(stmt).fetchall()
            return results

    def get_all_with_no_embeddings(self, limit: int = 100, offset: int = 0):
        with Session(self.engine) as session:
            stmt = select(G1Chunks.id, G1Chunks.chunk).where(G1Chunks.embedding.is_(None)).limit(limit).offset(offset)
            results = session.execute(stmt).fetchall()
            return results

    def update_embedding(self, chunk_id: int, embedding: np.ndarray):
        with Session(self.engine) as session:
            stmt = update(G1Chunks).where(G1Chunks.id == chunk_id).values(embedding=embedding)
            session.execute(stmt)
            session.commit()

    def batch_update_embeddings(self, chunk_ids: list[int], embeddings: list[np.ndarray]):
        if len(chunk_ids) != len(embeddings):
            raise ValueError("chunk_ids and embeddings must have the same length")
        if not chunk_ids:
            return
        mappings = [
            {"id": chunk_id, "embedding": embedding}
            for chunk_id, embedding in zip(chunk_ids, embeddings)
        ]
        with Session(self.engine) as session:
            # SQLAlchemy's ORM bulk UPDATE-by-primary-key uses executemany,
            # replacing one client/server round trip per chunk with one batch.
            session.execute(update(G1Chunks), mappings)
            session.commit()
