"""WebSocket frame models for the web chat channel."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Inbound WebSocket frame — user sends a message."""

    type: str = "message"
    text: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Outbound WebSocket frame — agent replies."""

    type: str = "message"
    text: str
    session_id: str
    done: bool = True


class StreamEvent(BaseModel):
    """Outbound WebSocket frame — real-time streaming event."""

    type: str = "stream"  # stream, tool_call, tool_result, error, done
    data: dict[str, Any] = {}
    session_id: str = ""


class ErrorFrame(BaseModel):
    """Outbound WebSocket frame — error notification."""

    type: str = "error"
    error: str
    session_id: str = ""
