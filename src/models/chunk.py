import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    article: Mapped["Article"] = relationship(back_populates="chunks")  # type: ignore # relationship to article
    content: Mapped[str] = mapped_column()
    vector: Mapped[np.ndarray] = mapped_column(Vector(768))

    __table_args__ = (
        # Add an index on the vector column for efficient similarity search
        Index("ix_chunks_vector", "vector", postgresql_using="ivfflat"),
    )
