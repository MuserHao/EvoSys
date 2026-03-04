"""Tests for CompositeForge."""

from __future__ import annotations

from evosys.forge.composite_forge import CompositeForge, _CompositeSkill
from evosys.reflection.sequence_detector import SequenceCandidate
from evosys.schemas._types import ImplementationType
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str, result: dict[str, object]) -> None:
        self._name = name
        self._result = result

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
        return self._result

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {"name": self._name, "description": self.description, "parameters": {}},
        }


def _make_candidate(
    tool_sequence: list[str],
    frequency: int = 5,
) -> SequenceCandidate:
    return SequenceCandidate(
        tool_sequence=tool_sequence,
        frequency=frequency,
        session_ids=[f"s{i}" for i in range(frequency)],
        avg_latency_ms=100.0,
        avg_token_cost=50,
        canonical_form=" -> ".join(tool_sequence),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompositeForge:
    async def test_forge_success(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("fetch", {"html": "<h1>Hi</h1>"}))
        tr.register_external(_FakeTool("parse", {"title": "Hello"}))

        forge = CompositeForge(sr, tr)
        candidate = _make_candidate(["tool:fetch", "tool:parse"], frequency=5)

        record = await forge.forge(candidate)

        assert record is not None
        assert record.name.startswith("composite:fetch_parse_")
        assert record.implementation_type == ImplementationType.COMPOSITE
        assert record.confidence_score == 0.5  # 5/10
        assert record.name in sr

    async def test_forge_already_registered(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("fetch", {}))
        tr.register_external(_FakeTool("parse", {}))

        forge = CompositeForge(sr, tr)
        candidate = _make_candidate(["tool:fetch", "tool:parse"])

        # First forge
        await forge.forge(candidate)
        # Second forge - should return None
        result = await forge.forge(candidate)
        assert result is None

    async def test_forge_missing_tool(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("fetch", {}))
        # "parse" not registered

        forge = CompositeForge(sr, tr)
        candidate = _make_candidate(["tool:fetch", "tool:parse"])

        result = await forge.forge(candidate)
        assert result is None

    async def test_forge_confidence_scaling(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("a", {}))
        tr.register_external(_FakeTool("b", {}))

        forge = CompositeForge(sr, tr)

        # frequency=10 -> confidence=1.0
        candidate = _make_candidate(["tool:a", "tool:b"], frequency=10)
        record = await forge.forge(candidate)
        assert record is not None
        assert record.confidence_score == 1.0

    async def test_forge_description(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("a", {}))
        tr.register_external(_FakeTool("b", {}))

        forge = CompositeForge(sr, tr)
        candidate = _make_candidate(["tool:a", "tool:b"], frequency=5)

        record = await forge.forge(candidate)
        assert record is not None
        assert "a -> b" in record.description

    async def test_different_sequences_produce_unique_names(self) -> None:
        """Two sequences with the same short names but different order
        must not collide because the hash disambiguates them."""
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("fetch", {}))
        tr.register_external(_FakeTool("parse", {}))

        forge = CompositeForge(sr, tr)

        candidate_ab = _make_candidate(["tool:fetch", "tool:parse"])
        candidate_ba = _make_candidate(["tool:parse", "tool:fetch"])

        record_ab = await forge.forge(candidate_ab)
        record_ba = await forge.forge(candidate_ba)

        assert record_ab is not None
        assert record_ba is not None
        assert record_ab.name != record_ba.name

    async def test_name_contains_hash_suffix(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("fetch", {}))
        tr.register_external(_FakeTool("parse", {}))

        forge = CompositeForge(sr, tr)
        candidate = _make_candidate(["tool:fetch", "tool:parse"])
        record = await forge.forge(candidate)

        assert record is not None
        # Name should be "composite:fetch_parse_<6hexchars>"
        parts = record.name.rsplit("_", 1)
        assert len(parts) == 2
        assert len(parts[1]) == 6
        assert all(c in "0123456789abcdef" for c in parts[1])
        assert "5 times" in record.description


class TestCompositeSkill:
    async def test_chains_tools(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("step1", {"intermediate": "data"}))
        tr.register_external(_FakeTool("step2", {"final": "result"}))

        skill = _CompositeSkill(["step1", "step2"], tr)
        result = await skill.invoke({"input": "start"})
        # Should have accumulated results from both tools
        assert "intermediate" in result
        assert "final" in result

    async def test_error_in_chain(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("step1", {"error": "something broke"}))

        skill = _CompositeSkill(["step1", "step2"], tr)
        result = await skill.invoke({})
        assert "error" in result

    async def test_missing_tool_in_chain(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        # No tools registered

        skill = _CompositeSkill(["nonexistent"], tr)
        result = await skill.invoke({})
        assert "error" in result
        assert "not found" in str(result["error"]).lower()

    def test_validate_all_tools_present(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("a", {}))
        tr.register_external(_FakeTool("b", {}))

        skill = _CompositeSkill(["a", "b"], tr)
        assert skill.validate()

    def test_validate_missing_tool(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(_FakeTool("a", {}))

        skill = _CompositeSkill(["a", "missing"], tr)
        assert not skill.validate()
