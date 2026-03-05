"""SQLAlchemy model for embedding storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from evosys.storage.models import Base


class EmbeddingChunkRow(Base):
    """A text chunk with its embedding vector stored as JSON.

    Vectors are stored as JSON arrays in SQLite (no pgvector dep).
    Cosine similarity is computed in Python after fetching candidates
    via FTS pre-filtering.
    """

    __tablename__ = "embedding_chunks"

    chunk_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(512), index=True)
    namespace: Mapped[str] = mapped_column(String(256), default="default", index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    # JSON-serialised float array — compact enough for <100K chunks
    vector_json: Mapped[str] = mapped_column(Text, default="[]")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_embedding_ns_source", "namespace", "source_key"),
    )
