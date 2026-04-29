from typing import Any

from sqlalchemy import ARRAY, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from models.base import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(unique=True)
    sitemap_url: Mapped[str] = mapped_column()
    sitemap_lastmod: Mapped[str] = mapped_column()
    sitemap_article_lastmod: Mapped[str] = mapped_column()
    sitemap_image_url: Mapped[str] = mapped_column()
    first_seen_at: Mapped[str] = mapped_column()
    last_seen_at: Mapped[str] = mapped_column()
    fetch_status: Mapped[str] = mapped_column()
    fetch_error: Mapped[str] = mapped_column()
    fetch_attempts: Mapped[int] = mapped_column()
    http_status: Mapped[int] = mapped_column()
    fetched_at: Mapped[str] = mapped_column()
    final_url: Mapped[str] = mapped_column()
    extraction_status: Mapped[str] = mapped_column()
    extraction_error: Mapped[str] = mapped_column()
    extracted_at: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    author: Mapped[str] = mapped_column()
    hostname: Mapped[str] = mapped_column()
    sitename: Mapped[str] = mapped_column()
    date_published: Mapped[str] = mapped_column()
    language: Mapped[str] = mapped_column()
    excerpt: Mapped[str] = mapped_column()
    categories: Mapped[list[str]] = mapped_column(ARRAY(String))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String))
    text_content: Mapped[str] = mapped_column()
    raw_sitemap: Mapped[dict[str, Any]] = mapped_column(JSONB)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="article"
    )  # type: ignore # relationship to chunks
