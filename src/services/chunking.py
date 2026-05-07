from chonkie import TokenChunker

from models.models import G1Articles


class ChunkingService:
    def __init__(self, chunk_size: int = 1024, overlap: int = 256):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunker = TokenChunker(chunk_size=self.chunk_size, chunk_overlap=self.overlap)

    def chunk_article(self, article: G1Articles) -> list[str]:
        text = article.text_content
        chunks = self.chunker.chunk(text)

        excerpt = f"Trecho: {article.excerpt}\n" if article.excerpt else ""
        categories = (
            f"Categorias: {', '.join(article.categories)}\n"
            if article.categories
            else ""
        )

        header = (
            f"Título: {article.title}\n"
            f"Publicado: {article.date_published}\n"
            f"{excerpt}"
            f"{categories}\n"
        )

        for i, chunk in enumerate(chunks):
            chunks[i].text = f"{header}{chunk.text}"

        return chunks
