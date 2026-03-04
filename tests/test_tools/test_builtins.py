"""Tests for built-in tools (WebFetchTool, ExtractStructuredTool, and system tools)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

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


class TestWebFetchTool:
    def test_satisfies_protocol(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert isinstance(tool, Tool)

    def test_name(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert tool.name == "web_fetch"

    def test_description(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert "URL" in tool.description or "url" in tool.description.lower()

    def test_parameters_schema(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert "url" in tool.parameters_schema

    def test_to_openai_tool_format(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        fmt = tool.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "web_fetch"
        assert "required" in fn["parameters"]

    async def test_call_success(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(
                action_id=new_ulid(),
                success=True,
                result={
                    "html": "<h1>Hello</h1>",
                    "status_code": 200,
                    "url": "http://example.com",
                },
                latency_ms=100,
            )
        )
        tool = WebFetchTool(http)
        result = await tool(url="http://example.com")
        assert result["html"] == "<h1>Hello</h1>"
        assert result["status_code"] == 200

    async def test_call_failure(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(
                action_id=new_ulid(),
                success=False,
                error="Timeout",
            )
        )
        tool = WebFetchTool(http)
        result = await tool(url="http://example.com")
        assert "error" in result


class TestExtractStructuredTool:
    def test_satisfies_protocol(self) -> None:
        mock_agent = AsyncMock()
        tool = ExtractStructuredTool(mock_agent)
        assert isinstance(tool, Tool)

    def test_name(self) -> None:
        tool = ExtractStructuredTool(AsyncMock())
        assert tool.name == "extract_structured"

    def test_to_openai_tool_format(self) -> None:
        tool = ExtractStructuredTool(AsyncMock())
        fmt = tool.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "extract_structured"

    async def test_call_success(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class _FakeResult:
            data: dict[str, object]

        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(return_value=_FakeResult(data={"title": "Test"}))
        tool = ExtractStructuredTool(mock_agent)
        result = await tool(url="http://example.com", schema_description='{"title":"string"}')
        assert result == {"title": "Test"}

    async def test_call_failure(self) -> None:
        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(side_effect=RuntimeError("boom"))
        tool = ExtractStructuredTool(mock_agent)
        result = await tool(url="http://example.com")
        assert "error" in result


# ---------------------------------------------------------------------------
# ShellExecTool
# ---------------------------------------------------------------------------


class TestShellExecTool:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(ShellExecTool(), Tool)

    def test_name(self) -> None:
        assert ShellExecTool().name == "shell_exec"

    def test_description(self) -> None:
        assert "shell" in ShellExecTool().description.lower()

    def test_parameters_schema(self) -> None:
        schema = ShellExecTool().parameters_schema
        assert "command" in schema

    def test_to_openai_tool_format(self) -> None:
        fmt = ShellExecTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "shell_exec"
        assert "command" in fn["parameters"]["required"]

    async def test_echo_success(self) -> None:
        tool = ShellExecTool()
        result = await tool(command="echo hello")
        assert result["stdout"].strip() == "hello"
        assert result["return_code"] == 0

    async def test_exit_failure(self) -> None:
        tool = ShellExecTool()
        result = await tool(command="exit 1")
        assert result["return_code"] == 1

    async def test_timeout(self) -> None:
        tool = ShellExecTool()
        result = await tool(command="sleep 10", timeout_s=0.1)
        assert "error" in result
        assert result["return_code"] == -1

    async def test_working_dir(self, tmp_path: Path) -> None:
        tool = ShellExecTool()
        result = await tool(command="pwd", working_dir=str(tmp_path))
        assert str(tmp_path) in result["stdout"]

    async def test_invalid_working_dir(self) -> None:
        tool = ShellExecTool()
        result = await tool(
            command="echo hi", working_dir="/nonexistent_dir_xyz"
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# FileReadTool
# ---------------------------------------------------------------------------


class TestFileReadTool:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FileReadTool(), Tool)

    def test_name(self) -> None:
        assert FileReadTool().name == "file_read"

    def test_description(self) -> None:
        assert "file" in FileReadTool().description.lower()

    def test_parameters_schema(self) -> None:
        assert "path" in FileReadTool().parameters_schema

    def test_to_openai_tool_format(self) -> None:
        fmt = FileReadTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "file_read"
        assert "path" in fn["parameters"]["required"]

    async def test_read_temp_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        tool = FileReadTool()
        result = await tool(path=str(f))
        assert result["content"] == "hello world"
        assert result["size_bytes"] == len(b"hello world")

    async def test_file_not_found(self) -> None:
        tool = FileReadTool()
        result = await tool(path="/nonexistent_xyz.txt")
        assert "error" in result

    async def test_file_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_text("x" * 100)
        tool = FileReadTool(max_file_bytes=10)
        result = await tool(path=str(f))
        assert "error" in result
        assert "too large" in result["error"].lower()

    async def test_path_is_directory(self, tmp_path: Path) -> None:
        tool = FileReadTool()
        result = await tool(path=str(tmp_path))
        assert "error" in result


# ---------------------------------------------------------------------------
# FileWriteTool
# ---------------------------------------------------------------------------


class TestFileWriteTool:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FileWriteTool(), Tool)

    def test_name(self) -> None:
        assert FileWriteTool().name == "file_write"

    def test_description(self) -> None:
        assert "write" in FileWriteTool().description.lower()

    def test_parameters_schema(self) -> None:
        schema = FileWriteTool().parameters_schema
        assert "path" in schema
        assert "content" in schema

    def test_to_openai_tool_format(self) -> None:
        fmt = FileWriteTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "file_write"
        assert "path" in fn["parameters"]["required"]
        assert "content" in fn["parameters"]["required"]

    async def test_write_and_read_back(self, tmp_path: Path) -> None:
        f = tmp_path / "out.txt"
        tool = FileWriteTool()
        result = await tool(path=str(f), content="hello")
        assert result["mode"] == "write"
        assert result["bytes_written"] == 5
        assert f.read_text() == "hello"

    async def test_append_mode(self, tmp_path: Path) -> None:
        f = tmp_path / "log.txt"
        f.write_text("line1\n")
        tool = FileWriteTool()
        result = await tool(path=str(f), content="line2\n", append=True)
        assert result["mode"] == "append"
        assert f.read_text() == "line1\nline2\n"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "a" / "b" / "c.txt"
        tool = FileWriteTool()
        await tool(path=str(f), content="nested")
        assert f.read_text() == "nested"

    async def test_content_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        tool = FileWriteTool(max_write_bytes=10)
        result = await tool(path=str(f), content="x" * 100)
        assert "error" in result
        assert "too large" in result["error"].lower()


# ---------------------------------------------------------------------------
# FileListTool
# ---------------------------------------------------------------------------


class TestFileListTool:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(FileListTool(), Tool)

    def test_name(self) -> None:
        assert FileListTool().name == "file_list"

    def test_description(self) -> None:
        assert "list" in FileListTool().description.lower()

    def test_parameters_schema(self) -> None:
        schema = FileListTool().parameters_schema
        assert "path" in schema
        assert "pattern" in schema

    def test_to_openai_tool_format(self) -> None:
        fmt = FileListTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "file_list"

    async def test_list_temp_dir(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        tool = FileListTool()
        result = await tool(path=str(tmp_path))
        names = {e["name"] for e in result["entries"]}
        assert "a.txt" in names
        assert "b.txt" in names
        assert "sub" in names
        assert result["total"] == 3

    async def test_glob_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        tool = FileListTool()
        result = await tool(path=str(tmp_path), pattern="*.txt")
        names = {e["name"] for e in result["entries"]}
        assert "a.txt" in names
        assert "b.py" not in names

    async def test_invalid_dir(self) -> None:
        tool = FileListTool()
        result = await tool(path="/nonexistent_dir_xyz")
        assert "error" in result

    async def test_recursive_mode(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        (tmp_path / "top.txt").write_text("top")
        tool = FileListTool()
        result = await tool(
            path=str(tmp_path), pattern="*.txt", recursive=True
        )
        names = {e["name"] for e in result["entries"]}
        assert "top.txt" in names
        assert "deep.txt" in names


# ---------------------------------------------------------------------------
# PythonEvalTool
# ---------------------------------------------------------------------------


class TestPythonEvalTool:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(PythonEvalTool(), Tool)

    def test_name(self) -> None:
        assert PythonEvalTool().name == "python_eval"

    def test_description(self) -> None:
        assert "python" in PythonEvalTool().description.lower()

    def test_parameters_schema(self) -> None:
        assert "code" in PythonEvalTool().parameters_schema

    def test_to_openai_tool_format(self) -> None:
        fmt = PythonEvalTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "python_eval"
        assert "code" in fn["parameters"]["required"]

    async def test_print_expression(self) -> None:
        tool = PythonEvalTool()
        result = await tool(code="print(2 + 2)")
        assert result["stdout"].strip() == "4"
        assert result["return_code"] == 0

    async def test_raise_error(self) -> None:
        tool = PythonEvalTool()
        result = await tool(code="raise ValueError('boom')")
        assert result["return_code"] != 0
        assert "boom" in result["stderr"]

    async def test_timeout(self) -> None:
        tool = PythonEvalTool()
        result = await tool(
            code="import time; time.sleep(10)", timeout_s=0.1
        )
        assert "error" in result
        assert result["return_code"] == -1

    async def test_multiline_code(self) -> None:
        tool = PythonEvalTool()
        code = "x = 3\ny = 4\nprint(x * y)"
        result = await tool(code=code)
        assert result["stdout"].strip() == "12"
        assert result["return_code"] == 0
