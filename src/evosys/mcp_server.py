"""EvoSys MCP server — expose skills to external agents.

Runs as a stdio-based MCP server that any MCP-compatible client
(Claude Code, Cursor, etc.) can connect to. Each skill invocation
flows through SkillExecutor and logs a trajectory, so the evolution
loop learns from external agent usage automatically.

Usage in Claude Code's settings.json:
  {
    "mcpServers": {
      "evosys": {
        "command": "evosys",
        "args": ["mcp-serve"]
      }
    }
  }
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import structlog

log = structlog.get_logger()


async def run_mcp_server(db_url: str = "") -> None:
    """Start the MCP server on stdin/stdout.

    Reads JSON-RPC messages from stdin, dispatches to the appropriate
    handler, and writes responses to stdout.
    """
    from evosys.bootstrap import bootstrap
    from evosys.config import EvoSysConfig

    cfg = EvoSysConfig(db_url=db_url) if db_url else EvoSysConfig.from_env()
    runtime = await bootstrap(cfg)

    log.info("mcp_server.started", skills=len(list(runtime.skill_registry.list_all())))

    try:
        await _stdio_loop(runtime)
    finally:
        await runtime.shutdown()


async def _stdio_loop(runtime: Any) -> None:
    """Read JSON-RPC from stdin, dispatch, write to stdout."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: protocol, sys.stdin.buffer
    )

    while True:
        line = await reader.readline()
        if not line:
            break
        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue

        try:
            request = json.loads(line_str)
        except json.JSONDecodeError:
            _write_error(None, -32700, "Parse error")
            continue

        req_id = request.get("id")
        method = request.get("method", "")

        if method == "initialize":
            _write_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "evosys",
                    "version": "0.1.0",
                },
            })
        elif method == "notifications/initialized":
            pass  # no response needed for notifications
        elif method == "tools/list":
            tools = _build_tool_list(runtime)
            _write_response(req_id, {"tools": tools})
        elif method == "tools/call":
            params = request.get("params", {})
            result = await _handle_tool_call(runtime, params)
            _write_response(req_id, result)
        elif method == "ping":
            _write_response(req_id, {})
        else:
            _write_error(req_id, -32601, f"Method not found: {method}")


def _skill_name_to_mcp(name: str) -> str:
    """Encode a skill name for MCP (reversible)."""
    return "evosys_" + name.replace(".", "--dot--").replace(":", "--c--")


def _mcp_to_skill_name(mcp_name: str) -> str:
    """Decode an MCP tool name back to a skill name."""
    stripped = mcp_name.removeprefix("evosys_")
    return stripped.replace("--c--", ":").replace("--dot--", ".")


def _build_tool_list(runtime: Any) -> list[dict[str, Any]]:
    """Build the MCP tools list from registered skills + built-in tools."""
    tools: list[dict[str, Any]] = []

    # Expose all active skills as MCP tools
    for entry in runtime.skill_registry.list_active():
        record = entry.record
        input_schema = dict(record.input_schema) if record.input_schema else {}
        tools.append({
            "name": _skill_name_to_mcp(record.name),
            "description": (
                f"[EvoSys skill] {record.description} "
                f"(confidence: {record.confidence_score:.2f})"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    k: {"type": "string", "description": str(v)}
                    for k, v in input_schema.items()
                } if input_schema else {
                    "input": {
                        "type": "string",
                        "description": "Input data for the skill",
                    },
                },
            },
        })

    # Expose core tools: extract, web_fetch, remember, recall
    tools.append({
        "name": "evosys_extract",
        "description": (
            "Extract structured data from a URL. Routes to a forged "
            "skill if available, otherwise falls back to LLM extraction."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to extract data from",
                },
                "schema_description": {
                    "type": "string",
                    "description": "Description of desired output schema",
                },
            },
            "required": ["url"],
        },
    })

    tools.append({
        "name": "evosys_remember",
        "description": "Store a value in EvoSys's persistent memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key"},
                "value": {"type": "string", "description": "Value to store"},
            },
            "required": ["key", "value"],
        },
    })

    tools.append({
        "name": "evosys_recall",
        "description": "Retrieve a value from EvoSys's persistent memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key"},
            },
            "required": ["key"],
        },
    })

    tools.append({
        "name": "evosys_skills",
        "description": "List all available EvoSys skills and their status.",
        "inputSchema": {"type": "object", "properties": {}},
    })

    return tools


async def _handle_tool_call(
    runtime: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Dispatch an MCP tools/call request to the appropriate handler."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name == "evosys_extract":
        return await _call_extract(runtime, arguments)
    elif tool_name == "evosys_remember":
        return await _call_remember(runtime, arguments)
    elif tool_name == "evosys_recall":
        return await _call_recall(runtime, arguments)
    elif tool_name == "evosys_skills":
        return _call_skills_list(runtime)
    elif tool_name.startswith("evosys_"):
        return await _call_skill(runtime, tool_name, arguments)
    else:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True,
        }


async def _call_extract(
    runtime: Any, args: dict[str, Any]
) -> dict[str, Any]:
    """Handle evosys_extract — routes through the full extraction pipeline."""
    url = str(args.get("url", ""))
    schema = str(args.get("schema_description", ""))
    if not url:
        return {
            "content": [{"type": "text", "text": "Error: url is required"}],
            "isError": True,
        }
    try:
        result = await runtime.extraction_agent.extract(
            url=url,
            target_schema=schema or "{}",
        )
        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result.data, indent=2, default=str),
            }],
        }
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"Extraction failed: {exc}"}],
            "isError": True,
        }


async def _call_remember(
    runtime: Any, args: dict[str, Any]
) -> dict[str, Any]:
    key = str(args.get("key", ""))
    value = str(args.get("value", ""))
    if not key:
        return {
            "content": [{"type": "text", "text": "Error: key is required"}],
            "isError": True,
        }
    await runtime.memory_store.set(key, value)
    return {"content": [{"type": "text", "text": f"Remembered: {key}"}]}


async def _call_recall(
    runtime: Any, args: dict[str, Any]
) -> dict[str, Any]:
    key = str(args.get("key", ""))
    if not key:
        keys = await runtime.memory_store.list_keys()
        return {
            "content": [{
                "type": "text",
                "text": f"Available keys: {', '.join(keys) or '(none)'}",
            }],
        }
    value = await runtime.memory_store.get(key)
    if value is None:
        return {
            "content": [{"type": "text", "text": f"Key not found: {key}"}],
        }
    return {"content": [{"type": "text", "text": value}]}


def _call_skills_list(runtime: Any) -> dict[str, Any]:
    entries = runtime.skill_registry.list_active()
    lines = []
    for e in sorted(entries, key=lambda x: x.record.name):
        r = e.record
        lines.append(
            f"  {r.name} — {r.status.value} "
            f"(confidence: {r.confidence_score:.2f}, "
            f"invocations: {e.invocation_count})"
        )
    text = f"{len(entries)} active skills:\n" + "\n".join(lines)
    return {"content": [{"type": "text", "text": text}]}


async def _call_skill(
    runtime: Any, mcp_tool_name: str, args: dict[str, Any]
) -> dict[str, Any]:
    """Invoke a specific EvoSys skill by its MCP tool name."""
    skill_name = _mcp_to_skill_name(mcp_tool_name)

    entry = runtime.skill_registry.lookup(skill_name)
    if entry is None:
        return {
            "content": [{
                "type": "text",
                "text": f"Skill not found: {skill_name}",
            }],
            "isError": True,
        }

    try:
        result = await entry.implementation.invoke(dict(args))
        runtime.skill_registry.record_invocation(skill_name)

        # Log to trajectory for evolution loop learning
        await runtime.trajectory_logger.log(
            action_name=f"mcp:{skill_name}",
            context_summary=f"MCP invocation of {skill_name}",
            action_params=args,
            action_result=result,
            skill_used=skill_name,
        )

        return {
            "content": [{
                "type": "text",
                "text": json.dumps(result, indent=2, default=str),
            }],
        }
    except Exception as exc:
        return {
            "content": [{
                "type": "text",
                "text": f"Skill invocation failed: {exc}",
            }],
            "isError": True,
        }


def _write_response(req_id: Any, result: Any) -> None:
    """Write a JSON-RPC response to stdout."""
    msg = json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    })
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _write_error(req_id: Any, code: int, message: str) -> None:
    """Write a JSON-RPC error to stdout."""
    msg = json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    })
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
