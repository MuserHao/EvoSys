"""Tests for CLI chat session."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from evosys.channels.cli_chat import CLIChatSession


class TestCLIChatSession:
    def test_init_defaults(self) -> None:
        agent = MagicMock()
        session = CLIChatSession(agent=agent)
        assert session._history == []
        assert session._session_name == ""

    async def test_handle_quit_command(self) -> None:
        agent = MagicMock()
        session = CLIChatSession(agent=agent)
        result = await session._handle_command("/quit")
        assert result is False

    async def test_handle_clear_command(self) -> None:
        agent = MagicMock()
        session = CLIChatSession(agent=agent)
        session._history = [{"role": "user", "content": "hello"}]
        result = await session._handle_command("/clear")
        assert result is True
        assert session._history == []

    async def test_handle_history_command(self) -> None:
        agent = MagicMock()
        session = CLIChatSession(agent=agent)
        session._history = [{"role": "user", "content": "test"}]
        result = await session._handle_command("/history")
        assert result is True

    async def test_handle_unknown_command(self) -> None:
        agent = MagicMock()
        session = CLIChatSession(agent=agent)
        result = await session._handle_command("/unknown")
        assert result is True

    async def test_save_session(self) -> None:
        agent = MagicMock()
        memory = AsyncMock()
        session = CLIChatSession(
            agent=agent,
            memory_store=memory,
            session_name="test-session",
        )
        session._history = [{"role": "user", "content": "hello"}]

        await session._save_session()
        memory.set.assert_called_once()
        call_args = memory.set.call_args
        assert call_args[0][0] == "chat_history"
        assert "hello" in call_args[0][1]

    async def test_load_session(self) -> None:
        agent = MagicMock()
        memory = AsyncMock()
        memory.get = AsyncMock(
            return_value='[{"role": "user", "content": "prior message"}]'
        )
        session = CLIChatSession(
            agent=agent,
            memory_store=memory,
            session_name="test-session",
        )

        await session._load_session()
        assert len(session._history) == 1
        assert session._history[0]["content"] == "prior message"

    async def test_load_session_no_data(self) -> None:
        agent = MagicMock()
        memory = AsyncMock()
        memory.get = AsyncMock(return_value=None)
        session = CLIChatSession(
            agent=agent,
            memory_store=memory,
            session_name="empty",
        )

        await session._load_session()
        assert session._history == []
