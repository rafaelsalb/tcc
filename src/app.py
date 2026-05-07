from time import sleep

from db import engine
from repositories.article import ArticleRepository
from repositories.chunk import ChunkRepository
from services.chunking import ChunkingService
from services.search import SearchService
from services.vectorizer import VectorizerService
from ollama import Client


class App:
    def __init__(self):
        self.article_repo = ArticleRepository(engine)
        self.chunk_repo = ChunkRepository(engine)
        self.chunking_service = ChunkingService()
        self.client = Client(host="http://paradiddle-earth:11434")
        self.vectorizer = VectorizerService(self.client, model="qwen3-embedding:0.6b", dimensions=768)
        self.search_service = SearchService(self.article_repo, self.chunk_repo, self.vectorizer)

    def populate_chunks(self):
        while True:
            print("Checking for articles without chunks...")
            articles = self.article_repo.get_all_with_no_chunks()
            if not articles:
                print("No more articles to process.")
                break
            print(f"Found {len(articles)} articles to process.")
            for i, article in enumerate(articles):
                print(f"Processing article {i+1}/{len(articles)}: {article.title}")
                print("Chunking article...")
                chunks = self.chunking_service.chunk_article(article)
                chunk_texts = [chunk.text for chunk in chunks]
                # print("Vectorizing chunks...")
                # embeddings = self.vectorizer.embed(chunk_texts)
                print("Saving chunks to database...")
                self.chunk_repo.batch_add_chunk([article.url] * len(chunks), chunk_texts, [None] * len(chunks))
                sleep(0.01)
            print("Finished processing batch of articles.")

    def populate_embeddings(self):
        while True:
            print("Checking for chunks without embeddings...")
            chunks = self.chunk_repo.get_all_with_no_embeddings()
            if not chunks:
                print("No more chunks to process.")
                break
            print(f"Found {len(chunks)} chunks to process.")
            ids = [chunk[0] for chunk in chunks]
            chunk_texts = [chunk[1] for chunk in chunks]
            print("Vectorizing chunks...")
            embeddings = self.vectorizer.embed(chunk_texts)
            print("Saving embeddings to database...")
            self.chunk_repo.batch_update_embeddings(ids, embeddings)
            sleep(0.1)
            print("Finished processing batch of chunks.")
