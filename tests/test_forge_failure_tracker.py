"""Tests for ForgeFailureTracker."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from evosys.forge.failure_tracker import ForgeFailureTracker
from evosys.storage.memory_store import MemoryStore
from evosys.storage.models import Base


@pytest.fixture()
async def memory_store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    yield MemoryStore(factory)
    await engine.dispose()


class TestForgeFailureTracker:
    async def test_no_failures_allows_forge(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store)
        assert await tracker.should_skip("example.com") is False

    async def test_single_failure_still_allows(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store, max_attempts=3)
        await tracker.record_failure("example.com", "compile failed")
        assert await tracker.should_skip("example.com") is False

    async def test_threshold_abandons_domain(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store, max_attempts=3)
        await tracker.record_failure("bad.com", "error 1")
        await tracker.record_failure("bad.com", "error 2")
        rec = await tracker.record_failure("bad.com", "error 3")
        assert rec.abandoned is True
        assert rec.attempt_count == 3
        assert await tracker.should_skip("bad.com") is True

    async def test_success_clears_history(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store, max_attempts=3)
        await tracker.record_failure("recover.com", "error 1")
        await tracker.record_failure("recover.com", "error 2")
        await tracker.record_success("recover.com")
        # Should be back to clean slate
        assert await tracker.should_skip("recover.com") is False

    async def test_custom_max_attempts(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store, max_attempts=1)
        rec = await tracker.record_failure("fragile.com", "error")
        assert rec.abandoned is True
        assert await tracker.should_skip("fragile.com") is True

    async def test_error_stored(self, memory_store: MemoryStore):
        tracker = ForgeFailureTracker(memory_store)
        rec = await tracker.record_failure("err.com", "unsafe code detected")
        assert rec.last_error == "unsafe code detected"
        assert rec.attempt_count == 1
