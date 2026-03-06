"""Forge failure tracker — stop retrying hopeless domains.

Tracks forge failures per domain and decides when to skip future
attempts, preventing wasted LLM credits on domains that consistently
fail synthesis or validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from evosys.storage.memory_store import MemoryStore

log = structlog.get_logger()

_NAMESPACE = "forge_failures"


@dataclass
class ForgeFailureRecord:
    """Tracks forge failure history for a single domain."""

    domain: str
    attempt_count: int = 0
    last_error: str = ""
    abandoned: bool = False


class ForgeFailureTracker:
    """Track forge failures per domain and skip hopeless ones.

    Backed by :class:`MemoryStore` with namespace ``forge_failures``.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        *,
        max_attempts: int = 3,
    ) -> None:
        self._store = memory_store
        self._max_attempts = max_attempts

    async def should_skip(self, domain: str) -> bool:
        """Return True if *domain* has been abandoned (too many failures)."""
        record = await self._load(domain)
        if record is None:
            return False
        return record.abandoned

    async def record_failure(
        self, domain: str, error: str
    ) -> ForgeFailureRecord:
        """Record a forge failure for *domain* and return updated record."""
        record = await self._load(domain) or ForgeFailureRecord(domain=domain)
        record.attempt_count += 1
        record.last_error = error[:500]
        if record.attempt_count >= self._max_attempts:
            record.abandoned = True
            log.warning(
                "forge_failure.abandoned",
                domain=domain,
                attempts=record.attempt_count,
            )
        await self._save(record)
        return record

    async def record_success(self, domain: str) -> None:
        """Clear failure history for *domain* after a successful forge."""
        await self._store.delete(domain, namespace=_NAMESPACE)

    async def _load(self, domain: str) -> ForgeFailureRecord | None:
        raw = await self._store.get(domain, namespace=_NAMESPACE)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return ForgeFailureRecord(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    async def _save(self, record: ForgeFailureRecord) -> None:
        data = json.dumps({
            "domain": record.domain,
            "attempt_count": record.attempt_count,
            "last_error": record.last_error,
            "abandoned": record.abandoned,
        })
        await self._store.set(record.domain, data, namespace=_NAMESPACE)
