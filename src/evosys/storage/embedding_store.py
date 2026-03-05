"""Embedding memory store — chunk, embed, store, and search.

Hybrid retrieval: cosine similarity over pre-fetched vectors combined
with SQLite FTS-style text matching for keyword recall.  Good enough
for personal-scale usage (<100K chunks) without requiring a vector DB.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evosys.llm.embeddings import EmbeddingProvider
from evosys.schemas._types import new_ulid
from evosys.storage.embedding_models import EmbeddingChunkRow

log = structlog.get_logger()

# --- Chunking ---

_DEFAULT_CHUNK_SIZE = 512  # tokens (approximate via chars / 4)
_DEFAULT_CHUNK_OVERLAP = 64


def _chunk_text(
    text_: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split *text_* into overlapping chunks by approximate token count.

    Uses char_count / 4 as a rough token estimate to avoid importing
    a tokenizer.  Good enough for chunking purposes.
    """
    if not text_.strip():
        return []

    char_size = chunk_size * 4
    char_overlap = overlap * 4
    chunks: list[str] = []
    start = 0

    while start < len(text_):
        end = start + char_size
        chunk = text_[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text_):
            break
        start = end - char_overlap

    return chunks


# --- Vector math ---


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --- Result DTO ---


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single search hit with score and metadata."""

    chunk_id: str
    source_key: str
    text: str
    score: float
    namespace: str


# --- Store ---


class EmbeddingMemoryStore:
    """Chunk, embed, store, and search text using vector similarity.

    All vectors are stored as JSON in SQLite.  Search combines:
    1. **Semantic**: Embed query → cosine similarity against all chunks
    2. **Keyword**: SQL LIKE matching for exact term recall
    Results are merged and deduplicated by chunk_id, taking the max score.

    Parameters
    ----------
    session_factory:
        SQLAlchemy async session factory.
    embedding_provider:
        Provider that turns text into vectors.
    chunk_size:
        Approximate token count per chunk.
    chunk_overlap:
        Overlap tokens between adjacent chunks.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_provider: EmbeddingProvider,
        *,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._sf = session_factory
        self._embedder = embedding_provider
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def store(
        self,
        key: str,
        text_: str,
        *,
        namespace: str = "default",
    ) -> int:
        """Chunk, embed, and store *text_* under *key*.

        Returns the number of chunks stored.  If *key* already exists
        in *namespace*, the old chunks are replaced.
        """
        chunks = _chunk_text(text_, self._chunk_size, self._chunk_overlap)
        if not chunks:
            return 0

        vectors = await self._embedder.embed(chunks)
        now = datetime.now(UTC)

        async with self._sf() as session:
            # Delete old chunks for this key
            await session.execute(
                delete(EmbeddingChunkRow).where(
                    EmbeddingChunkRow.source_key == key,
                    EmbeddingChunkRow.namespace == namespace,
                )
            )

            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                row = EmbeddingChunkRow(
                    chunk_id=str(new_ulid()),
                    source_key=key,
                    namespace=namespace,
                    chunk_index=i,
                    text=chunk,
                    vector_json=json.dumps(vector),
                    token_count=len(chunk) // 4,
                    created_at=now,
                )
                session.add(row)

            await session.commit()

        log.debug(
            "embedding_store.stored",
            key=key,
            chunks=len(chunks),
            namespace=namespace,
        )
        return len(chunks)

    async def search(
        self,
        query: str,
        *,
        namespace: str = "default",
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Hybrid search: semantic similarity + keyword matching.

        Returns up to *top_k* results sorted by descending score.
        """
        # Embed the query
        query_vectors = await self._embedder.embed([query])
        if not query_vectors or not query_vectors[0]:
            return await self._keyword_search(query, namespace=namespace, top_k=top_k)

        query_vec = query_vectors[0]

        # Fetch all chunks in namespace (fine for <100K rows)
        async with self._sf() as session:
            stmt = select(EmbeddingChunkRow).where(
                EmbeddingChunkRow.namespace == namespace
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())

        if not rows:
            return []

        # Score each chunk by cosine similarity
        scored: dict[str, SearchResult] = {}
        for row in rows:
            try:
                vec = json.loads(row.vector_json)
            except (json.JSONDecodeError, TypeError):
                continue
            sim = _cosine_similarity(query_vec, vec)
            scored[row.chunk_id] = SearchResult(
                chunk_id=row.chunk_id,
                source_key=row.source_key,
                text=row.text,
                score=sim,
                namespace=row.namespace,
            )

        # Keyword boost: if query words appear in text, bump score
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]
        for row in rows:
            text_lower = row.text.lower()
            keyword_hits = sum(1 for w in query_words if w in text_lower)
            if keyword_hits > 0 and row.chunk_id in scored:
                old = scored[row.chunk_id]
                boost = min(0.2, keyword_hits * 0.05)
                scored[row.chunk_id] = SearchResult(
                    chunk_id=old.chunk_id,
                    source_key=old.source_key,
                    text=old.text,
                    score=min(1.0, old.score + boost),
                    namespace=old.namespace,
                )

        results = sorted(scored.values(), key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def _keyword_search(
        self,
        query: str,
        *,
        namespace: str = "default",
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Fallback keyword-only search when embedding fails."""
        query_words = [w for w in query.lower().split() if len(w) > 2]
        if not query_words:
            return []

        async with self._sf() as session:
            stmt = select(EmbeddingChunkRow).where(
                EmbeddingChunkRow.namespace == namespace
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())

        hits: list[SearchResult] = []
        for row in rows:
            text_lower = row.text.lower()
            keyword_hits = sum(1 for w in query_words if w in text_lower)
            if keyword_hits > 0:
                score = keyword_hits / max(len(query_words), 1)
                hits.append(SearchResult(
                    chunk_id=row.chunk_id,
                    source_key=row.source_key,
                    text=row.text,
                    score=score,
                    namespace=row.namespace,
                ))

        hits.sort(key=lambda r: r.score, reverse=True)
        return hits[:top_k]

    async def delete(self, key: str, *, namespace: str = "default") -> int:
        """Delete all chunks for *key* in *namespace*. Returns count deleted."""
        async with self._sf() as session:
            stmt = delete(EmbeddingChunkRow).where(
                EmbeddingChunkRow.source_key == key,
                EmbeddingChunkRow.namespace == namespace,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount  # type: ignore[return-value]

    async def list_keys(self, *, namespace: str = "default") -> list[str]:
        """Return distinct source keys in *namespace*."""
        async with self._sf() as session:
            stmt = (
                select(EmbeddingChunkRow.source_key)
                .where(EmbeddingChunkRow.namespace == namespace)
                .distinct()
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
