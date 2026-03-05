"""Tests for WatchTool and InboxTool."""

from __future__ import annotations

import pytest

from evosys.storage.schedule_store import ScheduleStore
from evosys.tools.builtins import InboxTool, WatchTool


@pytest.fixture()
async def schedule_store(session_factory):
    return ScheduleStore(session_factory)


class TestWatchTool:
    async def test_creates_scheduled_task(
        self, schedule_store: ScheduleStore
    ) -> None:
        tool = WatchTool(schedule_store)
        result = await tool(task="Check Amazon price", interval_hours=6)
        assert result["status"] == "scheduled"
        assert "task_id" in result
        assert result["interval_hours"] == 6.0

    async def test_empty_task_returns_error(
        self, schedule_store: ScheduleStore
    ) -> None:
        tool = WatchTool(schedule_store)
        result = await tool(task="", interval_hours=6)
        assert "error" in result

    async def test_invalid_interval_returns_error(
        self, schedule_store: ScheduleStore
    ) -> None:
        tool = WatchTool(schedule_store)
        result = await tool(task="Check something", interval_hours=-1)
        assert "error" in result

    def test_protocol_compliance(self, schedule_store: ScheduleStore) -> None:
        from evosys.core.tool import Tool
        assert isinstance(WatchTool(schedule_store), Tool)

    def test_to_openai_tool_format(self, schedule_store: ScheduleStore) -> None:
        fmt = WatchTool(schedule_store).to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "watch"
        assert "task" in fn["parameters"]["required"]
        assert "interval_hours" in fn["parameters"]["required"]


class TestInboxTool:
    async def test_empty_inbox(self, schedule_store: ScheduleStore) -> None:
        tool = InboxTool(schedule_store)
        result = await tool()
        assert result["count"] == 0
        assert result["watches"] == []

    async def test_lists_active_watches(
        self, schedule_store: ScheduleStore
    ) -> None:
        watch = WatchTool(schedule_store)
        await watch(task="Track news", interval_hours=12)

        inbox = InboxTool(schedule_store)
        result = await inbox()
        assert result["count"] == 1
        assert result["watches"][0]["task"] == "Track news"

    async def test_get_specific_task(
        self, schedule_store: ScheduleStore
    ) -> None:
        watch = WatchTool(schedule_store)
        created = await watch(task="Price watch", interval_hours=24)
        task_id = created["task_id"]

        inbox = InboxTool(schedule_store)
        result = await inbox(task_id=task_id)
        assert result["task_id"] == task_id
        assert result["task"] == "Price watch"

    async def test_missing_task_id_returns_error(
        self, schedule_store: ScheduleStore
    ) -> None:
        inbox = InboxTool(schedule_store)
        result = await inbox(task_id="01AAAAAAAAAAAAAAAAAAAAAAAAA")
        assert "error" in result

    async def test_result_surfaced_after_record(
        self, schedule_store: ScheduleStore
    ) -> None:
        watch = WatchTool(schedule_store)
        created = await watch(task="Check stock", interval_hours=6)
        task_id = created["task_id"]

        await schedule_store.record_result(
            task_id, {"answer": "AAPL is at $192", "total_tokens": 50}
        )

        inbox = InboxTool(schedule_store)
        result = await inbox(task_id=task_id)
        assert result["result"]["answer"] == "AAPL is at $192"

    def test_protocol_compliance(self, schedule_store: ScheduleStore) -> None:
        from evosys.core.tool import Tool
        assert isinstance(InboxTool(schedule_store), Tool)

    def test_to_openai_tool_format(self, schedule_store: ScheduleStore) -> None:
        fmt = InboxTool(schedule_store).to_openai_tool()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "inbox"
