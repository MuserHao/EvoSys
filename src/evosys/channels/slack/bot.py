"""Slack bot — Socket Mode integration for EvoSys.

Uses slack_bolt's async Socket Mode handler so no public URL is needed.
Each Slack thread maps to a separate agent session.  Messages and
app_mentions both trigger the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from evosys.channels import OutboundMessage
from evosys.channels.slack.formatting import to_slack_mrkdwn
from evosys.channels.slack.threading import resolve_thread_id

if TYPE_CHECKING:
    from evosys.agents.agent import Agent
    from evosys.config import EvoSysConfig

log = structlog.get_logger()


class SlackBot:
    """EvoSys Slack bot using Socket Mode.

    Handles direct messages and @mentions.  Each Slack thread maps to
    a separate agent session for context isolation.

    Parameters
    ----------
    config:
        EvoSys configuration with Slack tokens.
    agent:
        The general agent to handle messages.
    """

    def __init__(self, config: EvoSysConfig, agent: Agent) -> None:
        self._config = config
        self._agent = agent
        self._app: Any = None
        self._handler: Any = None
        self._sessions: dict[str, list[dict[str, str]]] = {}  # thread_id → history

    @property
    def name(self) -> str:
        return "slack"

    async def start(self) -> None:
        """Initialize and start the Slack Socket Mode handler."""
        try:
            from slack_bolt.adapter.socket_mode.async_handler import (
                AsyncSocketModeHandler,
            )
            from slack_bolt.async_app import AsyncApp
        except ImportError:
            log.error(
                "slack.import_failed",
                hint="Install with: uv sync --group slack",
            )
            return

        self._app = AsyncApp(token=self._config.slack_bot_token)

        # Register event handlers
        @self._app.event("message")
        async def handle_message(event: dict[str, Any], say: Any) -> None:
            await self._on_message(event, say)

        @self._app.event("app_mention")
        async def handle_mention(event: dict[str, Any], say: Any) -> None:
            await self._on_message(event, say)

        self._handler = AsyncSocketModeHandler(
            self._app, self._config.slack_app_token
        )
        log.info("slack.starting")
        await self._handler.start_async()
        log.info("slack.started")

    async def stop(self) -> None:
        """Stop the Socket Mode handler."""
        if self._handler is not None:
            await self._handler.close_async()
            log.info("slack.stopped")

    async def send(self, message: OutboundMessage) -> None:
        """Send a message to a Slack channel/thread."""
        if self._app is None:
            return
        kwargs: dict[str, Any] = {
            "channel": message.channel_id,
            "text": to_slack_mrkdwn(message.text),
        }
        if message.thread_id:
            kwargs["thread_ts"] = message.thread_id
        await self._app.client.chat_postMessage(**kwargs)

    async def _on_message(self, event: dict[str, Any], say: Any) -> None:
        """Handle an incoming Slack message or mention."""
        text = event.get("text", "").strip()
        if not text:
            return

        # Ignore bot messages to prevent loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        thread_ts = resolve_thread_id(event, self._config.slack_reply_in_thread)

        log.info(
            "slack.message_received",
            channel=channel_id,
            user=user_id,
            thread=thread_ts,
        )

        try:
            # Build context from thread history
            session_key = thread_ts or f"{channel_id}:{user_id}"
            history = self._sessions.get(session_key, [])

            context: dict[str, object] | None = None
            if history:
                context = {"thread_history": history[-10:]}  # Last 10 messages

            result = await self._agent.run(task=text, context=context)

            # Store in session history
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": result.answer})
            self._sessions[session_key] = history[-20:]  # Cap at 20

            # Reply
            outbound = OutboundMessage(
                text=result.answer,
                channel_id=channel_id,
                thread_id=thread_ts,
            )
            await self.send(outbound)

        except Exception:
            log.exception("slack.handler_error", channel=channel_id)
            error_msg = OutboundMessage(
                text="Sorry, I encountered an error processing your request.",
                channel_id=channel_id,
                thread_id=thread_ts,
            )
            await self.send(error_msg)
