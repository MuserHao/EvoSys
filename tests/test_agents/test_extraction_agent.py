"""Tests for ExtractionAgent (all deps mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from evosys.agents.extraction_agent import ExtractionAgent, ExtractionError, ExtractionResult
from evosys.core.interfaces import BaseSkill
from evosys.core.types import Observation
from evosys.executors.http_executor import HttpExecutor
from evosys.executors.skill_executor import SkillExecutor
from evosys.llm.client import LLMClient, LLMError, LLMResponse
from evosys.orchestration.routing_orchestrator import RoutingOrchestrator
from evosys.schemas._types import ImplementationType
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry
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


# ---------------------------------------------------------------------------
# Skill routing tests (Phase 1b)
# ---------------------------------------------------------------------------


class _StubSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return {"extracted": True, "source": str(input_data.get("url", ""))}

    def validate(self) -> bool:
        return True


def _make_skill_record(name: str = "extract:example.com") -> SkillRecord:
    return SkillRecord(
        name=name,
        description="Stub skill",
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="skills/stub.py",
        test_suite_path="tests/test_stub.py",
        confidence_score=0.9,
    )


class TestSkillRouting:
    async def test_skill_routing_returns_result_with_skill_used(
        self,
        mock_llm: LLMClient,
        mock_http: HttpExecutor,
        mock_logger: TrajectoryLogger,
    ):
        reg = SkillRegistry()
        reg.register(_make_skill_record(), _StubSkill())
        routing_orch = RoutingOrchestrator(reg)
        skill_exec = SkillExecutor(reg)

        agent = ExtractionAgent(
            mock_llm, mock_http, mock_logger,
            orchestrator=routing_orch,
            skill_executor=skill_exec,
        )
        result = await agent.extract(
            url="https://example.com/page",
            target_schema="{}",
        )
        assert isinstance(result, ExtractionResult)
        assert result.skill_used == "extract:example.com"
        assert result.data["extracted"] is True
        assert result.token_cost == 0

    async def test_falls_back_to_llm_when_no_skill(
        self,
        mock_llm: LLMClient,
        mock_http: HttpExecutor,
        mock_logger: TrajectoryLogger,
    ):
        reg = SkillRegistry()  # empty registry
        routing_orch = RoutingOrchestrator(reg)
        skill_exec = SkillExecutor(reg)

        agent = ExtractionAgent(
            mock_llm, mock_http, mock_logger,
            orchestrator=routing_orch,
            skill_executor=skill_exec,
        )
        result = await agent.extract(
            url="https://example.com/page",
            target_schema='{"name": "string"}',
        )
        assert isinstance(result, ExtractionResult)
        assert result.skill_used is None
        assert result.data == {"name": "Test"}

    async def test_skill_path_logs_one_trajectory(
        self,
        mock_llm: LLMClient,
        mock_http: HttpExecutor,
        mock_logger: TrajectoryLogger,
    ):
        reg = SkillRegistry()
        reg.register(_make_skill_record(), _StubSkill())
        routing_orch = RoutingOrchestrator(reg)
        skill_exec = SkillExecutor(reg)

        agent = ExtractionAgent(
            mock_llm, mock_http, mock_logger,
            orchestrator=routing_orch,
            skill_executor=skill_exec,
        )
        await agent.extract(url="https://example.com/page", target_schema="{}")
        assert mock_logger._iteration == 1

    async def test_backward_compat_no_skill_executor_uses_llm(
        self,
        mock_llm: LLMClient,
        mock_http: HttpExecutor,
        mock_logger: TrajectoryLogger,
    ):
        """Without skill_executor, agent behaves identically to Phase 1a."""
        agent = ExtractionAgent(mock_llm, mock_http, mock_logger)
        result = await agent.extract(
            url="https://example.com",
            target_schema='{"name": "string"}',
        )
        assert isinstance(result, ExtractionResult)
        assert result.skill_used is None
        assert result.data == {"name": "Test"}
