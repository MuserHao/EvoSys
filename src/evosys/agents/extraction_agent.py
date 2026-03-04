"""End-to-end extraction agent: URL + schema -> structured JSON."""

from __future__ import annotations

import time
from dataclasses import dataclass

import orjson

from evosys.core.types import Action
from evosys.executors.http_executor import HttpExecutor
from evosys.llm.client import LLMClient, LLMError
from evosys.orchestration.extraction_orchestrator import ExtractionOrchestrator
from evosys.trajectory.logger import TrajectoryLogger

_DEFAULT_SYSTEM_PROMPT = (
    "You are a precise data extraction assistant. "
    "Extract the requested information from the provided HTML content "
    "and return it as a JSON object matching the target schema. "
    "Only return valid JSON, no commentary."
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Successful extraction output."""

    data: dict[str, object]
    url: str
    token_cost: int
    total_latency_ms: float
    session_id: str


class ExtractionError(Exception):
    """Raised when the extraction pipeline fails."""


class ExtractionAgent:
    """Orchestrates fetch -> LLM extract -> JSON parse with trajectory logging."""

    def __init__(
        self,
        llm: LLMClient,
        http: HttpExecutor,
        trajectory_logger: TrajectoryLogger,
        orchestrator: ExtractionOrchestrator | None = None,
    ) -> None:
        self._llm = llm
        self._http = http
        self._logger = trajectory_logger
        self._orchestrator = orchestrator or ExtractionOrchestrator()

    async def extract(
        self,
        *,
        url: str,
        target_schema: str,
        system_prompt: str | None = None,
    ) -> ExtractionResult:
        """Run the full extraction pipeline and return structured data."""
        t0 = time.monotonic()
        total_tokens = 0
        prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

        # --- Plan ---
        plan = await self._orchestrator.plan(f"Extract from {url}")
        fetch_action = plan.actions[0]
        extract_action = plan.actions[1]

        # --- Fetch ---
        fetch_with_params = Action(
            action_id=fetch_action.action_id,
            name=fetch_action.name,
            params={"url": url},
        )
        obs = await self._http.execute(fetch_with_params)

        await self._logger.log(
            action_name="fetch_url",
            context_summary=f"Fetch HTML from {url}",
            action_params={"url": url},
            action_result=dict(obs.result) if obs.success else {"error": obs.error},
            latency_ms=obs.latency_ms,
        )

        if not obs.success:
            raise ExtractionError(f"Fetch failed: {obs.error}")

        html = str(obs.result.get("html", ""))

        # --- LLM Extract ---
        try:
            llm_t0 = time.monotonic()
            llm_resp = await self._llm.extract_json(
                system_prompt=prompt,
                user_content=html,
                target_schema_description=target_schema,
            )
            llm_latency = (time.monotonic() - llm_t0) * 1000
            total_tokens += llm_resp.total_tokens
        except LLMError as exc:
            await self._logger.log(
                action_name="llm_extract",
                context_summary=f"LLM extraction from {url}",
                action_params={"target_schema": target_schema},
                action_result={"error": str(exc)},
            )
            raise ExtractionError(f"LLM failed: {exc}") from exc

        # --- Parse JSON ---
        try:
            data: dict[str, object] = orjson.loads(llm_resp.content)
        except Exception as exc:
            await self._logger.log(
                action_name="llm_extract",
                context_summary=f"LLM extraction from {url}",
                action_params={"target_schema": target_schema},
                action_result={"error": f"Invalid JSON: {exc}", "raw": llm_resp.content},
                token_cost=llm_resp.total_tokens,
                latency_ms=llm_latency,
            )
            raise ExtractionError(f"Invalid JSON from LLM: {exc}") from exc

        await self._logger.log(
            action_name="llm_extract",
            context_summary=f"LLM extraction from {url}",
            action_params={"target_schema": target_schema},
            action_result=data,
            token_cost=llm_resp.total_tokens,
            latency_ms=llm_latency,
            llm_reasoning=extract_action.name,
        )

        total_latency = (time.monotonic() - t0) * 1000
        return ExtractionResult(
            data=data,
            url=url,
            token_cost=total_tokens,
            total_latency_ms=total_latency,
            session_id=str(self._logger.session_id),
        )
