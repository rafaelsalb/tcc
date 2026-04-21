from ollama import Client


class Selection:
    def __init__(self, query: str, article_titles: list[str]):
        self.client = Client("http://paradiddle-earth:11434")
        self.query = query
        self.article_titles = article_titles

    def select(self) -> str:
        article_list = "\n".join(f"- {title}" for title in self.article_titles)
        prompt = f"{self.query}\n\nConsidere as seguintes manchetes de notícias sobre o assunto {self.query}:\n\n{article_list}\n\nSelecione as notícias mais relevantes para o assunto."
        response = self.client.generate("deepseek-r1:8b", prompt)
        return response.response
