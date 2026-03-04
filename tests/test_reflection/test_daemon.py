"""Tests for ReflectionDaemon."""

from __future__ import annotations

from evosys.reflection.daemon import ReflectionDaemon
from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.trajectory_store import TrajectoryStore


def _make_record(
    domain: str = "example.com",
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=new_ulid(),
        iteration_index=0,
        context_summary=f"LLM extraction from https://{domain}/page",
        action_name="llm_extract",
        action_params={"target_schema": "{}"},
        action_result={"title": "Test"},
    )


class TestRunCycle:
    async def test_produces_candidates(
        self, trajectory_store: TrajectoryStore
    ):
        for _ in range(5):
            await trajectory_store.save(_make_record())

        daemon = ReflectionDaemon(trajectory_store, min_frequency=3)
        candidates = await daemon.run_cycle()
        assert len(candidates) == 1
        assert candidates[0].frequency == 5
        assert candidates[0].action_sequence == ["llm_extract"]

    async def test_empty_store_returns_empty(
        self, trajectory_store: TrajectoryStore
    ):
        daemon = ReflectionDaemon(trajectory_store)
        candidates = await daemon.run_cycle()
        assert candidates == []

    async def test_below_threshold_returns_empty(
        self, trajectory_store: TrajectoryStore
    ):
        await trajectory_store.save(_make_record())
        await trajectory_store.save(_make_record())

        daemon = ReflectionDaemon(trajectory_store, min_frequency=5)
        candidates = await daemon.run_cycle()
        assert candidates == []

    async def test_multiple_domains(
        self, trajectory_store: TrajectoryStore
    ):
        for _ in range(4):
            await trajectory_store.save(_make_record("a.com"))
        for _ in range(6):
            await trajectory_store.save(_make_record("b.com"))

        daemon = ReflectionDaemon(trajectory_store, min_frequency=3)
        candidates = await daemon.run_cycle()
        assert len(candidates) == 2
        # Sorted by frequency
        assert candidates[0].frequency == 6
        assert candidates[1].frequency == 4

    async def test_candidate_has_trace_ids(
        self, trajectory_store: TrajectoryStore
    ):
        for _ in range(3):
            await trajectory_store.save(_make_record())

        daemon = ReflectionDaemon(trajectory_store, min_frequency=3)
        candidates = await daemon.run_cycle()
        assert len(candidates[0].occurrence_trace_ids) == 3

    async def test_candidate_has_inferred_schema(
        self, trajectory_store: TrajectoryStore
    ):
        for _ in range(3):
            await trajectory_store.save(_make_record())

        daemon = ReflectionDaemon(trajectory_store, min_frequency=3)
        candidates = await daemon.run_cycle()
        schema = candidates[0].output_schema_inferred
        assert "title" in schema
