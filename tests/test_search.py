from app import App

from models.models import G1Articles
from schemas.search_result import SearchResultSchema


def test_load_schema():
    g1_app = App()
    results = g1_app.search_service.search("homem", top_k=5, limit=5)
    print("Search results:", results['articles'])
    schema = SearchResultSchema(many=True)
    loaded = schema.load(results['articles'])
    assert len(loaded) == 5
