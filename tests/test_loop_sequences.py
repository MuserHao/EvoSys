"""Tests for the evolution loop's tool-call sequence detection path."""

from __future__ import annotations

from unittest.mock import AsyncMock

from ulid import ULID

from evosys.forge.composite_forge import CompositeForge
from evosys.forge.forge import SkillForge
from evosys.loop import EvolutionLoop, EvolveCycleResult
from evosys.reflection.sequence_detector import SequenceDetector
from evosys.schemas._types import ImplementationType, MaturationStage
from evosys.schemas.skill import SkillRecord
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.tools.registry import ToolRegistry


def _make_tool_record(
    session_id: ULID,
    iteration: int,
    action_name: str,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=session_id,
        iteration_index=iteration,
        action_name=action_name,
        context_summary="Agent task: test",
    )


def _make_composite_record(name: str) -> SkillRecord:
    return SkillRecord(
        name=name,
        description=f"Composite skill {name}",
        implementation_type=ImplementationType.COMPOSITE,
        implementation_path=f"forge:composite:{name}",
        test_suite_path="auto-generated",
        maturation_stage=MaturationStage.SYNTHESIZED,
    )


class TestEvolutionLoopSequenceDetection:
    async def test_no_tool_records(self) -> None:
        store = AsyncMock(spec=TrajectoryStore)
        store.get_llm_extractions_by_domain = AsyncMock(return_value={})
        store.get_tool_trajectories = AsyncMock(return_value=[])

        forge = AsyncMock(spec=SkillForge)
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        cf = CompositeForge(sr, tr)

        loop = EvolutionLoop(
            store, forge, sr,
            tool_registry=tr,
            composite_forge=cf,
        )
        result = await loop.run_cycle()
        assert result.sequences_detected == 0
        assert result.composites_forged == 0

    async def test_sequences_detected_and_forged(self) -> None:
        store = AsyncMock(spec=TrajectoryStore)
        store.get_llm_extractions_by_domain = AsyncMock(return_value={})

        # Create tool trajectory data with a recurring pattern
        records = []
        for _ in range(5):
            sid = ULID()
            records.extend([
                _make_tool_record(sid, 0, "tool:web_fetch"),
                _make_tool_record(sid, 1, "tool:extract"),
            ])
        store.get_tool_trajectories = AsyncMock(return_value=records)

        forge = AsyncMock(spec=SkillForge)
        sr = SkillRegistry()
        tr = ToolRegistry(sr)

        # Register the tools so composite forge can find them
        class _FakeTool:
            def __init__(self, name):
                self._name = name
            @property
            def name(self): return self._name
            @property
            def description(self): return ""
            @property
            def parameters_schema(self): return {}
            async def __call__(self, **kwargs): return {}
            def to_openai_tool(self):
                return {
                    "type": "function",
                    "function": {
                        "name": self._name,
                        "description": "",
                        "parameters": {},
                    },
                }

        tr.register_external(_FakeTool("web_fetch"))
        tr.register_external(_FakeTool("extract"))
        cf = CompositeForge(sr, tr)

        loop = EvolutionLoop(
            store, forge, sr,
            tool_registry=tr,
            composite_forge=cf,
            sequence_detector=SequenceDetector(min_frequency=3),
        )
        result = await loop.run_cycle()
        assert result.sequences_detected >= 1
        assert result.composites_forged >= 1
        assert len(result.new_skills) >= 1

    async def test_no_composite_forge_skips_sequences(self) -> None:
        """Without composite_forge, sequence detection is skipped."""
        store = AsyncMock(spec=TrajectoryStore)
        store.get_llm_extractions_by_domain = AsyncMock(return_value={})

        forge = AsyncMock(spec=SkillForge)
        sr = SkillRegistry()

        # No tool_registry or composite_forge
        loop = EvolutionLoop(store, forge, sr)
        result = await loop.run_cycle()
        assert result.sequences_detected == 0
        assert result.composites_forged == 0

    async def test_both_paths_run(self) -> None:
        """Both domain detection and sequence detection run in one cycle."""
        store = AsyncMock(spec=TrajectoryStore)
        store.get_llm_extractions_by_domain = AsyncMock(return_value={})
        store.get_tool_trajectories = AsyncMock(return_value=[])

        forge = AsyncMock(spec=SkillForge)
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        cf = CompositeForge(sr, tr)

        loop = EvolutionLoop(
            store, forge, sr,
            tool_registry=tr,
            composite_forge=cf,
        )
        result = await loop.run_cycle()
        assert isinstance(result, EvolveCycleResult)
        # Both domain call and tool call were made
        store.get_llm_extractions_by_domain.assert_called_once()
        store.get_tool_trajectories.assert_called_once()


class TestEvolveCycleResultNewFields:
    def test_default_values(self) -> None:
        result = EvolveCycleResult(
            candidates_found=0,
            already_covered=0,
            forge_attempted=0,
            forge_succeeded=0,
        )
        assert result.sequences_detected == 0
        assert result.composites_forged == 0

    def test_with_sequence_data(self) -> None:
        result = EvolveCycleResult(
            candidates_found=3,
            already_covered=1,
            forge_attempted=2,
            forge_succeeded=1,
            sequences_detected=5,
            composites_forged=2,
        )
        assert result.sequences_detected == 5
        assert result.composites_forged == 2
