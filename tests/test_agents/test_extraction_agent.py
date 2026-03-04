"""Tests for ExtractionAgent (all deps mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from evosys.agents.extraction_agent import ExtractionAgent, ExtractionError, ExtractionResult
from evosys.core.types import Observation
from evosys.executors.http_executor import HttpExecutor
from evosys.llm.client import LLMClient, LLMError, LLMResponse
from evosys.trajectory.logger import TrajectoryLogger


def _mock_llm_response(
    content: str = '{"name": "Test"}',
    total_tokens: int = 50,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        prompt_tokens=20,
        completion_tokens=30,
        total_tokens=total_tokens,
        model="test-model",
    )


@pytest.fixture()
def mock_llm() -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.extract_json = AsyncMock(return_value=_mock_llm_response())
    return client


@pytest.fixture()
def mock_http() -> HttpExecutor:
    executor = AsyncMock(spec=HttpExecutor)
    executor.execute = AsyncMock(
        return_value=Observation(
            action_id=ULID(),
            success=True,
            result={
                "html": "<html>test</html>",
                "status_code": 200,
                "content_type": "text/html",
                "url": "https://example.com",
            },
            latency_ms=100.0,
        )
    )
    return executor


@pytest.fixture()
def mock_logger(trajectory_logger: TrajectoryLogger) -> TrajectoryLogger:
    return trajectory_logger


class TestSuccessfulExtraction:
    async def test_returns_extraction_result(
        self, mock_llm: LLMClient, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        agent = ExtractionAgent(mock_llm, mock_http, mock_logger)
        result = await agent.extract(
            url="https://example.com",
            target_schema='{"name": "string"}',
        )
        assert isinstance(result, ExtractionResult)
        assert result.data == {"name": "Test"}
        assert result.url == "https://example.com"

    async def test_token_cost_accumulated(
        self, mock_llm: LLMClient, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        agent = ExtractionAgent(mock_llm, mock_http, mock_logger)
        result = await agent.extract(
            url="https://example.com",
            target_schema='{"name": "string"}',
        )
        assert result.token_cost == 50

    async def test_session_id_set(
        self, mock_llm: LLMClient, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        agent = ExtractionAgent(mock_llm, mock_http, mock_logger)
        result = await agent.extract(
            url="https://example.com",
            target_schema="{}",
        )
        assert result.session_id == str(mock_logger.session_id)


class TestFetchFailure:
    async def test_raises_extraction_error(
        self, mock_llm: LLMClient, mock_logger: TrajectoryLogger
    ):
        http = AsyncMock(spec=HttpExecutor)
        http.execute = AsyncMock(
            return_value=Observation(
                action_id=ULID(),
                success=False,
                error="Connection refused",
            )
        )
        agent = ExtractionAgent(mock_llm, http, mock_logger)
        with pytest.raises(ExtractionError, match="Fetch failed"):
            await agent.extract(url="https://bad.com", target_schema="{}")


class TestLLMFailure:
    async def test_raises_extraction_error(
        self, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        llm = AsyncMock(spec=LLMClient)
        llm.extract_json = AsyncMock(side_effect=LLMError("rate limited"))
        agent = ExtractionAgent(llm, mock_http, mock_logger)
        with pytest.raises(ExtractionError, match="LLM failed"):
            await agent.extract(url="https://example.com", target_schema="{}")


class TestInvalidJson:
    async def test_raises_extraction_error(
        self, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        llm = AsyncMock(spec=LLMClient)
        llm.extract_json = AsyncMock(
            return_value=_mock_llm_response(content="not valid json {{{")
        )
        agent = ExtractionAgent(llm, mock_http, mock_logger)
        with pytest.raises(ExtractionError, match="Invalid JSON"):
            await agent.extract(url="https://example.com", target_schema="{}")


class TestTrajectoryLogging:
    async def test_two_records_on_success(
        self, mock_llm: LLMClient, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        agent = ExtractionAgent(mock_llm, mock_http, mock_logger)
        await agent.extract(url="https://example.com", target_schema="{}")
        # Logger should have been called twice (fetch + extract)
        assert mock_logger._iteration == 2

    async def test_trajectory_logged_on_fetch_failure(
        self, mock_llm: LLMClient, mock_logger: TrajectoryLogger
    ):
        http = AsyncMock(spec=HttpExecutor)
        http.execute = AsyncMock(
            return_value=Observation(
                action_id=ULID(),
                success=False,
                error="Connection refused",
            )
        )
        agent = ExtractionAgent(mock_llm, http, mock_logger)
        with pytest.raises(ExtractionError):
            await agent.extract(url="https://bad.com", target_schema="{}")
        # Fetch trajectory should still be logged
        assert mock_logger._iteration == 1

    async def test_trajectory_logged_on_llm_failure(
        self, mock_http: HttpExecutor, mock_logger: TrajectoryLogger
    ):
        llm = AsyncMock(spec=LLMClient)
        llm.extract_json = AsyncMock(side_effect=LLMError("boom"))
        agent = ExtractionAgent(llm, mock_http, mock_logger)
        with pytest.raises(ExtractionError):
            await agent.extract(url="https://example.com", target_schema="{}")
        # Both fetch and failed extract should be logged
        assert mock_logger._iteration == 2
