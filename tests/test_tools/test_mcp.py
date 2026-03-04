"""Tests for MCP integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from evosys.core.tool import Tool
from evosys.tools.mcp import MCPManager, MCPServerConfig, MCPToolWrapper


class TestMCPServerConfig:
    def test_valid_config(self) -> None:
        cfg = MCPServerConfig(name="fs", command="npx", args=["-y", "server-fs"])
        assert cfg.name == "fs"
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "server-fs"]
        assert cfg.env == {}

    def test_with_env(self) -> None:
        cfg = MCPServerConfig(
            name="api", command="node", args=["server.js"], env={"API_KEY": "abc"}
        )
        assert cfg.env == {"API_KEY": "abc"}

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerConfig(name="", command="npx")

    def test_empty_command_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerConfig(name="test", command="")

    def test_serialization_roundtrip(self) -> None:
        cfg = MCPServerConfig(name="s", command="c", args=["a"], env={"k": "v"})
        data = cfg.model_dump_orjson()
        restored = MCPServerConfig.model_validate_orjson(data)
        assert restored == cfg


class TestMCPToolWrapper:
    def test_satisfies_protocol(self) -> None:
        wrapper = MCPToolWrapper(
            tool_name="test",
            tool_description="desc",
            tool_input_schema={"a": {"type": "string"}},
            call_fn=AsyncMock(return_value={"ok": True}),
        )
        assert isinstance(wrapper, Tool)

    def test_name_and_description(self) -> None:
        wrapper = MCPToolWrapper(
            tool_name="my_tool",
            tool_description="A cool tool",
            tool_input_schema={},
            call_fn=AsyncMock(),
        )
        assert wrapper.name == "my_tool"
        assert wrapper.description == "A cool tool"

    def test_parameters_schema(self) -> None:
        schema = {"path": {"type": "string"}}
        wrapper = MCPToolWrapper(
            tool_name="t", tool_description="d", tool_input_schema=schema, call_fn=AsyncMock()
        )
        assert wrapper.parameters_schema == {"path": {"type": "string"}}

    def test_parameters_schema_is_copy(self) -> None:
        schema = {"a": {"type": "string"}}
        wrapper = MCPToolWrapper(
            tool_name="t", tool_description="d", tool_input_schema=schema, call_fn=AsyncMock()
        )
        result = wrapper.parameters_schema
        result["b"] = {"type": "int"}
        assert "b" not in wrapper.parameters_schema

    def test_to_openai_tool_format(self) -> None:
        wrapper = MCPToolWrapper(
            tool_name="tool",
            tool_description="desc",
            tool_input_schema={"x": {"type": "number"}},
            call_fn=AsyncMock(),
        )
        fmt = wrapper.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "tool"
        assert fn["description"] == "desc"

    async def test_call_success(self) -> None:
        async def fake_call(name, args):
            return {"result": "hello"}

        wrapper = MCPToolWrapper(
            tool_name="t", tool_description="d", tool_input_schema={}, call_fn=fake_call
        )
        result = await wrapper(a="b")
        assert result == {"result": "hello"}

    async def test_call_returns_string_result(self) -> None:
        async def fake_call(name, args):
            return "plain text"

        wrapper = MCPToolWrapper(
            tool_name="t", tool_description="d", tool_input_schema={}, call_fn=fake_call
        )
        result = await wrapper()
        assert result == {"result": "plain text"}

    async def test_call_error(self) -> None:
        async def failing_call(name, args):
            raise RuntimeError("connection lost")

        wrapper = MCPToolWrapper(
            tool_name="t", tool_description="d", tool_input_schema={}, call_fn=failing_call
        )
        result = await wrapper()
        assert "error" in result
        assert "connection lost" in result["error"]


class TestMCPManager:
    def test_initial_state(self) -> None:
        mgr = MCPManager()
        assert mgr.connected_servers == []
        assert mgr.list_tools() == []

    async def test_connect_missing_mcp_package(self) -> None:
        mgr = MCPManager()
        cfg = MCPServerConfig(name="test", command="npx", args=["server"])
        with patch.dict("sys.modules", {"mcp": None}):
            # Will fail to import mcp and return empty list
            tools = await mgr.connect(cfg)
            assert tools == []

    async def test_disconnect_nonexistent(self) -> None:
        mgr = MCPManager()
        await mgr.disconnect("nonexistent")  # should not raise

    async def test_disconnect_all_empty(self) -> None:
        mgr = MCPManager()
        await mgr.disconnect_all()  # should not raise

    async def test_connect_already_connected(self) -> None:
        mgr = MCPManager()
        # Manually inject a fake connection
        fake_tool = MCPToolWrapper("t", "d", {}, AsyncMock())
        from evosys.tools.mcp import _MCPConnection

        mgr._connections["test"] = _MCPConnection(
            config=MCPServerConfig(name="test", command="echo"),
            ctx_manager=MagicMock(),
            session=MagicMock(),
            tools=[fake_tool],
        )
        cfg = MCPServerConfig(name="test", command="echo")
        result = await mgr.connect(cfg)
        assert len(result) == 1
        assert result[0].name == "t"

    async def test_list_tools_from_connections(self) -> None:
        mgr = MCPManager()
        from evosys.tools.mcp import _MCPConnection

        t1 = MCPToolWrapper("tool1", "d1", {}, AsyncMock())
        t2 = MCPToolWrapper("tool2", "d2", {}, AsyncMock())

        mgr._connections["s1"] = _MCPConnection(
            config=MCPServerConfig(name="s1", command="c"),
            ctx_manager=MagicMock(),
            session=MagicMock(),
            tools=[t1],
        )
        mgr._connections["s2"] = _MCPConnection(
            config=MCPServerConfig(name="s2", command="c"),
            ctx_manager=MagicMock(),
            session=MagicMock(),
            tools=[t2],
        )
        tools = mgr.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"tool1", "tool2"}

    async def test_disconnect_calls_cleanup(self) -> None:
        mgr = MCPManager()
        from evosys.tools.mcp import _MCPConnection

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()

        mgr._connections["test"] = _MCPConnection(
            config=MCPServerConfig(name="test", command="c"),
            ctx_manager=mock_ctx,
            session=mock_session,
            tools=[],
        )
        await mgr.disconnect("test")
        assert "test" not in mgr._connections
        mock_session.__aexit__.assert_called_once()
        mock_ctx.__aexit__.assert_called_once()

    async def test_connected_servers(self) -> None:
        mgr = MCPManager()
        from evosys.tools.mcp import _MCPConnection

        mgr._connections["a"] = _MCPConnection(
            config=MCPServerConfig(name="a", command="c"),
            ctx_manager=MagicMock(),
            session=MagicMock(),
            tools=[],
        )
        mgr._connections["b"] = _MCPConnection(
            config=MCPServerConfig(name="b", command="c"),
            ctx_manager=MagicMock(),
            session=MagicMock(),
            tools=[],
        )
        assert set(mgr.connected_servers) == {"a", "b"}
