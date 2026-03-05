"""WebSocket chat handler — /ws/chat endpoint.

Accepts WebSocket connections, receives chat messages, runs the
streaming agent, and sends back real-time event frames.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from evosys.channels.web.frames import ChatRequest, ErrorFrame
from evosys.channels.web.streaming_agent import StreamingAgent

if TYPE_CHECKING:
    from evosys.agents.agent import Agent

log = structlog.get_logger()


class WebSocketChatHandler:
    """Manages WebSocket connections for the chat UI.

    Each WebSocket connection is an independent session.  Messages
    are processed sequentially within a connection (one agent run
    at a time per client).

    Parameters
    ----------
    agent:
        The general agent to handle messages.
    """

    def __init__(self, agent: Agent) -> None:
        self._streaming = StreamingAgent(agent)
        self._connections: set[WebSocket] = set()

    async def handle(self, websocket: WebSocket) -> None:
        """Handle a WebSocket connection lifecycle."""
        await websocket.accept()
        self._connections.add(websocket)
        log.info("ws.connected", total=len(self._connections))

        try:
            while True:
                raw = await websocket.receive_text()

                try:
                    req = ChatRequest.model_validate_json(raw)
                except Exception:
                    await websocket.send_text(
                        ErrorFrame(error="Invalid message format").model_dump_json()
                    )
                    continue

                # Stream agent response back
                async for frame_json in self._streaming.run_streaming(
                    req.text, session_id=req.session_id
                ):
                    await websocket.send_text(frame_json)

        except WebSocketDisconnect:
            log.info("ws.disconnected")
        except Exception:
            log.exception("ws.error")
        finally:
            self._connections.discard(websocket)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
