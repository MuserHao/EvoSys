"""Channel abstractions — protocol + DTOs for multi-channel messaging.

All channel implementations (Slack, web chat, CLI) implement the
:class:`Channel` protocol and exchange :class:`InboundMessage` /
:class:`OutboundMessage` DTOs with the agent layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """A message received from a user via any channel."""

    text: str
    channel_id: str  # Slack channel, WebSocket session, etc.
    user_id: str
    thread_id: str | None = None  # Slack thread_ts or WS session
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """A message to send back to a user via any channel."""

    text: str
    channel_id: str
    thread_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Channel(Protocol):
    """Structural protocol for messaging channels."""

    @property
    def name(self) -> str:
        """Channel identifier (e.g. 'slack', 'web', 'cli')."""
        ...

    async def start(self) -> None:
        """Start listening for messages."""
        ...

    async def stop(self) -> None:
        """Stop the channel gracefully."""
        ...

    async def send(self, message: OutboundMessage) -> None:
        """Send a message to the channel."""
        ...
