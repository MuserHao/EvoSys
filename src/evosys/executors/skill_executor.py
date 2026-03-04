"""Skill executor — invokes a registered skill and returns an Observation."""

from __future__ import annotations

import time

from evosys.core.interfaces import BaseExecutor
from evosys.core.types import Action, Observation
from evosys.skills.registry import SkillRegistry


class SkillExecutor(BaseExecutor):
    """Execute a skill from the registry and return an :class:`Observation`.

    Never raises — errors are always captured in the Observation.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

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
