import spacy
import spacy_dbpedia_spotlight  # noqa: F401 — registers the 'dbpedia_spotlight' pipeline factory
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import SPOTLIGHT_ENDPOINT
from models.models import ArticleEntities, G1Articles, G1Entities
from repositories.entities import EntityRepository
from services.linking import SPOTLIGHT_CONFIDENCE, best_overlap


class NERService:
    """Hybrid pipeline: spaCy NER (pt_core_news_sm) extracts and types entities;
    the dbpedia_spotlight pipe links mentions to DBpedia URIs (canonical identity).
    Linking degrades gracefully when the Spotlight service is unavailable."""

    def __init__(self, entity_repository: EntityRepository, spotlight_endpoint: str | None = None):
        self.nlp = spacy.load("pt_core_news_sm")
        self.entity_repository = entity_repository
        self.linker_available = False
        try:
            self.nlp.add_pipe("dbpedia_spotlight", config={
                "dbpedia_rest_endpoint": spotlight_endpoint or SPOTLIGHT_ENDPOINT,
                "language_code": "pt",
                "confidence": SPOTLIGHT_CONFIDENCE,
                # spaCy entities stay in doc.ents; spotlight spans go to
                # doc.spans['dbpedia_spotlight'] — no overlap conflicts
                "overwrite_ents": False,
                # unreachable endpoint -> unlinked doc instead of raising
                "raise_http_errors": False,
            })
            self.linker_available = True
        except Exception as e:
            print(f"DBpedia Spotlight pipe unavailable, entity linking disabled: {e}")

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        doc = self.nlp(text)
        linked_spans = [
            (span.start_char, span.end_char, span.kb_id_)
            for span in doc.spans.get("dbpedia_spotlight", [])
            if span.kb_id_
        ]
        entities = []
        for ent in doc.ents:
            if ent.label_ == "DBPEDIA_ENT":
                continue
            canonical = best_overlap(ent.start_char, ent.end_char, linked_spans)
            entities.append({
                "text": ent.text,
                "label": ent.label_,
                "canonical": canonical,
            })
        return entities

    def batch_extract_entities(self, articles: list[G1Articles]) -> dict[str, list[dict[str, str]]]:
        entities = {}
        for article in articles:
            entities[article.url] = self.extract_entities(article.text_content)
        return entities

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
            # find articles with no entities
            stmt = (
                select(G1Articles)
                .outerjoin(ArticleEntities, ArticleEntities.g1_article_url == G1Articles.url)
                .where(ArticleEntities.g1_article_url.is_(None))
                .where(G1Articles.url.in_(articles))
            )
            articles_with_no_entities = session.scalars(stmt).all()
            print("Articles with no entities:", len(articles_with_no_entities), [article.url for article in articles_with_no_entities])

            # create the entities
            for article in articles_with_no_entities:
                print("Extracting entities for article:", article.url)
                entities = self.extract_entities(article.text_content)
                self.entity_repository.batch_add_entities(
                    articles=[article.url] * len(entities),
                    texts=[entity["text"] for entity in entities],
                    types=[entity["label"] for entity in entities],
                    canonicals=[entity.get("canonical") for entity in entities],
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
