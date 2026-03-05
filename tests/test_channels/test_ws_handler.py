"""Tests for WebSocket chat handler and streaming agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from evosys.channels.web.frames import ChatRequest, ChatResponse, ErrorFrame, StreamEvent
from evosys.channels.web.streaming_agent import StreamingAgent


class TestFrameModels:
    def test_chat_request_defaults(self) -> None:
        req = ChatRequest(text="hello")
        assert req.type == "message"
        assert req.session_id is None

    def test_chat_response(self) -> None:
        resp = ChatResponse(text="hi", session_id="s1")
        assert resp.done is True
        data = resp.model_dump()
        assert data["type"] == "message"

    def test_stream_event(self) -> None:
        evt = StreamEvent(data={"status": "started"}, session_id="s1")
        assert evt.type == "stream"

    def test_error_frame(self) -> None:
        err = ErrorFrame(error="something broke", session_id="s1")
        assert err.type == "error"

    def test_serialization_roundtrip(self) -> None:
        req = ChatRequest(text="test", session_id="abc")
        json_str = req.model_dump_json()
        parsed = ChatRequest.model_validate_json(json_str)
        assert parsed.text == "test"
        assert parsed.session_id == "abc"


class TestStreamingAgent:
    async def test_yields_start_and_response(self) -> None:
        mock_agent = AsyncMock()
        result = MagicMock()
        result.answer = "42"
        result.tool_calls_made = []
        result.tool_results = []
        result.total_tokens = 50
        result.iterations = 1
        result.session_id = "sid"
        mock_agent.run = AsyncMock(return_value=result)

        streaming = StreamingAgent(mock_agent)
        frames = []
        async for frame_json in streaming.run_streaming("What is 6*7?"):
            frames.append(frame_json)

        assert len(frames) >= 2  # start event + final response
        # First frame should be a start event
        assert '"started"' in frames[0]
        # Last frame should contain the answer
        assert "42" in frames[-1]

    async def test_error_yields_error_frame(self) -> None:
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("kaboom"))

        streaming = StreamingAgent(mock_agent)
        frames = []
        async for frame_json in streaming.run_streaming("fail"):
            frames.append(frame_json)

        # Should have start + error
        assert any("kaboom" in f for f in frames)
