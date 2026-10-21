import threading
from concurrent.futures import ThreadPoolExecutor

import requests
import spacy
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import SPOTLIGHT_ENDPOINT
from models.models import ArticleEntities, G1Articles, G1Entities
from repositories.entities import EntityRepository
from services.linking import SPOTLIGHT_CONFIDENCE, best_overlap


class NERService:
    """Hybrid pipeline: spaCy NER (pt_core_news_sm) extracts and types entities;
    the DBpedia Spotlight REST service (`/rest/annotate`) provides each
    mention's canonical identity.

    NER is CPU-bound, so spaCy always runs on the calling thread (nlp.pipe
    batches it). Linking is I/O-bound — `requests` releases the GIL during the
    socket wait — so batches annotate documents on a thread pool that overlaps
    the spaCy pass. This replicates the old `dbpedia_spotlight` pipe component
    (same request params, same @offset/@surfaceForm/@URI parsing, same
    best-overlap merge) while parallelizing it and degrading gracefully when
    the service is down (mentions stay unlinked)."""

    def __init__(self, entity_repository: EntityRepository, spotlight_endpoint: str | None = None,
                 link_workers: int = 8, link_timeout: float = 30.0):
        self.nlp = spacy.load("pt_core_news_sm")
        self.entity_repository = entity_repository
        self.spotlight_endpoint = (spotlight_endpoint or SPOTLIGHT_ENDPOINT).rstrip("/")
        self.link_workers = link_workers
        self.link_timeout = link_timeout
        # Informational: flips False while the endpoint is failing; failures
        # print once per outage window instead of once per document.
        self.linker_available = True
        self._failures_since_success = 0
        self._thread_state = threading.local()

    def _session(self) -> requests.Session:
        """One pooled connection per worker thread (Session objects are not
        thread-safe for cross-thread sharing)."""
        session = getattr(self._thread_state, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"accept": "application/json"})
            self._thread_state.session = session
        return session

    def _annotate(self, text: str) -> list[tuple[int, int, str]]:
        """POST one document to Spotlight and return (start, end, uri) char
        triples — the same triples the pipe component fed through kb_id."""
        try:
            response = self._session().post(
                f"{self.spotlight_endpoint}/annotate",
                data={"text": text, "confidence": SPOTLIGHT_CONFIDENCE},
                timeout=self.link_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            self.linker_available = False
            if self._failures_since_success == 0:
                print(f"DBpedia Spotlight unavailable, mentions stay unlinked ({type(exc).__name__}); retrying silently.")
            self._failures_since_success += 1
            return []
        self.linker_available = True
        self._failures_since_success = 0
        resources = response.json().get("Resources", [])
        return [
            (int(resource["@offset"]), int(resource["@offset"]) + len(resource["@surfaceForm"]), resource["@URI"])
            for resource in resources
        ]

    def _compose(self, ents: list[tuple[int, int, str, str]], annotations: list[tuple[int, int, str]]) -> list[dict[str, str]]:
        return [
            {"text": text, "label": label, "canonical": best_overlap(start, end, annotations)}
            for start, end, label, text in ents
        ]

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        return self._compose(
            [(ent.start_char, ent.end_char, ent.label_, ent.text) for ent in self.nlp(text).ents],
            self._annotate(text),
        )

    def batch_extract_entities(self, articles: list[G1Articles]) -> dict[str, list[dict[str, str]]]:
        if not articles:
            return {}
        texts = [article.text_content for article in articles]
        with ThreadPoolExecutor(max_workers=self.link_workers, thread_name_prefix="spotlight-link") as pool:
            # map() submits every request right away, so the modeled HTTP
            # waits (GIL-free) already run while the spaCy pass below runs on
            # this thread.
            annotations = pool.map(self._annotate, texts)
            results = {}
            for article, doc, annotation in zip(articles, self.nlp.pipe(texts, batch_size=16), annotations):
                ents = [(ent.start_char, ent.end_char, ent.label_, ent.text) for ent in doc.ents]
                results[article.url] = self._compose(ents, annotation)
        return results

    def batch_extract_entities_and_store(self, articles: list[G1Articles]):
        article_entities = self.batch_extract_entities(articles)
        articles_batch: list[str] = []
        texts_batch: list[str] = []
        types_batch: list[str] = []
        canonicals_batch: list[str | None] = []
        for article_url, entities in article_entities.items():
            for entity in entities:
                articles_batch.append(article_url)
                texts_batch.append(entity["text"])
                types_batch.append(entity["label"])
                canonicals_batch.append(entity.get("canonical"))
        if articles_batch:
            self.entity_repository.batch_add_entities(
                articles=articles_batch,
                texts=texts_batch,
                types=types_batch,
                canonicals=canonicals_batch,
            )

    def get_entities_for_article(self, article_url: str) -> list[dict[str, str]]:
        with Session(self.entity_repository.engine) as session:
            stmt = (
                select(G1Entities)
                .join(ArticleEntities, ArticleEntities.g1_entities_id == G1Entities.id)
                .where(ArticleEntities.g1_article_url == article_url)
            )
            results = session.scalars(stmt).all()
            return results

    def batch_get_or_extract_entities_and_store_for_articles(self, articles: list[str], of_types: list[str] = None) -> dict[str, list[G1Entities]]:
        with Session(self.entity_repository.engine) as session:
            # find articles with no entities; text_content is feedstock for the
            # NER pipeline (nlp(None) raises), so exclude NULL bodies up front
            stmt = (
                select(G1Articles)
                .outerjoin(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
                .where(ArticleEntities.g1_article_url.is_(None))
                .where(G1Articles.url.in_(articles))
                .where(G1Articles.text_content.is_not(None))
            )
            articles_with_no_entities = session.scalars(stmt).all()
            if articles_with_no_entities:
                print(f"Extracting entities for {len(articles_with_no_entities)} article(s).")
                # parallel extract, one batched write for the whole request
                extracted = self.batch_extract_entities(articles_with_no_entities)
                batch_articles, batch_texts, batch_types, batch_canonicals = [], [], [], []
                for article_url, entities in extracted.items():
                    batch_articles.extend([article_url] * len(entities))
                    batch_texts.extend(entity["text"] for entity in entities)
                    batch_types.extend(entity["label"] for entity in entities)
                    batch_canonicals.extend(entity.get("canonical") for entity in entities)
                self.entity_repository.batch_add_entities(
                    articles=batch_articles,
                    texts=batch_texts,
                    types=batch_types,
                    canonicals=batch_canonicals,
                )

            print("Retrieving entities for all articles...")
            # retrieve all entities for the articles
            stmt = (
                select(G1Entities, ArticleEntities.g1_article_url)
                .join(ArticleEntities, ArticleEntities.g1_entities_id == G1Entities.id)
                .where(ArticleEntities.g1_article_url.in_(articles))
                .where(G1Entities.is_junk.is_(False))
                .where(G1Entities.text_.not_in(["g1", "G1", "Foto", "foto", "Vídeo", "vídeo"]))  # filter out common non-informative entities
            )
            if of_types:
                stmt = stmt.where(G1Entities.type.in_(of_types))
            results = session.execute(stmt).fetchall()
            entities_by_article = {}
            for entity, article_url in results:
                if article_url not in entities_by_article:
                    entities_by_article[article_url] = []
                entities_by_article[article_url].append(entity)
            return entities_by_article
