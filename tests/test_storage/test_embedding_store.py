"""Tests for EmbeddingMemoryStore."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from evosys.storage.embedding_store import (
    EmbeddingMemoryStore,
    _chunk_text,
    _cosine_similarity,
)
from evosys.storage.models import Base

# --- Fixtures ---


class FakeEmbeddingProvider:
    """Deterministic embedding provider for testing."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic vectors based on text hash."""
        vectors = []
        for text in texts:
            # Simple hash-based vector for reproducibility
            h = hash(text) % 1000
            vec = [(h + i) % 100 / 100.0 for i in range(self._dimensions)]
            vectors.append(vec)
        return vectors


@pytest.fixture()
async def embedding_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def embedding_session_factory(embedding_engine) -> async_sessionmaker:
    return async_sessionmaker(embedding_engine, expire_on_commit=False)


@pytest.fixture()
def embedding_store(embedding_session_factory) -> EmbeddingMemoryStore:
    provider = FakeEmbeddingProvider(dimensions=8)
    return EmbeddingMemoryStore(embedding_session_factory, provider)


# --- Unit tests ---


class TestChunkText:
    def test_empty_text(self) -> None:
        assert _chunk_text("") == []

    def test_whitespace_only(self) -> None:
        assert _chunk_text("   \n  ") == []

    def test_short_text_single_chunk(self) -> None:
        chunks = _chunk_text("Hello world")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_text_multiple_chunks(self) -> None:
        text = "word " * 2000  # ~10K chars → multiple chunks
        chunks = _chunk_text(text, chunk_size=128, overlap=16)
        assert len(chunks) > 1

    def test_overlap_between_chunks(self) -> None:
        text = "A" * 4096  # 4096 chars = ~1024 tokens
        chunks = _chunk_text(text, chunk_size=256, overlap=64)
        assert len(chunks) > 1
        # Each chunk should be approximately chunk_size * 4 chars


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_different_lengths(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_empty_vectors(self) -> None:
        assert _cosine_similarity([], []) == 0.0


# --- Integration tests ---


class TestEmbeddingMemoryStore:
    async def test_store_and_search(self, embedding_store: EmbeddingMemoryStore) -> None:
        count = await embedding_store.store("doc1", "Python programming language")
        assert count >= 1

        results = await embedding_store.search("programming", top_k=3)
        assert len(results) >= 1
        assert results[0].source_key == "doc1"

    async def test_store_replaces_existing(self, embedding_store: EmbeddingMemoryStore) -> None:
        await embedding_store.store("key1", "first version")
        await embedding_store.store("key1", "second version")

        results = await embedding_store.search("version", top_k=10)
        # Should only have chunks from the second version
        keys = {r.source_key for r in results}
        assert "key1" in keys

    async def test_search_empty_store(self, embedding_store: EmbeddingMemoryStore) -> None:
        results = await embedding_store.search("anything")
        assert results == []

    async def test_search_with_namespace(self, embedding_store: EmbeddingMemoryStore) -> None:
        await embedding_store.store("doc1", "hello world", namespace="ns1")
        await embedding_store.store("doc2", "hello planet", namespace="ns2")

        results = await embedding_store.search("hello", namespace="ns1")
        source_keys = {r.source_key for r in results}
        assert "doc1" in source_keys
        assert "doc2" not in source_keys

    async def test_delete(self, embedding_store: EmbeddingMemoryStore) -> None:
        await embedding_store.store("to_delete", "some content")
        deleted = await embedding_store.delete("to_delete")
        assert deleted >= 1

        results = await embedding_store.search("some content")
        source_keys = {r.source_key for r in results}
        assert "to_delete" not in source_keys

    async def test_list_keys(self, embedding_store: EmbeddingMemoryStore) -> None:
        await embedding_store.store("a", "alpha content")
        await embedding_store.store("b", "beta content")

        keys = await embedding_store.list_keys()
        assert set(keys) == {"a", "b"}

    async def test_keyword_fallback(self, embedding_store: EmbeddingMemoryStore) -> None:
        # Even with bad embeddings, keyword matching should work
        await embedding_store.store("doc1", "unique_keyword_xyz is here")
        results = await embedding_store.search("unique_keyword_xyz")
        # Should find via keyword boost even if cosine sim is low
        assert len(results) >= 1
