from sqlalchemy import select
from sqlalchemy.orm import Session

from models.models import ArticleEntities, G1Articles, G1Entities
from repositories.entities import EntityRepository
import spacy


class NERService:
    def __init__(self, entity_repository: EntityRepository):
        self.nlp = spacy.load("pt_core_news_sm")
        self.entity_repository = entity_repository

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entities.append({
                "text": ent.text,
                "label": ent.label_
            })
        return entities

    def batch_extract_entities(self, articles: list[str]) -> dict[str, list[dict[str, str]]]:
        entities = {}
        for article in articles:
            entities[article] = self.extract_entities(article.text_content)
        return entities

    def batch_extract_entities_and_store(self, articles: list[G1Articles]):
        assert all(isinstance(article, G1Articles) for article in articles), "All items in articles must be instances of G1Articles"
        article_entities = self.batch_extract_entities(articles)
        articles_batch: list[str] = []
        texts_batch: list[str] = []
        types_batch: list[str] = []
        for article, entities in article_entities.items():
            for entity in entities:
                articles_batch.append(article.url)
                texts_batch.append(entity["text"])
                types_batch.append(entity["label"])
        if articles_batch:
            self.entity_repository.batch_add_entities(
                articles=articles_batch,
                texts=texts_batch,
                types=types_batch,
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
                )

            print("Retrieving entities for all articles...")
            # retrieve all entities for the articles
            stmt = (
                select(G1Entities, ArticleEntities.g1_article_url)
                .join(ArticleEntities, ArticleEntities.g1_entities_id == G1Entities.id)
                .where(ArticleEntities.g1_article_url.in_(articles))
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
