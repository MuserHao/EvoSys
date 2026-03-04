"""Tests for get_tool_trajectories() in TrajectoryStore."""

from __future__ import annotations

from ulid import ULID

from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.trajectory_store import TrajectoryStore


class TestGetToolTrajectories:
    async def test_returns_tool_records(self, trajectory_store: TrajectoryStore) -> None:
        sid = ULID()
        r1 = TrajectoryRecord(
            session_id=sid, iteration_index=0, action_name="tool:web_fetch",
            context_summary="test", latency_ms=10,
        )
        r2 = TrajectoryRecord(
            session_id=sid, iteration_index=1, action_name="tool:extract",
            context_summary="test", latency_ms=20,
        )
        r3 = TrajectoryRecord(
            session_id=sid, iteration_index=2, action_name="llm_extract",
            context_summary="test",
        )
        await trajectory_store.save(r1)
        await trajectory_store.save(r2)
        await trajectory_store.save(r3)

        results = await trajectory_store.get_tool_trajectories()
        names = {r.action_name for r in results}
        assert "tool:web_fetch" in names
        assert "tool:extract" in names
        assert "llm_extract" not in names

    async def test_empty_store(self, trajectory_store: TrajectoryStore) -> None:
        results = await trajectory_store.get_tool_trajectories()
        assert results == []

    async def test_limit(self, trajectory_store: TrajectoryStore) -> None:
        sid = ULID()
        for i in range(5):
            r = TrajectoryRecord(
                session_id=sid, iteration_index=i, action_name=f"tool:t{i}",
                context_summary="test",
            )
            await trajectory_store.save(r)

        results = await trajectory_store.get_tool_trajectories(limit=3)
        assert len(results) == 3
