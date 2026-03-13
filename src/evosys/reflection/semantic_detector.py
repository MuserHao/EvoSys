"""Semantic pattern detector — clusters trajectories by task similarity.

Unlike the domain-based PatternDetector which groups by URL hostname,
this detector uses embedding vectors to find semantically similar
tasks regardless of domain.  This catches patterns like "weather
queries" or "price lookups" that span multiple domains.

Requires an EmbeddingProvider for vector generation.  Falls back
gracefully to an empty result if embeddings are unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from evosys.schemas.trajectory import TrajectoryRecord

if TYPE_CHECKING:
    from evosys.llm.embeddings import EmbeddingProvider

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class SemanticCluster:
    """A cluster of semantically similar trajectory records."""

    label: str
    records: list[TrajectoryRecord]
    centroid_text: str
    avg_similarity: float


class SemanticPatternDetector:
    """Detect recurring patterns by embedding similarity.

    Algorithm:
    1. Embed the ``context_summary`` of each trajectory record
    2. Greedy clustering: for each record, find the nearest existing
       cluster centroid within ``similarity_threshold``
    3. If no cluster is close enough, start a new cluster
    4. Return clusters above ``min_frequency``

    This is intentionally simple (no HDBSCAN dependency). It runs in
    O(n x k) where k is the number of clusters -- fine for <10K records.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        min_frequency: int = 3,
        similarity_threshold: float = 0.85,
    ) -> None:
        self._embedder = embedding_provider
        self._min_frequency = min_frequency
        self._similarity_threshold = similarity_threshold

    async def detect(
        self,
        records: list[TrajectoryRecord],
    ) -> list[SemanticCluster]:
        """Cluster records by semantic similarity."""
        if not records:
            return []

        # Only use successful records with meaningful context
        filtered = [
            r for r in records
            if r.success and len(r.context_summary) > 10
        ]
        if len(filtered) < self._min_frequency:
            return []

        # Embed context summaries
        texts = [r.context_summary[:500] for r in filtered]
        try:
            vectors = await self._embedder.embed(texts)
        except Exception:
            log.debug("semantic_detector.embedding_failed")
            return []

        if len(vectors) != len(filtered):
            return []

        # Greedy clustering
        clusters: list[_Cluster] = []
        for rec, vec in zip(filtered, vectors, strict=True):
            best_idx = -1
            best_sim = 0.0
            for i, cluster in enumerate(clusters):
                sim = _cosine_similarity(vec, cluster.centroid)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i

            if best_sim >= self._similarity_threshold and best_idx >= 0:
                clusters[best_idx].add(rec, vec)
            else:
                clusters.append(_Cluster(rec, vec))

        # Filter by min_frequency and convert to result type
        result = []
        for cluster in clusters:
            if len(cluster.records) < self._min_frequency:
                continue
            result.append(SemanticCluster(
                label=cluster.records[0].action_name,
                records=cluster.records,
                centroid_text=cluster.records[0].context_summary[:200],
                avg_similarity=cluster.avg_similarity(),
            ))

        result.sort(key=lambda c: len(c.records), reverse=True)
        return result


class _Cluster:
    """Internal mutable cluster state."""

    def __init__(self, first_record: TrajectoryRecord, vector: list[float]):
        self.records: list[TrajectoryRecord] = [first_record]
        self.centroid: list[float] = list(vector)
        self._similarities: list[float] = [1.0]

    def add(self, record: TrajectoryRecord, vector: list[float]) -> None:
        sim = _cosine_similarity(vector, self.centroid)
        self._similarities.append(sim)
        self.records.append(record)
        # Update centroid as running average
        n = len(self.records)
        self.centroid = [
            (c * (n - 1) + v) / n
            for c, v in zip(self.centroid, vector, strict=True)
        ]

    def avg_similarity(self) -> float:
        return sum(self._similarities) / len(self._similarities)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
