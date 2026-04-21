from dataclasses import dataclass


@dataclass
class CandidateArticle:
    title: str
    url: str
    content: str
    summary: str
    entities: list[str]
