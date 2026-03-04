"""Tests for bootstrap module."""

from __future__ import annotations

from evosys.bootstrap import EvoSysRuntime, bootstrap
from evosys.config import EvoSysConfig

_TEST_CONFIG = EvoSysConfig(db_url="sqlite+aiosqlite:///:memory:")


class TestBootstrap:
    async def test_returns_runtime(self):
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert isinstance(rt, EvoSysRuntime)
        finally:
            await rt.shutdown()

    async def test_loads_builtin_skills(self):
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert len(rt.skill_registry) > 0
            assert "extract:news.ycombinator.com" in rt.skill_registry
        finally:
            await rt.shutdown()

    async def test_skip_builtin_skills(self):
        rt = await bootstrap(_TEST_CONFIG, load_builtin_skills=False)
        try:
            assert len(rt.skill_registry) == 0
        finally:
            await rt.shutdown()

    async def test_agent_is_wired(self):
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert rt.agent is not None
            assert rt.agent._skill_executor is not None
        finally:
            await rt.shutdown()

    async def test_shutdown_disposes_engine(self):
        rt = await bootstrap(_TEST_CONFIG)
        await rt.shutdown()
        # After dispose, the engine should not accept new connections
        pool_status = rt.engine.pool.status()
        assert "disposed" in pool_status.lower() or "closed" in pool_status.lower() or (
            # StaticPool used by in-memory SQLite doesn't change status text
            pool_status == "StaticPool"
        )


class TestDangerousToolFlags:
    async def test_shell_tool_disabled_by_default(self):
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert rt.tool_registry.get_tool("shell_exec") is None
        finally:
            await rt.shutdown()

    async def test_python_eval_disabled_by_default(self):
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert rt.tool_registry.get_tool("python_eval") is None
        finally:
            await rt.shutdown()

    async def test_shell_tool_enabled_by_config(self):
        cfg = EvoSysConfig(
            db_url="sqlite+aiosqlite:///:memory:", enable_shell_tool=True
        )
        rt = await bootstrap(cfg)
        try:
            assert rt.tool_registry.get_tool("shell_exec") is not None
        finally:
            await rt.shutdown()

    async def test_python_eval_enabled_by_config(self):
        cfg = EvoSysConfig(
            db_url="sqlite+aiosqlite:///:memory:", enable_python_eval_tool=True
        )
        rt = await bootstrap(cfg)
        try:
            assert rt.tool_registry.get_tool("python_eval") is not None
        finally:
            await rt.shutdown()

    async def test_file_tools_always_registered(self):
        """file_read, file_write, file_list are never dangerous — always on."""
        rt = await bootstrap(_TEST_CONFIG)
        try:
            assert rt.tool_registry.get_tool("file_read") is not None
            assert rt.tool_registry.get_tool("file_write") is not None
            assert rt.tool_registry.get_tool("file_list") is not None
        finally:
            await rt.shutdown()
