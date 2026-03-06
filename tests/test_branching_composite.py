"""Tests for branching composite skills."""

from __future__ import annotations

from typing import ClassVar

from ulid import ULID

from evosys.forge.composite_forge import (
    CompositeForge,
    CompositeStep,
    OnError,
    _BranchingCompositeSkill,
)
from evosys.reflection.sequence_detector import SequenceDetector
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(
        self,
        name: str,
        result: dict[str, object] | None = None,
        *,
        fail: bool = False,
    ):
        self._name = name
        self._result = result or {"data": "ok"}
        self._fail = fail

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake {self._name}"

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {}

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        if self._fail:
            return {"error": "tool failed"}
        return self._result

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }


def _make_registry_pair(
    *tools: _FakeTool,
) -> tuple[SkillRegistry, ToolRegistry]:
    sr = SkillRegistry()
    tr = ToolRegistry(sr)
    for t in tools:
        tr.register_external(t)
    return sr, tr


def _make_record(
    session_id: ULID,
    iteration: int,
    action_name: str,
    success: bool = True,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=session_id,
        iteration_index=iteration,
        action_name=action_name,
        context_summary="Test",
        success=success,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBranchingCompositeSkill:
    async def test_retry_on_error(self):
        """Retry policy retries a failing tool."""
        call_count = 0

        class _FlakeyTool:
            name = "flakey"
            description = "Flakey tool"
            parameters_schema: ClassVar[dict] = {}

            async def __call__(self, **kw: object) -> dict[str, object]:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    return {"error": "transient"}
                return {"data": "ok"}

            def to_openai_tool(self) -> dict[str, object]:
                return {
                    "type": "function",
                    "function": {
                        "name": "flakey",
                        "description": "f",
                        "parameters": {},
                    },
                }

        _sr, tr = _make_registry_pair()
        tr.register_external(_FlakeyTool())  # type: ignore[arg-type]
        step = CompositeStep(
            tool_name="flakey",
            on_error=OnError.RETRY,
            max_retries=3,
        )
        skill = _BranchingCompositeSkill([step], tr)
        result = await skill.invoke({})
        assert "error" not in result or len(result) > 1
        assert result["data"] == "ok"

    async def test_skip_on_error(self):
        """SKIP policy continues to next step on failure."""
        fail_tool = _FakeTool("fail_step", fail=True)
        ok_tool = _FakeTool("ok_step", {"final": "done"})
        _sr, tr = _make_registry_pair(fail_tool, ok_tool)

        steps = [
            CompositeStep(
                tool_name="fail_step", on_error=OnError.SKIP
            ),
            CompositeStep(tool_name="ok_step"),
        ]
        skill = _BranchingCompositeSkill(steps, tr)
        result = await skill.invoke({})
        assert result.get("final") == "done"

    async def test_fallback_tool(self):
        """Fallback tool is tried when primary fails."""
        primary = _FakeTool("primary", fail=True)
        fallback = _FakeTool("fallback", {"from": "fallback"})
        _sr, tr = _make_registry_pair(primary, fallback)

        step = CompositeStep(
            tool_name="primary",
            fallback_tool="fallback",
        )
        skill = _BranchingCompositeSkill([step], tr)
        result = await skill.invoke({})
        assert result.get("from") == "fallback"

    async def test_conditional_step(self):
        """Step with condition_key is skipped if key is falsy."""
        tool = _FakeTool("conditional", {"cond_result": True})
        _sr, tr = _make_registry_pair(tool)

        step = CompositeStep(
            tool_name="conditional",
            condition_key="should_run",
            optional=True,
        )
        skill = _BranchingCompositeSkill([step], tr)
        # condition_key not in input → step skipped
        result = await skill.invoke({})
        assert "cond_result" not in result

    async def test_optional_step_skipped_on_failure(self):
        """Optional step doesn't abort the chain on failure."""
        opt_tool = _FakeTool("optional_step", fail=True)
        final_tool = _FakeTool("final_step", {"done": True})
        _sr, tr = _make_registry_pair(opt_tool, final_tool)

        steps = [
            CompositeStep(
                tool_name="optional_step", optional=True
            ),
            CompositeStep(tool_name="final_step"),
        ]
        skill = _BranchingCompositeSkill(steps, tr)
        result = await skill.invoke({})
        assert result.get("done") is True

    async def test_validate_checks_primary_tools(self):
        """validate() returns False if primary tool is missing."""
        _sr, tr = _make_registry_pair()
        step = CompositeStep(tool_name="nonexistent")
        skill = _BranchingCompositeSkill([step], tr)
        assert not skill.validate()


class TestForgeBranching:
    async def test_forge_branching_creates_skill(self):
        tool_a = _FakeTool("tool_a", {"a": 1})
        tool_b = _FakeTool("tool_b", {"b": 2})
        sr, tr = _make_registry_pair(tool_a, tool_b)

        forge = CompositeForge(sr, tr)
        steps = [
            CompositeStep(tool_name="tool_a"),
            CompositeStep(tool_name="tool_b"),
        ]
        record = await forge.forge_branching(steps, frequency=5)
        assert record is not None
        assert "branching" in record.name
        assert record.name in sr


class TestDetectFallbacks:
    def test_detect_a_fail_b_success_pattern(self):
        """Finds A(fail)->B(success) patterns across sessions."""
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend([
                _make_record(sid, 0, "tool:fetch", success=False),
                _make_record(sid, 1, "tool:fetch_v2", success=True),
            ])

        detector = SequenceDetector(min_frequency=3)
        fallbacks = detector.detect_fallbacks(records)
        assert fallbacks == {"tool:fetch": "tool:fetch_v2"}

    def test_no_fallback_below_threshold(self):
        """Fallbacks below min_frequency are not reported."""
        records = []
        sid = ULID()
        records.extend([
            _make_record(sid, 0, "tool:a", success=False),
            _make_record(sid, 1, "tool:b", success=True),
        ])

        detector = SequenceDetector(min_frequency=3)
        fallbacks = detector.detect_fallbacks(records)
        assert fallbacks == {}
