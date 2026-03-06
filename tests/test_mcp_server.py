"""Tests for EvoSys MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from evosys.mcp_server import (
    _build_tool_list,
    _call_recall,
    _call_remember,
    _call_skills_list,
    _handle_tool_call,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(
    skills: list[tuple[str, str, float]] | None = None,
) -> MagicMock:
    """Create a mock runtime with optional skills."""
    runtime = MagicMock()

    # Build mock skill entries
    entries = []
    if skills:
        for name, desc, confidence in skills:
            entry = MagicMock()
            entry.record.name = name
            entry.record.description = desc
            entry.record.confidence_score = confidence
            entry.record.status.value = "active"
            entry.record.input_schema = {}
            entry.record.output_schema = {}
            entry.invocation_count = 0
            entries.append(entry)

    runtime.skill_registry.list_active.return_value = entries
    runtime.skill_registry.list_all.return_value = entries
    runtime.memory_store.set = AsyncMock()
    runtime.memory_store.get = AsyncMock(return_value=None)
    runtime.memory_store.list_keys = AsyncMock(return_value=[])
    runtime.trajectory_logger.log = AsyncMock()
    return runtime


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildToolList:
    def test_always_includes_core_tools(self):
        runtime = _make_runtime()
        tools = _build_tool_list(runtime)
        names = [t["name"] for t in tools]
        assert "evosys_extract" in names
        assert "evosys_remember" in names
        assert "evosys_recall" in names
        assert "evosys_skills" in names

    def test_includes_registered_skills(self):
        runtime = _make_runtime([
            ("extract:github.com", "GitHub extractor", 0.9),
        ])
        tools = _build_tool_list(runtime)
        names = [t["name"] for t in tools]
        assert "evosys_extract_github_com" in names

    def test_skill_description_includes_confidence(self):
        runtime = _make_runtime([
            ("extract:test.com", "Test skill", 0.85),
        ])
        tools = _build_tool_list(runtime)
        skill_tool = next(t for t in tools if "test_com" in t["name"])
        assert "0.85" in skill_tool["description"]


class TestHandleToolCall:
    @pytest.mark.asyncio
    async def test_remember(self):
        runtime = _make_runtime()
        result = await _call_remember(
            runtime, {"key": "foo", "value": "bar"}
        )
        assert not result.get("isError")
        runtime.memory_store.set.assert_called_once_with("foo", "bar")

    @pytest.mark.asyncio
    async def test_recall_missing_key(self):
        runtime = _make_runtime()
        runtime.memory_store.get = AsyncMock(return_value=None)
        result = await _call_recall(runtime, {"key": "missing"})
        assert "not found" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_recall_existing_key(self):
        runtime = _make_runtime()
        runtime.memory_store.get = AsyncMock(return_value="stored_value")
        result = await _call_recall(runtime, {"key": "mykey"})
        assert result["content"][0]["text"] == "stored_value"

    def test_skills_list(self):
        runtime = _make_runtime([
            ("extract:a.com", "Skill A", 0.9),
            ("extract:b.com", "Skill B", 0.8),
        ])
        result = _call_skills_list(runtime)
        text = result["content"][0]["text"]
        assert "2 active skills" in text
        assert "extract:a.com" in text
        assert "extract:b.com" in text

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        runtime = _make_runtime()
        result = await _handle_tool_call(
            runtime, {"name": "nonexistent", "arguments": {}}
        )
        assert result.get("isError")
        assert "Unknown" in result["content"][0]["text"]
