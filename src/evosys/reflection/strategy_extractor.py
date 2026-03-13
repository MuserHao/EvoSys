"""Strategy extractor — extract reusable strategies from expensive sessions.

After Claude Code sessions that involve many steps and/or significant
cost, the StrategyExtractor asks the LLM to identify reusable
strategies and registers them as ``strategy:{name}`` skills.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from evosys.core.interfaces import BaseSkill
from evosys.schemas._types import ImplementationType, MaturationStage, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.schemas.trajectory import TrajectoryRecord

if TYPE_CHECKING:
    from evosys.llm.client import LLMClient
    from evosys.skills.registry import SkillRegistry
    from evosys.storage.skill_store import SkillStore

log = structlog.get_logger()

_SYSTEM_PROMPT = """\
You are an expert at identifying reusable strategies from agent session logs.
Given a summary of an agent's actions, extract ONE concrete, reusable strategy
that could help future sessions with similar tasks.

Respond with valid JSON:
{
  "name": "short_snake_case_name",
  "description": "1-2 sentence description of when and how to apply this strategy",
  "prompt_template": "The instruction/prompt that implements this strategy"
}

If no clear strategy can be extracted, respond with: {"skip": true}
"""


class _StrategySkill(BaseSkill):
    """A strategy skill that delegates to the LLM with a specific prompt."""

    def __init__(self, prompt_template: str, llm: LLMClient) -> None:
        self._prompt_template = prompt_template
        self._llm = llm

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        """Execute the strategy by sending prompt + input to the LLM."""
        task = str(input_data.get("task", ""))
        messages = [
            {"role": "system", "content": self._prompt_template},
            {"role": "user", "content": task[:5000]},
        ]
        resp = await self._llm.complete(messages)
        return {"result": resp.content, "tokens": resp.total_tokens}

    def validate(self) -> bool:
        return bool(self._prompt_template)


class StrategyExtractor:
    """Extract reusable strategies from expensive agent sessions."""

    def __init__(
        self,
        llm: LLMClient,
        skill_registry: SkillRegistry,
        *,
        skill_store: SkillStore | None = None,
        min_steps: int = 5,
        min_cost_usd: float = 0.01,
    ) -> None:
        self._llm = llm
        self._registry = skill_registry
        self._skill_store = skill_store
        self._min_steps = min_steps
        self._min_cost_usd = min_cost_usd

    async def extract_from_session(
        self,
        records: list[TrajectoryRecord],
        total_cost_usd: float,
    ) -> SkillRecord | None:
        """Analyze session records and extract a strategy if warranted.

        Gates on *min_steps* and *min_cost_usd* to avoid wasting
        LLM calls on trivial sessions.
        """
        if len(records) < self._min_steps:
            return None
        if total_cost_usd < self._min_cost_usd:
            return None

        summary = self._format_session(records)

        try:
            resp = await self._llm.complete(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": summary},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content)
        except Exception as exc:
            log.warning("strategy_extractor.llm_failed", error=str(exc))
            return None

        if data.get("skip"):
            return None

        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        prompt_template = str(data.get("prompt_template", "")).strip()

        if not name or not description or not prompt_template:
            return None

        skill_name = f"strategy:{name}"

        # Prevent duplicates
        if skill_name in self._registry:
            log.info("strategy_extractor.duplicate", skill_name=skill_name)
            return None

        skill = _StrategySkill(prompt_template, self._llm)
        record = SkillRecord(
            skill_id=new_ulid(),
            name=skill_name,
            description=description,
            implementation_type=ImplementationType.AGENT_DELEGATION,
            implementation_path=f"forge:strategy:{name}",
            test_suite_path="auto-generated",
            pass_rate=1.0,
            confidence_score=0.5,
            maturation_stage=MaturationStage.SYNTHESIZED,
        )

        try:
            self._registry.register(record, skill)
        except ValueError as exc:
            log.warning(
                "strategy_extractor.register_failed", error=str(exc)
            )
            return None

        # Persist to DB so the strategy survives restarts
        if self._skill_store is not None:
            try:
                await self._skill_store.save(record, prompt_template)
                log.info(
                    "strategy_extractor.persisted",
                    skill_name=skill_name,
                )
            except Exception:
                log.warning(
                    "strategy_extractor.persist_failed",
                    skill_name=skill_name,
                )

        log.info(
            "strategy_extractor.extracted",
            skill_name=skill_name,
            description=description[:100],
        )
        return record

    def _format_session(
        self, records: list[TrajectoryRecord]
    ) -> str:
        """Format trajectory records into a readable summary."""
        lines = [f"Session with {len(records)} steps:\n"]
        for i, rec in enumerate(records[:20]):
            status = "OK" if rec.success else "FAILED"
            lines.append(
                f"  Step {i + 1}: [{status}] {rec.action_name}"
                f" — {rec.context_summary[:100]}"
            )
        if len(records) > 20:
            lines.append(f"  ... ({len(records) - 20} more steps)")
        return "\n".join(lines)
