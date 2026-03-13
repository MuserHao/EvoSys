"""Tests for SemanticPatternDetector."""

from __future__ import annotations

from evosys.reflection.semantic_detector import (
    SemanticPatternDetector,
    _cosine_similarity,
)
from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEmbedder:
    """Fake embedding provider that returns deterministic vectors."""

    def __init__(self, dim: int = 8):
        self._dim = dim

    @property
    def dimensions(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Hash-based fake embeddings — similar texts get similar vectors."""
        vectors = []
        for text in texts:
            h = hash(text[:20])  # first 20 chars determine "meaning"
            vec = [(h >> i & 1) * 0.5 + 0.25 for i in range(self._dim)]
            # Normalize
            norm = sum(x * x for x in vec) ** 0.5
            vectors.append([x / norm for x in vec])
        return vectors


class _ClusterableEmbedder:
    """Embedder that produces known clusters for testing."""

    @property
    def dimensions(self) -> int:
        return 3

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "weather" in text:
                vectors.append([0.9, 0.1, 0.0])
            elif "price" in text:
                vectors.append([0.0, 0.9, 0.1])
            else:
                vectors.append([0.1, 0.1, 0.9])
        return vectors


def _make_record(
    context: str,
    action: str = "tool:web_fetch",
    success: bool = True,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=new_ulid(),
        iteration_index=0,
        action_name=action,
        context_summary=context,
        success=success,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCosine:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0


class TestSemanticPatternDetector:
    async def test_clusters_similar_records(self):
        embedder = _ClusterableEmbedder()
        detector = SemanticPatternDetector(
            embedder, min_frequency=2, similarity_threshold=0.8
        )
        records = [
            _make_record("weather in Tokyo"),
            _make_record("weather in London"),
            _make_record("weather in Paris"),
            _make_record("price of iPhone"),
            _make_record("price of MacBook"),
        ]
        clusters = await detector.detect(records)
        assert len(clusters) >= 2
        sizes = sorted([len(c.records) for c in clusters], reverse=True)
        assert sizes[0] == 3  # weather cluster
        assert sizes[1] == 2  # price cluster

    async def test_empty_records(self):
        embedder = _FakeEmbedder()
        detector = SemanticPatternDetector(
            embedder, min_frequency=3
        )
        assert await detector.detect([]) == []

    async def test_below_min_frequency(self):
        embedder = _FakeEmbedder()
        detector = SemanticPatternDetector(
            embedder, min_frequency=10
        )
        records = [_make_record(f"task {i}") for i in range(5)]
        clusters = await detector.detect(records)
        assert clusters == []

    async def test_filters_failed_records(self):
        embedder = _ClusterableEmbedder()
        detector = SemanticPatternDetector(
            embedder, min_frequency=3, similarity_threshold=0.8
        )
        records = [
            _make_record("weather in Tokyo", success=True),
            _make_record("weather in London", success=True),
            _make_record("weather in Paris", success=False),  # filtered
            _make_record("weather in Berlin", success=True),
        ]
        clusters = await detector.detect(records)
        # Only 3 successful weather records
        if clusters:
            assert all(r.success for c in clusters for r in c.records)

    async def test_embedding_failure_returns_empty(self):
        class _FailingEmbedder:
            dimensions = 8

            async def embed(self, texts):
                raise RuntimeError("embedding service down")

        detector = SemanticPatternDetector(
            _FailingEmbedder(), min_frequency=2  # type: ignore[arg-type]
        )
        records = [_make_record("test") for _ in range(5)]
        assert await detector.detect(records) == []
