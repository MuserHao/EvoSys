"""Skill executor — invokes a registered skill and returns an Observation."""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

import structlog

from evosys.core.interfaces import BaseExecutor
from evosys.core.types import Action, Observation
from evosys.schemas._types import SkillStatus
from evosys.skills.registry import SkillEntry, SkillRegistry

if TYPE_CHECKING:
    from evosys.llm.client import LLMClient
    from evosys.reflection.shadow_evaluator import ShadowEvaluator
    from evosys.storage.skill_store import SkillStore

log = structlog.get_logger()


class SkillExecutor(BaseExecutor):
    """Execute a skill from the registry and return an :class:`Observation`.

    Never raises — errors are always captured in the Observation.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        *,
        shadow_evaluator: ShadowEvaluator | None = None,
        llm: LLMClient | None = None,
        skill_store: SkillStore | None = None,
    ) -> None:
        self._registry = registry
        self._shadow = shadow_evaluator
        self._llm = llm
        self._skill_store = skill_store

    async def execute(self, action: Action) -> Observation:
        """Execute a skill invocation.

        Expects ``action.params["skill_name"]`` to identify the skill.
        All other params are forwarded as ``input_data``.
        """
        skill_name = action.params.get("skill_name")
        if not skill_name or not isinstance(skill_name, str):
            return Observation(
                action_id=action.action_id,
                success=False,
                error="Missing or invalid 'skill_name' param",
            )

        entry = self._registry.lookup(skill_name)
        if entry is None:
            return Observation(
                action_id=action.action_id,
                success=False,
                error=f"Skill not found: {skill_name!r}",
            )

        input_data: dict[str, object] = {
            k: v for k, v in action.params.items() if k != "skill_name"
        }

        t0 = time.monotonic()
        try:
            result = await entry.implementation.invoke(input_data)
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._registry.record_invocation(skill_name)

            # Fire-and-forget shadow evaluation
            await self._maybe_shadow_evaluate(entry, input_data, result)

            return Observation(
                action_id=action.action_id,
                success=True,
                result=result,
                latency_ms=elapsed_ms,
                token_cost=0,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return Observation(
                action_id=action.action_id,
                success=False,
                error=str(exc),
                latency_ms=elapsed_ms,
                token_cost=0,
            )

    async def _maybe_shadow_evaluate(
        self,
        entry: SkillEntry,
        input_data: dict[str, object],
        skill_result: dict[str, object],
    ) -> None:
        """Probabilistically trigger shadow evaluation based on sample rate."""
        if self._shadow is None or self._llm is None:
            return

        rate = entry.record.shadow_sample_rate
        if rate <= 0 or random.random() > rate:
            return

        # Run shadow comparison in background to avoid blocking the caller
        task = asyncio.create_task(
            self._run_shadow_comparison(entry, input_data, skill_result)
        )
        # prevent task from being garbage-collected
        task.add_done_callback(lambda t: None)

    async def _run_shadow_comparison(
        self,
        entry: SkillEntry,
        input_data: dict[str, object],
        skill_result: dict[str, object],
    ) -> None:
        """Run LLM extraction on the same input and compare via ShadowEvaluator."""
        assert self._shadow is not None
        assert self._llm is not None

        try:
            llm_resp = await self._llm.extract_json(
                system_prompt=(
                    "Extract structured data from the input."
                ),
                user_content=str(input_data)[:5000],
                target_schema_description=str(entry.record.output_schema),
            )
            import json
            llm_output = json.loads(llm_resp.content)
        except Exception:
            log.debug(
                "shadow.llm_extraction_failed",
                skill_name=entry.record.name,
            )
            return

        try:
            comparison = await self._shadow.compare(
                skill_output=skill_result,
                llm_output=llm_output,
                output_schema=dict(entry.record.output_schema),
            )
            self._update_confidence(entry, comparison.agreement)
        except Exception:
            log.debug(
                "shadow.comparison_failed",
                skill_name=entry.record.name,
            )

    def _update_confidence(
        self, entry: SkillEntry, agreement: bool
    ) -> None:
        """Bayesian EMA update of shadow_agreement_rate and confidence_score.

        As shadow agreement accumulates, confidence_score is gradually
        promoted so the skill reaches the routing threshold organically.
        """
        record = entry.record
        alpha = 0.3  # EMA weight for new observation

        current = record.shadow_agreement_rate
        if current is None:
            current = 1.0

        new_rate = alpha * (1.0 if agreement else 0.0) + (1 - alpha) * current
        record.shadow_agreement_rate = round(new_rate, 4)
        record.total_shadow_comparisons += 1

        # --- Confidence promotion ---
        # After enough shadow comparisons with good agreement,
        # promote confidence_score toward 1.0 so the skill reaches
        # the routing threshold (default 0.7) organically.
        if (
            record.total_shadow_comparisons >= 3
            and record.shadow_agreement_rate >= 0.8
        ):
            # Blend confidence toward shadow agreement rate
            conf_alpha = 0.2
            new_conf = (
                conf_alpha * record.shadow_agreement_rate
                + (1 - conf_alpha) * record.confidence_score
            )
            record.confidence_score = round(min(1.0, new_conf), 4)

        # Mark DEGRADED if rate drops below 0.5 after enough samples
        if (
            record.total_shadow_comparisons >= 5
            and record.shadow_agreement_rate < 0.5
        ):
            record.status = SkillStatus.DEGRADED
            log.warning(
                "shadow.skill_degraded",
                skill_name=record.name,
                agreement_rate=record.shadow_agreement_rate,
                comparisons=record.total_shadow_comparisons,
            )

        # Persist updated metrics
        if self._skill_store is not None:
            task = asyncio.create_task(
                self._persist_shadow_update(record)
            )
            task.add_done_callback(lambda t: None)

    async def _persist_shadow_update(self, record: object) -> None:
        """Persist shadow metrics to the DB (fire-and-forget)."""
        assert self._skill_store is not None
        from evosys.schemas.skill import SkillRecord
        if not isinstance(record, SkillRecord):
            return
        try:
            await self._skill_store.update_shadow(
                record.name,
                record.shadow_agreement_rate or 0.0,
                record.total_shadow_comparisons,
            )
        except Exception:
            log.debug(
                "shadow.persist_failed",
                skill_name=record.name,
            )
