"""Tests for ToolCall and ToolResult types."""

import pytest
from pydantic import ValidationError

from evosys.core.types import ToolCall, ToolResult


class TestToolCall:
    def test_valid_construction(self) -> None:
        tc = ToolCall(call_id="c1", tool_name="web_fetch", arguments={"url": "http://x.com"})
        assert tc.call_id == "c1"
        assert tc.tool_name == "web_fetch"
        assert tc.arguments == {"url": "http://x.com"}

    def test_default_arguments(self) -> None:
        tc = ToolCall(call_id="c1", tool_name="t")
        assert tc.arguments == {}

    def test_empty_call_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolCall(call_id="", tool_name="t")

    def test_empty_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolCall(call_id="c1", tool_name="")

    def test_serialization_roundtrip(self) -> None:
        tc = ToolCall(call_id="c1", tool_name="t", arguments={"k": "v"})
        raw = tc.model_dump_orjson()
        restored = ToolCall.model_validate_orjson(raw)
        assert restored == tc

    def test_json_schema(self) -> None:
        schema = ToolCall.model_json_schema()
        assert "call_id" in schema["properties"]
        assert "tool_name" in schema["properties"]


class TestToolResult:
    def test_success_result(self) -> None:
        tr = ToolResult(
            call_id="c1",
            tool_name="web_fetch",
            success=True,
            result={"html": "<h1>hi</h1>"},
            latency_ms=42.5,
        )
        assert tr.success
        assert tr.error is None
        assert tr.latency_ms == 42.5

    def test_error_result(self) -> None:
        tr = ToolResult(
            call_id="c1",
            tool_name="web_fetch",
            success=False,
            error="timeout",
        )
        assert not tr.success
        assert tr.error == "timeout"
        assert tr.result == {}
        assert tr.latency_ms == 0

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolResult(call_id="c1", tool_name="t", success=True, latency_ms=-1)

    def test_serialization_roundtrip(self) -> None:
        tr = ToolResult(
            call_id="c1",
            tool_name="t",
            success=True,
            result={"a": 1},
            latency_ms=10,
        )
        raw = tr.model_dump_orjson()
        restored = ToolResult.model_validate_orjson(raw)
        assert restored == tr

    def test_empty_call_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolResult(call_id="", tool_name="t", success=True)
