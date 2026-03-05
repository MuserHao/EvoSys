"""Tests for ScheduleStore."""

from __future__ import annotations

from datetime import UTC, datetime

import orjson
import pytest

from evosys.storage.schedule_store import ScheduleStore


@pytest.fixture()
async def schedule_store(session_factory):
    return ScheduleStore(session_factory)


class TestScheduleStoreCreate:
    async def test_create_returns_task_id(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Check Amazon price", 3600)
        assert isinstance(task_id, str)
        assert len(task_id) == 26  # ULID

    async def test_created_task_is_enabled(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Check news", 86400)
        row = await schedule_store.get(task_id)
        assert row is not None
        assert row.enabled is True

    async def test_created_task_is_immediately_due(
        self, schedule_store: ScheduleStore
    ) -> None:
        """next_run_at is set to now so the first tick runs it immediately."""
        task_id = await schedule_store.create("Watch something", 3600)
        row = await schedule_store.get(task_id)
        assert row is not None
        # next_run_at should be set (not None) and the task should appear as due
        due_ids = {t.task_id for t in await schedule_store.get_due()}
        assert task_id in due_ids

    async def test_get_missing_returns_none(
        self, schedule_store: ScheduleStore
    ) -> None:
        result = await schedule_store.get("01AAAAAAAAAAAAAAAAAAAAAAAAA")
        assert result is None


class TestScheduleStoreDue:
    async def test_newly_created_task_is_due(
        self, schedule_store: ScheduleStore
    ) -> None:
        await schedule_store.create("Check price", 3600)
        due = await schedule_store.get_due()
        assert len(due) == 1

    async def test_get_due_respects_next_run_at(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Future task", 3600)
        # Push next_run_at far into the future by recording a result
        await schedule_store.record_result(task_id, {"answer": "done"})
        # After recording, next_run_at advances by interval_seconds (1h)
        due = await schedule_store.get_due(now=datetime.now(UTC))
        assert not any(t.task_id == task_id for t in due)

    async def test_disabled_task_not_due(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Disabled task", 3600)
        await schedule_store.disable(task_id)
        due = await schedule_store.get_due()
        assert not any(t.task_id == task_id for t in due)


class TestScheduleStoreRecordResult:
    async def test_record_result_stores_json(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Price check", 3600)
        await schedule_store.record_result(
            task_id, {"answer": "Price is $99", "total_tokens": 42}
        )
        row = await schedule_store.get(task_id)
        assert row is not None
        data = orjson.loads(row.last_result_json)
        assert data["answer"] == "Price is $99"

    async def test_record_result_advances_next_run_at(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Check", 7200)  # 2h interval
        # Task should be due now (just created)
        assert any(t.task_id == task_id for t in await schedule_store.get_due())
        # After recording a result next_run_at moves forward — task no longer due
        await schedule_store.record_result(task_id, {"answer": "ok"})
        assert not any(t.task_id == task_id for t in await schedule_store.get_due())

    async def test_record_result_sets_last_run_at(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Check", 3600)
        assert (await schedule_store.get(task_id)).last_run_at is None  # type: ignore[union-attr]
        await schedule_store.record_result(task_id, {})
        row = await schedule_store.get(task_id)
        assert row is not None
        assert row.last_run_at is not None


class TestScheduleStoreListAndDelete:
    async def test_list_enabled_returns_only_enabled(
        self, schedule_store: ScheduleStore
    ) -> None:
        t1 = await schedule_store.create("Task 1", 3600)
        t2 = await schedule_store.create("Task 2", 3600)
        await schedule_store.disable(t1)
        enabled = await schedule_store.list_enabled()
        ids = {r.task_id for r in enabled}
        assert t1 not in ids
        assert t2 in ids

    async def test_delete_removes_task(
        self, schedule_store: ScheduleStore
    ) -> None:
        task_id = await schedule_store.create("Delete me", 3600)
        await schedule_store.delete(task_id)
        assert await schedule_store.get(task_id) is None

    async def test_delete_noop_if_missing(
        self, schedule_store: ScheduleStore
    ) -> None:
        await schedule_store.delete("01AAAAAAAAAAAAAAAAAAAAAAAAA")  # must not raise
