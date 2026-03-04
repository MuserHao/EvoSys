"""Tests for built-in tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from evosys.core.tool import Tool
from evosys.core.types import Observation
from evosys.executors.http_executor import HttpExecutor
from evosys.schemas._types import new_ulid
from evosys.tools.builtins import (
    ExtractStructuredTool,
    FileListTool,
    FileReadTool,
    FileWriteTool,
    PythonEvalTool,
    ShellExecTool,
    WebFetchTool,
)

# ---------------------------------------------------------------------------
# Protocol compliance — one parametrized check covers all 7 tools
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool",
    [
        WebFetchTool(HttpExecutor()),
        ExtractStructuredTool(AsyncMock()),
        ShellExecTool(),
        FileReadTool(),
        FileWriteTool(),
        FileListTool(),
        PythonEvalTool(),
    ],
    ids=[
        "web_fetch",
        "extract_structured",
        "shell_exec",
        "file_read",
        "file_write",
        "file_list",
        "python_eval",
    ],
)
def test_tool_protocol_compliance(tool: Tool) -> None:
    """Every built-in tool must satisfy the Tool protocol and produce a
    well-formed OpenAI function descriptor."""
    assert isinstance(tool, Tool)
    assert isinstance(tool.name, str) and tool.name
    assert isinstance(tool.description, str) and tool.description
    assert isinstance(tool.parameters_schema, dict)
    fmt = tool.to_openai_tool()
    assert fmt["type"] == "function"
    fn = fmt["function"]
    assert fn["name"] == tool.name
    assert "parameters" in fn
    assert "properties" in fn["parameters"]


# ---------------------------------------------------------------------------
# WebFetchTool — functional tests
# ---------------------------------------------------------------------------


class TestWebFetchTool:
    async def test_call_success(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(
                action_id=new_ulid(),
                success=True,
                result={"html": "<h1>Hello</h1>", "status_code": 200, "url": "http://example.com"},
                latency_ms=100,
            )
        )
        result = await WebFetchTool(http)(url="http://example.com")
        assert result["html"] == "<h1>Hello</h1>"
        assert result["status_code"] == 200

    async def test_call_failure(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(action_id=new_ulid(), success=False, error="Timeout")
        )
        result = await WebFetchTool(http)(url="http://example.com")
        assert "error" in result


# ---------------------------------------------------------------------------
# ExtractStructuredTool — functional tests
# ---------------------------------------------------------------------------


class TestExtractStructuredTool:
    async def test_call_success(self) -> None:
        @dataclass
        class _FakeResult:
            data: dict[str, object]

        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(return_value=_FakeResult(data={"title": "Test"}))
        result = await ExtractStructuredTool(mock_agent)(
            url="http://example.com", schema_description='{"title":"string"}'
        )
        assert result == {"title": "Test"}

    async def test_call_failure(self) -> None:
        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ExtractStructuredTool(mock_agent)(url="http://example.com")
        assert "error" in result


# ---------------------------------------------------------------------------
# ShellExecTool — functional tests
# ---------------------------------------------------------------------------


class TestShellExecTool:
    async def test_echo_success(self) -> None:
        result = await ShellExecTool()(command="echo hello")
        assert result["stdout"].strip() == "hello"
        assert result["return_code"] == 0

    async def test_exit_failure(self) -> None:
        result = await ShellExecTool()(command="exit 1")
        assert result["return_code"] == 1

    async def test_timeout(self) -> None:
        result = await ShellExecTool()(command="sleep 10", timeout_s=0.1)
        assert "error" in result
        assert result["return_code"] == -1

    async def test_working_dir(self, tmp_path: Path) -> None:
        result = await ShellExecTool()(command="pwd", working_dir=str(tmp_path))
        assert str(tmp_path) in result["stdout"]

    async def test_invalid_working_dir(self) -> None:
        result = await ShellExecTool()(command="echo hi", working_dir="/nonexistent_dir_xyz")
        assert "error" in result


# ---------------------------------------------------------------------------
# FileReadTool — functional tests
# ---------------------------------------------------------------------------


class TestFileReadTool:
    async def test_read_temp_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        result = await FileReadTool()(path=str(f))
        assert result["content"] == "hello world"
        assert result["size_bytes"] == len(b"hello world")

    async def test_file_not_found(self) -> None:
        result = await FileReadTool()(path="/nonexistent_xyz.txt")
        assert "error" in result

    async def test_file_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_text("x" * 100)
        result = await FileReadTool(max_file_bytes=10)(path=str(f))
        assert "error" in result
        assert "too large" in result["error"].lower()

    async def test_path_is_directory(self, tmp_path: Path) -> None:
        result = await FileReadTool()(path=str(tmp_path))
        assert "error" in result


# ---------------------------------------------------------------------------
# FileWriteTool — functional tests
# ---------------------------------------------------------------------------


class TestFileWriteTool:
    async def test_write_and_read_back(self, tmp_path: Path) -> None:
        f = tmp_path / "out.txt"
        result = await FileWriteTool()(path=str(f), content="hello")
        assert result["mode"] == "write"
        assert result["bytes_written"] == 5
        assert f.read_text() == "hello"

    async def test_append_mode(self, tmp_path: Path) -> None:
        f = tmp_path / "log.txt"
        f.write_text("line1\n")
        result = await FileWriteTool()(path=str(f), content="line2\n", append=True)
        assert result["mode"] == "append"
        assert f.read_text() == "line1\nline2\n"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "a" / "b" / "c.txt"
        await FileWriteTool()(path=str(f), content="nested")
        assert f.read_text() == "nested"

    async def test_content_too_large(self, tmp_path: Path) -> None:
        result = await FileWriteTool(max_write_bytes=10)(
            path=str(tmp_path / "big.txt"), content="x" * 100
        )
        assert "error" in result
        assert "too large" in result["error"].lower()


# ---------------------------------------------------------------------------
# FileListTool — functional tests
# ---------------------------------------------------------------------------


class TestFileListTool:
    async def test_list_temp_dir(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        result = await FileListTool()(path=str(tmp_path))
        names = {e["name"] for e in result["entries"]}
        assert {"a.txt", "b.txt", "sub"} <= names
        assert result["total"] == 3

    async def test_glob_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        result = await FileListTool()(path=str(tmp_path), pattern="*.txt")
        names = {e["name"] for e in result["entries"]}
        assert "a.txt" in names
        assert "b.py" not in names

    async def test_invalid_dir(self) -> None:
        result = await FileListTool()(path="/nonexistent_dir_xyz")
        assert "error" in result

    async def test_recursive_mode(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        (tmp_path / "top.txt").write_text("top")
        result = await FileListTool()(path=str(tmp_path), pattern="*.txt", recursive=True)
        names = {e["name"] for e in result["entries"]}
        assert "top.txt" in names
        assert "deep.txt" in names


# ---------------------------------------------------------------------------
# PythonEvalTool — functional tests
# ---------------------------------------------------------------------------


class TestPythonEvalTool:
    async def test_print_expression(self) -> None:
        result = await PythonEvalTool()(code="print(2 + 2)")
        assert result["stdout"].strip() == "4"
        assert result["return_code"] == 0

    async def test_raise_error(self) -> None:
        result = await PythonEvalTool()(code="raise ValueError('boom')")
        assert result["return_code"] != 0
        assert "boom" in result["stderr"]

    async def test_timeout(self) -> None:
        result = await PythonEvalTool()(
            code="import time; time.sleep(10)", timeout_s=0.1
        )
        assert "error" in result
        assert result["return_code"] == -1

    async def test_multiline_code(self) -> None:
        result = await PythonEvalTool()(code="x = 3\ny = 4\nprint(x * y)")
        assert result["stdout"].strip() == "12"
        assert result["return_code"] == 0
