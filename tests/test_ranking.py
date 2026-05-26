from pprint import pprint

from sqlalchemy import create_engine

from app import App


g1_app = App()


def test_ranking():
    print("Testing article ranking...")
    # articles = g1_app.article_repo.get_all(limit=5)
    # article_urls = [article.url for article in articles]
    article_urls = [
        "https://g1.globo.com/podcast/o-assunto/noticia/2026/04/08/trump-x-ira-da-ameaca-de-exterminio-ao-cessar-fogo-o-assunto-1695.ghtml",
        "https://g1.globo.com/mundo/noticia/2026/03/10/larijani-ameaca-trum-cuidado-para-nao-ser-eliminado.ghtml",
        "https://g1.globo.com/mundo/noticia/2026/03/05/governo-trump-pede-ajuda-a-ucrania-para-lidar-com-drones-no-oriente-medio.ghtml"
    ]
    print("Testing ranking with articles:", article_urls)
    ranking = g1_app.ranking_service.ppr(article_urls)
    print("Ranking results:")
    pprint(ranking)
    # assert len(ranking) == len(articles)
