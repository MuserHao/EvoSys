"""Composite forge — generates chained skills from tool-call sequences.

When the SequenceDetector identifies recurring tool-call patterns like
A → B → C, the CompositeForge creates a single composite skill that
chains the individual tools. Future requests can invoke the composite
skill directly (~$0, ~0ms) instead of repeating the full agent loop.
"""

from __future__ import annotations

import structlog

from evosys.core.interfaces import BaseSkill
from evosys.reflection.sequence_detector import SequenceCandidate
from evosys.schemas._types import ImplementationType, MaturationStage, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry

log = structlog.get_logger()


class _CompositeSkill(BaseSkill):
    """A skill that chains multiple tools in sequence."""

    def __init__(
        self,
        tool_names: list[str],
        tool_registry: ToolRegistry,
    ) -> None:
        self._tool_names = tool_names
        self._tool_registry = tool_registry

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        """Execute tools in sequence, feeding each output to the next."""
        current_data = dict(input_data)
        for tool_name in self._tool_names:
            tool = self._tool_registry.get_tool(tool_name)
            if tool is None:
                return {"error": f"Tool not found: {tool_name}"}
            result = await tool(**current_data)
            if "error" in result and len(result) == 1:
                return result
            # Merge result into current data for the next tool
            current_data.update(result)
        return current_data

    def validate(self) -> bool:
        """Validate that all tools in the chain are available."""
        return all(
            self._tool_registry.get_tool(name) is not None for name in self._tool_names
        )


class CompositeForge:
    """Forge composite skills from recurring tool-call sequences."""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
    ) -> None:
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry

    async def forge(
        self,
        candidate: SequenceCandidate,
    ) -> SkillRecord | None:
        """Attempt to forge a composite skill from *candidate*.

        Returns the new SkillRecord on success, or None on failure.
        """
        # Derive a skill name from the tool sequence
        tool_names = candidate.tool_sequence
        short_names = [n.removeprefix("tool:") for n in tool_names]
        skill_name = "composite:" + "_".join(short_names)

        # Check if already registered
        if skill_name in self._skill_registry:
            log.info("composite_forge.already_registered", skill_name=skill_name)
            return None

        # Validate all tools exist
        for tool_name in tool_names:
            # Strip the "tool:" prefix to look up in the registry
            lookup_name = tool_name.removeprefix("tool:")
            if self._tool_registry.get_tool(lookup_name) is None:
                log.warning(
                    "composite_forge.missing_tool",
                    tool=lookup_name,
                    skill_name=skill_name,
                )
                return None

        # Build the composite skill using actual lookup names
        lookup_names = [tn.removeprefix("tool:") for tn in tool_names]
        skill = _CompositeSkill(lookup_names, self._tool_registry)
        if not skill.validate():
            log.warning("composite_forge.validation_failed", skill_name=skill_name)
            return None

        # Build the SkillRecord
        description = (
            f"Composite skill chaining: {' -> '.join(short_names)}. "
            f"Detected {candidate.frequency} times across sessions."
        )

        confidence = min(1.0, candidate.frequency / 10.0)

        record = SkillRecord(
            skill_id=new_ulid(),
            name=skill_name,
            description=description,
            implementation_type=ImplementationType.COMPOSITE,
            implementation_path=f"forge:composite:{skill_name}",
            test_suite_path="auto-generated",
            pass_rate=1.0,
            confidence_score=confidence,
            maturation_stage=MaturationStage.SYNTHESIZED,
        )

        try:
            self._skill_registry.register(record, skill)
        except ValueError as exc:
            log.warning("composite_forge.register_failed", error=str(exc))
            return None

        log.info(
            "composite_forge.success",
            skill_name=skill_name,
            sequence=candidate.canonical_form,
            frequency=candidate.frequency,
        )
        return record
