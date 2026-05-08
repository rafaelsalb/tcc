from repositories.entities import EntityRepository
import spacy


class NERService:
    def __init__(self, entity_repository: EntityRepository):
        self.nlp = spacy.load("pt_core_news_sm")
        self.entity_repository = entity_repository

    def extract_entities(self, text: str):
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entities.append({
                "text": ent.text,
                "label": ent.label_
            })
        return entities

    def batch_extract_entities(self, articles: list[str]):
        entities = {}
        for article in articles:
            entities[article] = self.extract_entities(article)
        return entities

    def batch_extract_entities_and_store(self, article_url: str):
        article_entities = self.batch_extract_entities([article_url])
        for article, entities in article_entities.items():
            for entity in entities:
                self.entity_repository.add_entity(article=article, text=entity["text"], type_=entity["label"])
