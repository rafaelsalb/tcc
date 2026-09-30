import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

import requests
from sqlalchemy import desc, func, select, text as sql_text, update
from sqlalchemy.orm import Session

from models.models import ArticleEntities, G1Articles, G1Entities

SPOTLIGHT_CONFIDENCE = 0.5

# Surfaces that are media-credit artifacts or generic objects, not entities
# worth of graph nodes. Normalized (accent/case-insensitive) comparison.
JUNK_SURFACES = {
    "foto", "fotos", "video", "videos", "imagem", "imagens",
    "reproducao", "divulgacao", "arquivo", "arquivos",
    "celular", "celulares", "g1", "print", "prints",
    "audio", "audios", "legenda", "foto g1",
}

JUNK_PATTERNS = [
    re.compile(r"^\W*$"),
    re.compile(r"^\d+$"),
    re.compile(r"(^|\s)(foto|v[íi]deo|imagem|reprodu[çc][ãa]o|divulga[çc][ãa]o|arquivo)\s*[:\-–]", re.IGNORECASE),
    re.compile(r"(—|–|\s|-)(foto|v[íi]deo|reprodu[çc][ãa]o|divulga[çc][ãa]o|arquivo)$", re.IGNORECASE),
]


def normalize_surface(surface: str) -> str:
    decomposed = unicodedata.normalize("NFD", surface or "")
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.casefold().strip().strip(".,;:!?/\\\"'()[]{}—–-_*#").strip()


def is_junk_surface(surface: str) -> bool:
    normalized = normalize_surface(surface)
    if normalized in JUNK_SURFACES:
        return True
    return any(pattern.search(surface or "") for pattern in JUNK_PATTERNS)


def uri_label(uri: str) -> str:
    """http://pt.dbpedia.org/resource/Donald_Trump -> 'Donald Trump'"""
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    return unquote(tail).replace("_", " ").strip()


def best_overlap(start: int, end: int, spans: list[tuple[int, int, str]]) -> str | None:
    """Pick the URI of the linked span with the largest character overlap."""
    best_uri = None
    best_overlap_len = 0
    for span_start, span_end, uri in spans:
        overlap = min(end, span_end) - max(start, span_start)
        if overlap > best_overlap_len:
            best_uri = uri
            best_overlap_len = overlap
    return best_uri


# A stored surface may carry a leading title ('presidente Lula') or function word
# ('de Lula') around the salient mention. Only these prefixes are accepted when
# the spotter found a shorter form than the stored surface; anything else
# ('José Guimarães' spotted as 'Guimarães' — a different person) is rejected.
SURFACE_PREFIX_WORDS = {
    "presidente", "presidenta", "ministro", "ministra", "senador", "senadora",
    "deputado", "deputada", "governador", "governadora", "prefeito", "prefeita",
    "vereador", "vereadora", "secretario", "secretaria", "juiz", "juiza",
    "desembargador", "desembargadora", "rei", "rainha", "papa", "cardeal",
    "arcebispo", "bispo", "padre", "pastor", "general", "coronel", "capitao",
    "comandante", "embaixador", "embaixadora", "professor", "professora",
    "doutor", "doutora", "dr", "dra", "sr", "sra",
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
    "ao", "aos", "a", "para", "com", "no", "na", "nos", "nas", "em", "por", "e",
}


def accepts_surface(query_surface: str, spotted_surface_form: str) -> bool:
    """A Spotlight link is only accepted when what the spotter actually found
    corresponds to the surface we asked about: an exact (normalized) match, or
    the salient mention plus an allowed title/function-word prefix."""
    query = normalize_surface(query_surface)
    spotted = normalize_surface(spotted_surface_form)
    if not query or not spotted:
        return False
    if spotted == query:
        return True
    if query.endswith(" " + spotted):
        prefix_tokens = query[: -(len(spotted) + 1)].strip().split()
        if prefix_tokens and all(token in SURFACE_PREFIX_WORDS for token in prefix_tokens):
            return True
    return False


def _annotate(text: str, endpoint: str, confidence: float, timeout: float, retries: int) -> list[dict]:
    for attempt in range(retries):
        try:
            response = requests.post(
                f"{endpoint}/annotate",
                data={"text": text, "confidence": confidence},
                headers={"accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json().get("Resources", [])
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    return []


def link_surface(surface: str, endpoint: str, confidence: float = SPOTLIGHT_CONFIDENCE,
                 timeout: float = 10.0, retries: int = 3) -> str | None:
    """Query DBpedia Spotlight with a bare surface form; returns its URI when the
    link is trustworthy (spotted form matches the surface), else None."""
    resources = _annotate(surface, endpoint, confidence, timeout, retries)
    for resource in resources:
        if accepts_surface(surface, resource.get("@surfaceForm", "")):
            return resource["@URI"]
    return None


def link_in_context(text: str, surface: str, endpoint: str, confidence: float = SPOTLIGHT_CONFIDENCE,
                    timeout: float = 20.0, retries: int = 2) -> str | None:
    """Annotate a text that contains the surface and return the URI linked to a
    mention that matches the surface (better disambiguation than bare queries)."""
    for resource in _annotate(text, endpoint, confidence, timeout, retries):
        if accepts_surface(surface, resource.get("@surfaceForm", "")):
            return resource["@URI"]
    return None


class EntityCanonicalizer:
    """Backfills g1_entities.canonical (DBpedia URI) and flags junk rows.

    Three linking passes, most trustworthy first:
    1. bare surface query against Spotlight (surfaceForm-validated);
    2. context retry: annotate one sample article containing the surface
       (only for rows with degree >= 2, which actually affect the graph);
    3. deterministic suffix merge: an unlinked surface whose tokens are the
       suffix of exactly one linked label ('Trump' -> 'Donald Trump') inherits
       that label's URI (highest total degree wins on ambiguity).
    """

    LINK_TYPES = ("PER", "ORG", "LOC")
    BATCH_SIZE = 500
    CONTEXT_MIN_DEGREE = 2
    SUFFIX_MIN_CHARS = 4

    def __init__(self, engine, endpoint: str):
        self.engine = engine
        self.endpoint = endpoint

    # ------------------------------------------------------------------ setup

    def ensure_columns(self):
        with self.engine.begin() as connection:
            connection.execute(sql_text("ALTER TABLE g1_entities ADD COLUMN IF NOT EXISTS canonical TEXT"))
            connection.execute(sql_text(
                "ALTER TABLE g1_entities ADD COLUMN IF NOT EXISTS is_junk BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        print("Ensured g1_entities.canonical / g1_entities.is_junk columns exist.")

    def mark_junk(self) -> int:
        with Session(self.engine) as session:
            rows = session.execute(
                select(G1Entities.id, G1Entities.text_).where(G1Entities.is_junk.is_(False))
            ).fetchall()
        junk_ids = [entity_id for entity_id, text_ in rows if is_junk_surface(text_)]
        for i in range(0, len(junk_ids), self.BATCH_SIZE):
            chunk = junk_ids[i:i + self.BATCH_SIZE]
            with Session(self.engine) as session:
                session.execute(update(G1Entities).where(G1Entities.id.in_(chunk)).values(is_junk=True))
                session.commit()
        print(f"Junk pass: marked {len(junk_ids)} of {len(rows)} entity rows as junk.")
        return len(junk_ids)

    # ----------------------------------------------------------------- passes

    def _pending_rows(self, limit: int | None) -> list[tuple[int, str, int]]:
        degree = (
            select(ArticleEntities.g1_entities_id, func.count().label("deg"))
            .group_by(ArticleEntities.g1_entities_id)
            .subquery()
        )
        stmt = (
            select(G1Entities.id, G1Entities.text_, func.coalesce(degree.c.deg, 0))
            .outerjoin(degree, degree.c.g1_entities_id == G1Entities.id)
            .where(G1Entities.canonical.is_(None))
            .where(G1Entities.is_junk.is_(False))
            .where(G1Entities.type.in_(self.LINK_TYPES))
            .order_by(desc(func.coalesce(degree.c.deg, 0)), G1Entities.id)
        )
        if limit:
            stmt = stmt.limit(limit)
        with Session(self.engine) as session:
            return session.execute(stmt).fetchall()

    def _persist(self, results: dict[int, str]):
        by_uri: dict[str, list[int]] = {}
        for entity_id, uri in results.items():
            by_uri.setdefault(uri, []).append(entity_id)
        updates = list(by_uri.items())
        for i in range(0, len(updates), 200):
            with Session(self.engine) as session:
                for uri, ids in updates[i:i + 200]:
                    session.execute(update(G1Entities).where(G1Entities.id.in_(ids)).values(canonical=uri))
                session.commit()

    def _bare_pass(self, rows, workers: int) -> dict[int, str]:
        results: dict[int, str] = {}
        total = len(rows)
        print(f"Link pass 1 (bare surface): {total} rows...")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(link_surface, text_, self.endpoint): entity_id
                for entity_id, text_, _ in rows
            }
            for processed, future in enumerate(as_completed(futures), 1):
                uri = future.result()
                if uri:
                    results[futures[future]] = uri
                if processed % 5000 == 0:
                    print(f"  {processed}/{total} ({len(results)} linked so far)...")
        print(f"Link pass 1 done: {len(results)} linked.")
        return results

    def _context_pass(self, rows, workers: int) -> dict[int, str]:
        results: dict[int, str] = {}
        total = len(rows)
        print(f"Link pass 2 (context retry, degree >= {self.CONTEXT_MIN_DEGREE}): {total} rows...")
        for chunk_start in range(0, total, 2000):
            chunk = rows[chunk_start:chunk_start + 2000]
            ids = [entity_id for entity_id, _, _ in chunk]
            surface_by_id = {entity_id: text_ for entity_id, text_, _ in chunk}
            with Session(self.engine) as session:
                samples = session.execute(
                    select(ArticleEntities.g1_entities_id, G1Articles.text_content)
                    .join(G1Articles, G1Articles.url == ArticleEntities.g1_article_url)
                    .where(ArticleEntities.g1_entities_id.in_(ids))
                    .where(G1Articles.text_content.is_not(None))
                    .distinct(ArticleEntities.g1_entities_id)
                ).fetchall()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(link_in_context, article_text, surface_by_id[entity_id], self.endpoint): entity_id
                    for entity_id, article_text in samples
                }
                for future in as_completed(futures):
                    uri = future.result()
                    if uri:
                        results[futures[future]] = uri
            done = min(chunk_start + 2000, total)
            print(f"  {done}/{total} ({len(results)} linked so far)...")
        print(f"Link pass 2 done: {len(results)} linked.")
        return results

    def _suffix_pass(self, rows) -> dict[int, str]:
        results: dict[int, str] = {}
        with Session(self.engine) as session:
            degree = (
                select(ArticleEntities.g1_entities_id, func.count().label("deg"))
                .group_by(ArticleEntities.g1_entities_id)
                .subquery()
            )
            linked = session.execute(
                select(G1Entities.canonical, func.coalesce(func.sum(degree.c.deg), 0))
                .outerjoin(degree, degree.c.g1_entities_id == G1Entities.id)
                .where(G1Entities.canonical.is_not(None))
                .group_by(G1Entities.canonical)
            ).fetchall()
        index: dict[str, list[tuple[list[str], str, int]]] = {}
        for canonical, total_degree in linked:
            label_tokens = normalize_surface(uri_label(canonical)).split()
            if len(label_tokens) < 2:
                continue
            index.setdefault(label_tokens[-1], []).append((label_tokens, canonical, total_degree))

        print(f"Link pass 3 (deterministic suffix merge) over {len(rows)} unlinked rows...")
        for entity_id, text_, _ in rows:
            surface_tokens = normalize_surface(text_).split()
            if len(" ".join(surface_tokens)) < self.SUFFIX_MIN_CHARS:
                continue
            candidates = [
                (label_tokens, canonical, total_degree)
                for label_tokens, canonical, total_degree in index.get(surface_tokens[-1], [])
                if len(label_tokens) > len(surface_tokens)
                and label_tokens[-len(surface_tokens):] == surface_tokens
            ]
            if not candidates:
                continue
            _, canonical, _ = max(candidates, key=lambda c: (c[2], len(c[0])))
            results[entity_id] = canonical
        print(f"Link pass 3 done: {len(results)} merged by suffix.")
        for entity_id, text_ in [(r[0], r[1]) for r in rows if r[0] in results][:40]:
            print(f"  suffix merge: {text_!r} -> {uri_label(results[entity_id])}")
        return results

    def link_all(self, limit: int | None = None, workers: int = 8) -> dict[str, int]:
        rows = self._pending_rows(limit)
        print(f"Rows to canonicalize: {len(rows)}")

        bare = self._bare_pass(rows, workers)
        self._persist(bare)

        context_rows = [(r[0], r[1], r[2]) for r in rows if r[0] not in bare and r[2] >= self.CONTEXT_MIN_DEGREE]
        context = self._context_pass(context_rows, workers)
        self._persist(context)

        suffix_rows = [r for r in rows if r[0] not in bare and r[0] not in context]
        suffix = self._suffix_pass(suffix_rows)
        self._persist(suffix)

        return {
            "rows": len(rows),
            "bare_linked": len(bare),
            "context_linked": len(context),
            "suffix_merged": len(suffix),
            "unlinked": len(rows) - len(bare) - len(context) - len(suffix),
        }

    # ---------------------------------------------------------------- report

    def report(self):
        with Session(self.engine) as session:
            total = session.execute(select(func.count()).select_from(G1Entities)).scalar()
            junk = session.execute(
                select(func.count()).select_from(G1Entities).where(G1Entities.is_junk.is_(True))
            ).scalar()
            linked = session.execute(
                select(func.count()).select_from(G1Entities).where(G1Entities.canonical.is_not(None))
            ).scalar()
            groups = session.execute(
                select(G1Entities.canonical, func.count(G1Entities.id))
                .where(G1Entities.canonical.is_not(None))
                .group_by(G1Entities.canonical)
                .order_by(desc(func.count(G1Entities.id)))
                .limit(30)
            ).fetchall()
        print(f"Report: {total} entity rows | {junk} junk | {linked} linked to DBpedia URIs")
        print("Top merged groups (surfaces collapsed into one canonical entity):")
        for canonical, count in groups:
            print(f"  {uri_label(canonical)}  <-  {count} surfaces  ({canonical})")

    def run(self, limit: int | None = None, workers: int = 8):
        self.ensure_columns()
        self.mark_junk()
        stats = self.link_all(limit=limit, workers=workers)
        print(f"Link stats: {stats}")
        self.report()
