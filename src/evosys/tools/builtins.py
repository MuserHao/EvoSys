"""Built-in tools for the general agent.

These wrap existing EvoSys components (HttpExecutor, ExtractionAgent) so
the agent loop can call them as standard tools.  System tools (shell, file
I/O, Python eval) are also provided as direct implementations.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from evosys.core.types import Action
from evosys.executors.http_executor import HttpExecutor
from evosys.schemas._types import new_ulid


class WebFetchTool:
    """Fetches a URL and returns HTML content. Wraps HttpExecutor."""

    def __init__(self, http_executor: HttpExecutor) -> None:
        self._http = http_executor

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page and return its HTML content. "
            "Use this when you need to read the contents of a URL."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        url = str(kwargs.get("url", ""))
        action = Action(
            action_id=new_ulid(),
            name="fetch_url",
            params={"url": url},
        )
        obs = await self._http.execute(action)
        if obs.success:
            return {
                "html": str(obs.result.get("html", "")),
                "status_code": obs.result.get("status_code", 0),
                "url": str(obs.result.get("url", url)),
            }
        return {"error": obs.error or "Unknown error"}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["url"],
                },
            },
        }


class ExtractStructuredTool:
    """Extracts structured data from HTML using LLM or skills.

    Wraps the existing ExtractionAgent, preserving full backward
    compatibility with skill routing and trajectory logging.
    """

    def __init__(self, extraction_agent: Any) -> None:
        self._agent = extraction_agent

    @property
    def name(self) -> str:
        return "extract_structured"

    @property
    def description(self) -> str:
        return (
            "Extract structured JSON data from a URL. Returns key-value pairs "
            "based on the page content. Provide the URL and optionally a schema "
            "description of the fields you want."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "url": {
                "type": "string",
                "description": "The URL to extract data from",
            },
            "schema_description": {
                "type": "string",
                "description": "Description of the target JSON schema",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        url = str(kwargs.get("url", ""))
        schema_desc = str(kwargs.get("schema_description", "{}"))
        try:
            result = await self._agent.extract(
                url=url,
                target_schema=schema_desc,
            )
            return dict(result.data)
        except Exception as exc:
            return {"error": str(exc)}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["url"],
                },
            },
        }


# ---------------------------------------------------------------------------
# System tools — direct implementations (no external component wrappers)
# ---------------------------------------------------------------------------


class ShellExecTool:
    """Run a shell command and return stdout/stderr/return_code."""

    def __init__(
        self,
        *,
        default_timeout_s: float = 30.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self._default_timeout_s = default_timeout_s
        self._max_output_bytes = max_output_bytes

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return its stdout, stderr, and "
            "return code. Use this to run CLI tools, scripts, or system "
            "commands."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout_s": {
                "type": "number",
                "description": "Timeout in seconds (default 30)",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for the command",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        command = str(kwargs.get("command", ""))
        timeout_s = float(str(kwargs.get("timeout_s", self._default_timeout_s)))
        working_dir = kwargs.get("working_dir")

        cwd: str | None = str(working_dir) if working_dir else None
        if cwd and not Path(cwd).is_dir():
            return {"error": f"working_dir does not exist: {cwd}"}

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.wait()
            return {"error": "Command timed out", "return_code": -1}

        return {
            "stdout": stdout_bytes[: self._max_output_bytes].decode(
                errors="replace"
            ),
            "stderr": stderr_bytes[: self._max_output_bytes].decode(
                errors="replace"
            ),
            "return_code": proc.returncode or 0,
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["command"],
                },
            },
        }


class FileReadTool:
    """Read the contents of a file."""

    def __init__(self, *, max_file_bytes: int = 10_000_000) -> None:
        self._max_file_bytes = max_file_bytes

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file and return it as text. "
            "Provide the file path and optionally an encoding."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
            },
            "encoding": {
                "type": "string",
                "description": "Text encoding (default utf-8)",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        path_str = str(kwargs.get("path", ""))
        encoding = str(kwargs.get("encoding", "utf-8"))
        p = Path(path_str)

        if not p.exists():
            return {"error": f"File not found: {path_str}"}
        if not p.is_file():
            return {"error": f"Path is not a file: {path_str}"}
        size = p.stat().st_size
        if size > self._max_file_bytes:
            return {
                "error": (
                    f"File too large: {size} bytes "
                    f"(limit {self._max_file_bytes})"
                )
            }

        content = await asyncio.to_thread(p.read_text, encoding=encoding)
        return {
            "content": content,
            "path": str(p.resolve()),
            "size_bytes": size,
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["path"],
                },
            },
        }


class FileWriteTool:
    """Write or append content to a file, creating parent dirs as needed."""

    def __init__(self, *, max_write_bytes: int = 10_000_000) -> None:
        self._max_write_bytes = max_write_bytes

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Creates parent directories if they "
            "don't exist. Use append=true to append instead of overwrite."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The text content to write",
            },
            "encoding": {
                "type": "string",
                "description": "Text encoding (default utf-8)",
            },
            "append": {
                "type": "boolean",
                "description": "Append to file instead of overwriting (default false)",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        path_str = str(kwargs.get("path", ""))
        content = str(kwargs.get("content", ""))
        encoding = str(kwargs.get("encoding", "utf-8"))
        append = bool(kwargs.get("append", False))

        content_bytes = content.encode(encoding)
        if len(content_bytes) > self._max_write_bytes:
            return {
                "error": (
                    f"Content too large: {len(content_bytes)} bytes "
                    f"(limit {self._max_write_bytes})"
                )
            }

        p = Path(path_str)

        def _write() -> int:
            p.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with p.open("a", encoding=encoding) as f:
                    f.write(content)
            else:
                p.write_text(content, encoding=encoding)
            return len(content_bytes)

        bytes_written = await asyncio.to_thread(_write)
        return {
            "path": str(p.resolve()),
            "bytes_written": bytes_written,
            "mode": "append" if append else "write",
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["path", "content"],
                },
            },
        }


class FileListTool:
    """List directory contents with optional glob filtering."""

    def __init__(self, *, max_entries: int = 1000) -> None:
        self._max_entries = max_entries

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return (
            "List files and directories. Supports glob patterns and "
            "recursive listing."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "path": {
                "type": "string",
                "description": "Directory path to list (default '.')",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter entries (default '*')",
            },
            "recursive": {
                "type": "boolean",
                "description": "Recurse into subdirectories (default false)",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        path_str = str(kwargs.get("path", "."))
        pattern = str(kwargs.get("pattern", "*"))
        recursive = bool(kwargs.get("recursive", False))

        p = Path(path_str)
        if not p.is_dir():
            return {"error": f"Not a directory: {path_str}"}

        def _list() -> tuple[list[dict[str, object]], int, bool]:
            matches = list(
                p.rglob(pattern) if recursive else p.glob(pattern)
            )
            total = len(matches)
            truncated = total > self._max_entries
            entries: list[dict[str, object]] = []
            for entry in matches[: self._max_entries]:
                try:
                    size = entry.stat().st_size if entry.is_file() else 0
                except OSError:
                    size = 0
                entries.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "is_dir": entry.is_dir(),
                        "size_bytes": size,
                    }
                )
            return entries, total, truncated

        entries, total, truncated = await asyncio.to_thread(_list)
        return {
            "entries": entries,
            "total": total,
            "truncated": truncated,
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": [],
                },
            },
        }


class PythonEvalTool:
    """Run Python code in a subprocess and return stdout/stderr."""

    def __init__(
        self,
        *,
        timeout_s: float = 30.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self._timeout_s = timeout_s
        self._max_output_bytes = max_output_bytes

    @property
    def name(self) -> str:
        return "python_eval"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a subprocess and return the output. "
            "The code is run via `python -c`, so use print() to produce "
            "output."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "timeout_s": {
                "type": "number",
                "description": "Timeout in seconds (default 30)",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        code = str(kwargs.get("code", ""))
        timeout_s = float(str(kwargs.get("timeout_s", self._timeout_s)))

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.wait()
            return {"error": "Code execution timed out", "return_code": -1}

        return {
            "stdout": stdout_bytes[: self._max_output_bytes].decode(
                errors="replace"
            ),
            "stderr": stderr_bytes[: self._max_output_bytes].decode(
                errors="replace"
            ),
            "return_code": proc.returncode or 0,
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["code"],
                },
            },
        }