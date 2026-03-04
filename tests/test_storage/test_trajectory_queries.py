"""Tests for TrajectoryStore query extensions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ulid import ULID

from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.trajectory_store import TrajectoryStore


def _make_record(
    action_name: str = "llm_extract",
    context_summary: str = "LLM extraction from https://example.com/page",
    skill_used: str | None = None,
    timestamp: datetime | None = None,
    session_id: ULID | None = None,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=session_id or new_ulid(),
        iteration_index=0,
        context_summary=context_summary,
        action_name=action_name,
        action_params={"target_schema": "{}"},
        action_result={"title": "Test Page"},
        skill_used=skill_used,
        timestamp_utc=timestamp or datetime.now(UTC),
    )


class TestGetRecent:
    async def test_returns_records_after_since(
        self, trajectory_store: TrajectoryStore
    ):
        old = _make_record(timestamp=datetime(2024, 1, 1, tzinfo=UTC))
        new = _make_record(timestamp=datetime(2025, 6, 1, tzinfo=UTC))
        await trajectory_store.save(old)
        await trajectory_store.save(new)

        results = await trajectory_store.get_recent(
            since=datetime(2025, 1, 1, tzinfo=UTC)
        )
        assert len(results) == 1
        assert results[0].trace_id == new.trace_id

    async def test_respects_limit(self, trajectory_store: TrajectoryStore):
        now = datetime.now(UTC)
        for i in range(5):
            rec = _make_record(timestamp=now + timedelta(seconds=i))
            await trajectory_store.save(rec)

        results = await trajectory_store.get_recent(
            since=now - timedelta(hours=1), limit=3
        )
        assert len(results) == 3


class TestGetByActionName:
    async def test_filters_by_action(self, trajectory_store: TrajectoryStore):
        await trajectory_store.save(_make_record(action_name="fetch_url"))
        await trajectory_store.save(_make_record(action_name="llm_extract"))
        await trajectory_store.save(_make_record(action_name="llm_extract"))

        results = await trajectory_store.get_by_action_name("llm_extract")
        assert len(results) == 2

    async def test_empty_result(self, trajectory_store: TrajectoryStore):
        results = await trajectory_store.get_by_action_name("nonexistent")
        assert results == []


class TestCountByActionName:
    async def test_counts(self, trajectory_store: TrajectoryStore):
        await trajectory_store.save(_make_record(action_name="fetch_url"))
        await trajectory_store.save(_make_record(action_name="llm_extract"))
        await trajectory_store.save(_make_record(action_name="llm_extract"))

        counts = await trajectory_store.count_by_action_name()
        assert counts["fetch_url"] == 1
        assert counts["llm_extract"] == 2

    async def test_empty_store(self, trajectory_store: TrajectoryStore):
        counts = await trajectory_store.count_by_action_name()
        assert counts == {}


class TestGetLlmExtractionsByDomain:
    async def test_groups_by_domain(self, trajectory_store: TrajectoryStore):
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://example.com/a"
            )
        )
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://example.com/b"
            )
        )
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://other.com/x"
            )
        )

        result = await trajectory_store.get_llm_extractions_by_domain()
        assert "example.com" in result
        assert len(result["example.com"]) == 2
        assert "other.com" in result
        assert len(result["other.com"]) == 1

    async def test_excludes_skill_used(
        self, trajectory_store: TrajectoryStore
    ):
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://example.com/a",
                skill_used="extract:example.com",
            )
        )
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://example.com/b"
            )
        )

        result = await trajectory_store.get_llm_extractions_by_domain()
        assert len(result.get("example.com", [])) == 1

    async def test_strips_www(self, trajectory_store: TrajectoryStore):
        await trajectory_store.save(
            _make_record(
                context_summary="LLM extraction from https://www.example.com/a"
            )
        )

        result = await trajectory_store.get_llm_extractions_by_domain()
        # www. is stripped by the regex
        assert "example.com" in result

    async def test_excludes_non_llm_actions(
        self, trajectory_store: TrajectoryStore
    ):
        await trajectory_store.save(
            _make_record(
                action_name="fetch_url",
                context_summary="Fetch from https://example.com/a",
            )
        )

        result = await trajectory_store.get_llm_extractions_by_domain()
        assert result == {}
