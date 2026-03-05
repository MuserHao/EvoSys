"""Embedding provider — protocol + LiteLLM implementation.

Decouples embedding generation from storage so the embedding model
can be swapped without touching the store (e.g. local sentence-transformers
vs. cloud OpenAI text-embedding-3-small).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """A single text → vector mapping."""

    text: str
    vector: list[float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Structural protocol for embedding providers."""

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for each input text."""
        ...


class LiteLLMEmbeddingProvider:
    """Embedding provider backed by :func:`litellm.aembedding`.

    Supports any model litellm routes to: ``text-embedding-3-small``,
    ``text-embedding-ada-002``, ``ollama/nomic-embed-text``, etc.

    Parameters
    ----------
    model:
        Model identifier in litellm format.
    dimensions:
        Expected vector dimensionality (must match model output).
    batch_size:
        Maximum texts per API call.  Larger batches are split automatically.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 64,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* in batches, returning one vector per input."""
        import litellm

        if not texts:
            return []

        all_vectors: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            try:
                resp = await litellm.aembedding(model=self._model, input=batch)
                # litellm returns {data: [{embedding: [...], index: 0}, ...]}
                sorted_data = sorted(resp.data, key=lambda d: d["index"])
                for item in sorted_data:
                    all_vectors.append(item["embedding"])
            except Exception:
                log.exception("embeddings.batch_failed", batch_start=i)
                # Pad with zero vectors so indices stay aligned
                all_vectors.extend([[0.0] * self._dimensions] * len(batch))

            # Respect rate limits between batches
            if i + self._batch_size < len(texts):
                await asyncio.sleep(0.05)

        return all_vectors
