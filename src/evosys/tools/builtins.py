"""Built-in tools for the general agent.

These wrap existing EvoSys components (HttpExecutor, ExtractionAgent) so
the agent loop can call them as standard tools.  System tools (shell, file
I/O, Python eval), memory tools, and scheduling tools are provided here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evosys.core.types import Action
from evosys.executors.http_executor import HttpExecutor
from evosys.schemas._types import new_ulid

if TYPE_CHECKING:
    from evosys.storage.memory_store import MemoryStore
    from evosys.storage.schedule_store import ScheduleStore


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
                "fetch_method": str(obs.result.get("fetch_method", "httpx")),
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


# ---------------------------------------------------------------------------
# External action tools — HTTP API calls and email
# ---------------------------------------------------------------------------


class HttpApiTool:
    """Make HTTP requests with custom method, headers, and body.

    Use this to call REST APIs, webhooks, or any HTTP endpoint.
    Supports POST, PUT, PATCH, DELETE (and GET for completeness).
    Returns the response status code and body.

    Examples:
      http_api(method="POST", url="https://api.example.com/items",
               body={"name": "widget"}, headers={"Authorization": "Bearer TOKEN"})
      http_api(method="DELETE", url="https://api.example.com/items/42")
    """

    def __init__(self, timeout_s: float = 30.0) -> None:
        self._timeout_s = timeout_s

    @property
    def name(self) -> str:
        return "http_api"

    @property
    def description(self) -> str:
        return (
            "Make an HTTP request to an API endpoint. Supports POST, PUT, "
            "PATCH, DELETE, GET. Use for sending data to APIs, triggering "
            "webhooks, or interacting with REST services."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "method": {
                "type": "string",
                "description": "HTTP method: GET, POST, PUT, PATCH, DELETE",
            },
            "url": {
                "type": "string",
                "description": "The URL to call",
            },
            "body": {
                "type": "object",
                "description": "Request body (sent as JSON)",
            },
            "headers": {
                "type": "object",
                "description": "Additional HTTP headers",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        import httpx as _httpx

        method = str(kwargs.get("method", "POST")).upper()
        url = str(kwargs.get("url", ""))
        body = kwargs.get("body")
        headers = kwargs.get("headers")

        if not url:
            return {"error": "url must not be empty"}
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            return {"error": f"Unsupported method: {method}"}

        req_headers: dict[str, str] = {}
        if isinstance(headers, dict):
            req_headers = {str(k): str(v) for k, v in headers.items()}

        try:
            async with _httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.request(
                    method,
                    url,
                    json=body if body is not None else None,
                    headers=req_headers or None,
                    timeout=self._timeout_s,
                )
            # Try to parse response as JSON, fall back to text
            try:
                import json as _json
                response_body: object = _json.loads(resp.text)
            except Exception:
                response_body = resp.text[:10_000]
            return {
                "status_code": resp.status_code,
                "ok": resp.is_success,
                "body": response_body,
                "url": str(resp.url),
            }
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
                    "required": ["method", "url"],
                },
            },
        }


class SendEmailTool:
    """Send an email via SMTP.

    Requires SMTP configuration via environment variables:
      EVOSYS_SMTP_HOST, EVOSYS_SMTP_PORT (default 587)
      EVOSYS_SMTP_USER, EVOSYS_SMTP_PASSWORD
      EVOSYS_SMTP_FROM (sender address)

    Use this to send notifications, alerts, or summaries.
    """

    def __init__(self) -> None:
        import os
        self._host = os.environ.get("EVOSYS_SMTP_HOST", "")
        self._port = int(os.environ.get("EVOSYS_SMTP_PORT", "587"))
        self._user = os.environ.get("EVOSYS_SMTP_USER", "")
        self._password = os.environ.get("EVOSYS_SMTP_PASSWORD", "")
        self._from_addr = os.environ.get("EVOSYS_SMTP_FROM", self._user)

    @property
    def name(self) -> str:
        return "send_email"

    @property
    def description(self) -> str:
        return (
            "Send an email. Use for notifications, alerts, and summaries. "
            "Requires EVOSYS_SMTP_* environment variables to be configured."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "to": {
                "type": "string",
                "description": "Recipient email address",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text)",
            },
        }

    def _is_configured(self) -> bool:
        return bool(self._host and self._user and self._password)

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        if not self._is_configured():
            return {
                "error": (
                    "SMTP not configured. Set EVOSYS_SMTP_HOST, "
                    "EVOSYS_SMTP_USER, EVOSYS_SMTP_PASSWORD environment variables."
                )
            }

        to = str(kwargs.get("to", "")).strip()
        subject = str(kwargs.get("subject", "(no subject)"))
        body = str(kwargs.get("body", ""))

        if not to:
            return {"error": "to must not be empty"}

        import smtplib
        from email.mime.text import MIMEText

        def _send() -> None:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self._from_addr
            msg["To"] = to
            with smtplib.SMTP(self._host, self._port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._user, self._password)
                smtp.sendmail(self._from_addr, [to], msg.as_string())

        try:
            await asyncio.to_thread(_send)
            return {"sent": True, "to": to, "subject": subject}
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
                    "required": ["to", "subject", "body"],
                },
            },
        }


# ---------------------------------------------------------------------------
# Scheduling tools — recurring agent tasks
# ---------------------------------------------------------------------------


class WatchTool:
    """Schedule the agent to run a task repeatedly on an interval.

    Use this when the user wants to be notified about something over time:
    price changes, news updates, stock levels, new job postings, etc.
    The agent will run the task description as a new agent request on
    every tick.  Results are stored and can be retrieved with the
    'inbox' tool.

    Examples:
      watch("Check if the price of Sonos Era 100 on Amazon is below $200",
            interval_hours=6)
      watch("Look for new Python developer jobs in San Francisco on LinkedIn",
            interval_hours=24)
    """

    def __init__(self, schedule_store: ScheduleStore) -> None:
        self._store = schedule_store

    @property
    def name(self) -> str:
        return "watch"

    @property
    def description(self) -> str:
        return (
            "Schedule a task to run repeatedly at a set interval. "
            "The agent will execute the task description on every tick and "
            "store the result. Use 'inbox' to check for updates. "
            "Useful for price tracking, monitoring news, checking availability."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "task": {
                "type": "string",
                "description": "What to check or look for (plain language task description)",
            },
            "interval_hours": {
                "type": "number",
                "description": (
                    "How often to run the task, in hours"
                    " (e.g. 6 for every 6 hours)"
                ),
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task", "")).strip()
        interval_hours = float(str(kwargs.get("interval_hours", 24)))
        if not task:
            return {"error": "task must not be empty"}
        if interval_hours <= 0:
            return {"error": "interval_hours must be positive"}
        interval_seconds = int(interval_hours * 3600)
        task_id = await self._store.create(task, interval_seconds)
        return {
            "task_id": task_id,
            "task": task,
            "interval_hours": interval_hours,
            "status": "scheduled",
            "message": (
                f"Watching every {interval_hours:.0f}h. "
                "Use the 'inbox' tool to check for results."
            ),
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
                    "required": ["task", "interval_hours"],
                },
            },
        }


class InboxTool:
    """Check results from scheduled watch tasks.

    Returns the latest result from each active watch task, or the
    result for a specific task if a task_id is provided.
    """

    def __init__(self, schedule_store: ScheduleStore) -> None:
        self._store = schedule_store

    @property
    def name(self) -> str:
        return "inbox"

    @property
    def description(self) -> str:
        return (
            "Check for results from scheduled watch tasks. "
            "Without arguments, lists all active watches and their latest results. "
            "Pass a task_id to get the latest result for a specific watch."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "task_id": {
                "type": "string",
                "description": "Optional task_id to check a specific watch",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        import orjson

        task_id = str(kwargs.get("task_id", "")).strip()

        if task_id:
            row = await self._store.get(task_id)
            if row is None:
                return {"error": f"No watch task found with id: {task_id}"}
            result = orjson.loads(row.last_result_json) if row.last_result_json else {}
            return {
                "task_id": row.task_id,
                "task": row.description,
                "last_run_at": (
                    row.last_run_at.isoformat() if row.last_run_at else None
                ),
                "next_run_at": row.next_run_at.isoformat(),
                "enabled": row.enabled,
                "result": result,
            }

        rows = await self._store.list_enabled()
        if not rows:
            return {
                "watches": [],
                "count": 0,
                "message": "No active watches. Use 'watch' to set one up.",
            }

        watches = []
        for row in rows:
            result = orjson.loads(row.last_result_json) if row.last_result_json else None
            watches.append({
                "task_id": row.task_id,
                "task": row.description,
                "interval_hours": row.interval_seconds / 3600,
                "last_run_at": (
                    row.last_run_at.isoformat() if row.last_run_at else None
                ),
                "next_run_at": row.next_run_at.isoformat(),
                "has_result": result is not None,
                "latest_answer": (
                    result.get("answer", "")[:200]
                    if isinstance(result, dict) else ""
                ),
            })
        return {"watches": watches, "count": len(watches)}

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


# ---------------------------------------------------------------------------
# Memory tools — cross-session key-value storage
# ---------------------------------------------------------------------------


class RememberTool:
    """Store a value in persistent memory under a named key.

    Memory survives across agent sessions and can be recalled by key.
    Use this to save preferences, tracked items, prior research results,
    or any information the user wants the agent to remember.
    """

    def __init__(self, memory_store: MemoryStore, namespace: str = "default") -> None:
        self._store = memory_store
        self._namespace = namespace

    @property
    def name(self) -> str:
        return "remember"

    @property
    def description(self) -> str:
        return (
            "Save a piece of information to persistent memory under a key. "
            "The agent can recall it in future sessions using the 'recall' tool. "
            "Use this for user preferences, items to track, research findings, "
            "or anything the user wants remembered."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "key": {
                "type": "string",
                "description": (
                    "Short identifier for this memory"
                    " (e.g. 'laptop_budget', 'user_name')"
                ),
            },
            "value": {
                "type": "string",
                "description": "The value to remember",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs.get("key", "")).strip()
        value = str(kwargs.get("value", ""))
        if not key:
            return {"error": "key must not be empty"}
        await self._store.set(key, value, namespace=self._namespace)
        return {"stored": True, "key": key}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["key", "value"],
                },
            },
        }


class RecallTool:
    """Retrieve a previously remembered value by key.

    Returns the value stored with 'remember', or lists all stored keys
    if no key is provided.
    """

    def __init__(self, memory_store: MemoryStore, namespace: str = "default") -> None:
        self._store = memory_store
        self._namespace = namespace

    @property
    def name(self) -> str:
        return "recall"

    @property
    def description(self) -> str:
        return (
            "Retrieve a value from persistent memory by key, or list all "
            "remembered keys if no key is given. Use this to access "
            "previously saved preferences, tracked items, or research findings."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "key": {
                "type": "string",
                "description": "The key to look up. Omit to list all remembered keys.",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs.get("key", "")).strip()
        if not key:
            keys = await self._store.list_keys(namespace=self._namespace)
            return {"keys": keys, "count": len(keys)}
        value = await self._store.get(key, namespace=self._namespace)
        if value is None:
            return {"found": False, "key": key}
        return {"found": True, "key": key, "value": value}

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