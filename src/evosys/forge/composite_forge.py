"""Composite forge — generates chained skills from tool-call sequences.

When the SequenceDetector identifies recurring tool-call patterns like
A → B → C, the CompositeForge creates a single composite skill that
chains the individual tools. Future requests can invoke the composite
skill directly (~$0, ~0ms) instead of repeating the full agent loop.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

import structlog

from evosys.core.interfaces import BaseSkill
from evosys.reflection.sequence_detector import SequenceCandidate
from evosys.schemas._types import ImplementationType, MaturationStage, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry

log = structlog.get_logger()


class OnError(StrEnum):
    """Error-handling policy for a composite step."""

    ABORT = "abort"
    SKIP = "skip"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class CompositeStep:
    """A single step in a branching composite skill."""

    tool_name: str
    on_error: OnError = OnError.ABORT
    max_retries: int = 1
    optional: bool = False
    condition_key: str | None = None
    fallback_tool: str | None = None


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


class _BranchingCompositeSkill(BaseSkill):
    """A composite skill supporting retries, fallbacks, and conditional steps."""

    def __init__(
        self,
        steps: list[CompositeStep],
        tool_registry: ToolRegistry,
    ) -> None:
        self._steps = steps
        self._tool_registry = tool_registry

    async def invoke(
        self, input_data: dict[str, object]
    ) -> dict[str, object]:
        """Execute steps with error handling policies."""
        current_data = dict(input_data)

        for step in self._steps:
            # Check condition
            if step.condition_key and not current_data.get(step.condition_key):
                if step.optional:
                    continue
                return {
                    "error": f"Condition not met: {step.condition_key}",
                }

            # Try the primary tool with retries
            result = await self._try_tool(step.tool_name, current_data, step.max_retries)

            if result is None or ("error" in result and len(result) == 1):
                # Try fallback
                if step.fallback_tool:
                    result = await self._try_tool(
                        step.fallback_tool, current_data, 1
                    )

                if result is None or ("error" in result and len(result) == 1):
                    if step.on_error == OnError.SKIP or step.optional:
                        continue
                    elif step.on_error == OnError.ABORT:
                        return result or {"error": f"Step failed: {step.tool_name}"}
                    # RETRY already exhausted above
                    return result or {"error": f"Step failed: {step.tool_name}"}

            current_data.update(result)

        return current_data

    async def _try_tool(
        self,
        tool_name: str,
        data: dict[str, object],
        max_retries: int,
    ) -> dict[str, object] | None:
        """Try executing a tool up to max_retries times."""
        tool = self._tool_registry.get_tool(tool_name)
        if tool is None:
            return {"error": f"Tool not found: {tool_name}"}

        last_result: dict[str, object] | None = None
        for _ in range(max(1, max_retries)):
            try:
                result = await tool(**data)
                if "error" not in result or len(result) > 1:
                    return result
                last_result = result
            except Exception as exc:
                last_result = {"error": str(exc)}
        return last_result

    def validate(self) -> bool:
        """Validate that primary tools exist (fallbacks checked lazily)."""
        return all(
            self._tool_registry.get_tool(s.tool_name) is not None
            for s in self._steps
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
        # Derive a collision-resistant skill name from the tool sequence.
        # We join short names for readability and append a 6-char hash of the
        # full canonical sequence to prevent collisions when truncation would
        # make two different sequences produce identical strings.
        tool_names = candidate.tool_sequence
        short_names = [n.removeprefix("tool:") for n in tool_names]
        seq_hash = hashlib.sha1(  # sha1 is fine here — non-crypto, just a short ID
            candidate.canonical_form.encode()
        ).hexdigest()[:6]
        skill_name = "composite:" + "_".join(t[:20] for t in short_names)[:80] + f"_{seq_hash}"

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

    async def forge_branching(
        self,
        steps: list[CompositeStep],
        *,
        name_hint: str = "",
        frequency: int = 0,
    ) -> SkillRecord | None:
        """Forge a branching composite skill from explicit steps.

        Returns the new SkillRecord on success, or None on failure.
        """
        tool_names = [s.tool_name for s in steps]
        short_names = [n.removeprefix("tool:") for n in tool_names]
        canonical = " -> ".join(short_names)
        seq_hash = hashlib.sha1(canonical.encode()).hexdigest()[:6]

        skill_name = name_hint or (
            "composite:branching:"
            + "_".join(t[:20] for t in short_names)[:60]
            + f"_{seq_hash}"
        )

        if skill_name in self._skill_registry:
            log.info(
                "composite_forge.branching_exists",
                skill_name=skill_name,
            )
            return None

        # Validate primary tools
        for step in steps:
            lookup = step.tool_name.removeprefix("tool:")
            if self._tool_registry.get_tool(lookup) is None:
                log.warning(
                    "composite_forge.branching_missing_tool",
                    tool=lookup,
                )
                return None

        # Normalize tool names (strip tool: prefix)
        normalized_steps = [
            CompositeStep(
                tool_name=s.tool_name.removeprefix("tool:"),
                on_error=s.on_error,
                max_retries=s.max_retries,
                optional=s.optional,
                condition_key=s.condition_key,
                fallback_tool=(
                    s.fallback_tool.removeprefix("tool:")
                    if s.fallback_tool
                    else None
                ),
            )
            for s in steps
        ]

        skill = _BranchingCompositeSkill(normalized_steps, self._tool_registry)
        if not skill.validate():
            return None

        description = (
            f"Branching composite: {canonical}. "
            f"With error handling and fallbacks."
        )

        record = SkillRecord(
            skill_id=new_ulid(),
            name=skill_name,
            description=description,
            implementation_type=ImplementationType.COMPOSITE,
            implementation_path=f"forge:branching:{skill_name}",
            test_suite_path="auto-generated",
            pass_rate=1.0,
            confidence_score=min(1.0, frequency / 10.0) if frequency else 0.5,
            maturation_stage=MaturationStage.SYNTHESIZED,
        )

        try:
            self._skill_registry.register(record, skill)
        except ValueError as exc:
            log.warning(
                "composite_forge.branching_register_failed",
                error=str(exc),
            )
            return None

        log.info(
            "composite_forge.branching_success",
            skill_name=skill_name,
        )
        return record
