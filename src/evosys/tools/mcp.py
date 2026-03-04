"""MCP (Model Context Protocol) integration.

Connects to external MCP servers and wraps their tools so the agent
can use them alongside built-in tools and skills.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import Field

from evosys.schemas._types import EvoBaseModel

log = structlog.get_logger()


class MCPServerConfig(EvoBaseModel):
    """Configuration for connecting to an MCP server."""

    name: str = Field(min_length=1)
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPToolWrapper:
    """Wraps an MCP tool so it satisfies the EvoSys Tool protocol."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_input_schema: dict[str, object],
        call_fn: Any,
    ) -> None:
        self._name = tool_name
        self._description = tool_description
        self._input_schema = tool_input_schema
        self._call_fn = call_fn

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters_schema(self) -> dict[str, object]:
        return dict(self._input_schema)

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        try:
            result = await self._call_fn(self._name, kwargs)
            if isinstance(result, dict):
                return result
            return {"result": str(result)}
        except Exception as exc:
            return {"error": str(exc)}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": self._input_schema,
                },
            },
        }


class MCPManager:
    """Manages connections to MCP servers and provides their tools.

    Uses the ``mcp`` package for stdio-based server communication.
    """

    def __init__(self) -> None:
        self._connections: dict[str, _MCPConnection] = {}

    async def connect(self, config: MCPServerConfig) -> list[MCPToolWrapper]:
        """Connect to an MCP server and return its tools as wrappers."""
        if config.name in self._connections:
            log.warning("mcp.already_connected", server=config.name)
            return self._connections[config.name].tools

        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore[import-not-found]
            from mcp.client.stdio import stdio_client  # type: ignore[import-not-found]
        except ImportError:
            log.error(
                "mcp.import_error",
                msg="Install the 'mcp' package: pip install mcp",
            )
            return []

        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env or None,
        )

        try:
            ctx_manager = stdio_client(server_params)
            transport = await ctx_manager.__aenter__()
            read_stream, write_stream = transport
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            # List available tools
            tools_response = await session.list_tools()
            wrappers: list[MCPToolWrapper] = []

            for mcp_tool in tools_response.tools:
                tool_schema = (
                    mcp_tool.inputSchema
                    if hasattr(mcp_tool, "inputSchema")
                    else {}
                )
                properties = (
                    tool_schema.get("properties", {})
                    if isinstance(tool_schema, dict)
                    else {}
                )

                async def _call_tool(
                    name: str,
                    args: dict[str, object],
                    _session: ClientSession = session,
                ) -> dict[str, object]:
                    result = await _session.call_tool(name, arguments=args)
                    # Extract text content from the result
                    if hasattr(result, "content") and result.content:
                        texts = []
                        for item in result.content:
                            if hasattr(item, "text"):
                                texts.append(item.text)
                        return {"result": "\n".join(texts)}
                    return {"result": str(result)}

                wrapper = MCPToolWrapper(
                    tool_name=mcp_tool.name,
                    tool_description=mcp_tool.description or "",
                    tool_input_schema=properties,
                    call_fn=_call_tool,
                )
                wrappers.append(wrapper)

            conn = _MCPConnection(
                config=config,
                ctx_manager=ctx_manager,
                session=session,
                tools=wrappers,
            )
            self._connections[config.name] = conn

            log.info(
                "mcp.connected",
                server=config.name,
                tools=len(wrappers),
            )
            return wrappers

        except Exception as exc:
            log.error("mcp.connect_failed", server=config.name, error=str(exc))
            return []

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from a specific MCP server."""
        conn = self._connections.pop(server_name, None)
        if conn is None:
            return
        try:
            await conn.session.__aexit__(None, None, None)
            await conn.ctx_manager.__aexit__(None, None, None)
        except Exception:
            log.exception("mcp.disconnect_error", server=server_name)

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        names = list(self._connections.keys())
        for name in names:
            await self.disconnect(name)

    def list_tools(self) -> list[MCPToolWrapper]:
        """Return all tools from all connected servers."""
        tools: list[MCPToolWrapper] = []
        for conn in self._connections.values():
            tools.extend(conn.tools)
        return tools

    @property
    def connected_servers(self) -> list[str]:
        return list(self._connections.keys())


class _MCPConnection:
    """Internal: tracks a live MCP server connection."""

    def __init__(
        self,
        config: MCPServerConfig,
        ctx_manager: Any,
        session: Any,
        tools: list[MCPToolWrapper],
    ) -> None:
        self.config = config
        self.ctx_manager = ctx_manager
        self.session = session
        self.tools = tools
