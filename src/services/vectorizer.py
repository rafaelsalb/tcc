from ollama import Client


class VectorizerService:
    def __init__(self, client: Client, model: str = "qwen3-embedding:0.6b", dimensions: int = 768):
        self.client = client
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self.client.embed(self.model, texts, dimensions=self.dimensions)
        return result.embeddings
