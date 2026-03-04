"""End-to-end integration test: trajectory → evolution → routing.

Verifies the complete self-evolution pipeline in a single test:
1. Agent tool calls are logged to a real (in-memory) DB
2. EvolutionLoop.run_cycle() reads those records and forges a skill
3. RoutingOrchestrator routes subsequent requests to the forged skill

No LLM calls are made — only the synthesizer is mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from evosys.forge.forge import SkillForge
from evosys.forge.synthesizer import SkillSynthesizer
from evosys.loop import EvolutionLoop
from evosys.orchestration.routing_orchestrator import RoutingOrchestrator
from evosys.schemas._types import SkillStatus
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry
from evosys.storage.trajectory_store import TrajectoryStore


def _llm_extract_record(domain: str, session_id: str | None = None) -> TrajectoryRecord:
    """Simulate a trajectory record written by ExtractionAgent._execute_llm_path."""
    from ulid import ULID

    return TrajectoryRecord(
        session_id=ULID() if session_id is None else ULID.from_str(session_id),
        iteration_index=1,
        context_summary=f"LLM extraction from https://{domain}/page",
        action_name="llm_extract",
        action_params={
            "html": f"<h1>{domain} title</h1>",
            "url": f"https://{domain}/page",
        },
        action_result={"title": f"{domain} title"},
        token_cost=200,
        latency_ms=300.0,
        skill_used=None,
        timestamp_utc=datetime.now(UTC),
    )


@pytest.mark.anyio()
async def test_trajectory_to_forged_skill_to_routing(
    trajectory_store: TrajectoryStore,
) -> None:
    """Full pipeline: save trajectories → run evolution loop → skill is routable."""
    domain = "target.com"

    # --- Step 1: populate DB with enough LLM extraction records ---
    for _ in range(4):  # above default min_frequency=3
        await trajectory_store.save(_llm_extract_record(domain))

    # --- Step 2: build the evolution loop with a mock synthesizer ---
    # The synthesizer returns real (compilable, safe) Python code so the
    # full forge pipeline runs: AST check → compile → await invoke → register.
    synth_code = (
        "import re\n"
        "async def extract(input_data):\n"
        "    m = re.search(r'<h1>(.*?)</h1>', input_data.get('html', ''))\n"
        "    return {'title': m.group(1) if m else ''}\n"
    )
    mock_synth = AsyncMock(spec=SkillSynthesizer)
    mock_synth.synthesize = AsyncMock(return_value=synth_code)

    registry = SkillRegistry()
    forge = SkillForge(mock_synth, registry)
    loop = EvolutionLoop(trajectory_store, forge, registry, min_frequency=3)

    # --- Step 3: run the evolution cycle ---
    result = await loop.run_cycle()

    assert result.candidates_found >= 1
    assert result.forge_succeeded >= 1
    skill_name = f"extract:{domain}"
    assert skill_name in registry

    # --- Step 4: skill must be ACTIVE with a meaningful pass_rate ---
    entry = registry.lookup_active(skill_name)
    assert entry is not None
    assert entry.record.status == SkillStatus.ACTIVE
    assert entry.record.pass_rate > 0

    # --- Step 5: routing orchestrator must choose the skill over fallback ---
    fallback = AsyncMock()
    fallback.plan = AsyncMock()
    orchestrator = RoutingOrchestrator(
        registry, fallback=fallback, confidence_threshold=0.0
    )
    plan = await orchestrator.plan(f"Extract from https://{domain}/page")

    assert len(plan.actions) == 1
    assert plan.actions[0].name == "invoke_skill"
    assert plan.actions[0].params["skill_name"] == skill_name
    # Fallback was never called — skill was routed
    fallback.plan.assert_not_awaited()


@pytest.mark.anyio()
async def test_below_frequency_threshold_not_forged(
    trajectory_store: TrajectoryStore,
) -> None:
    """Domains with fewer records than min_frequency must not trigger forging."""
    await trajectory_store.save(_llm_extract_record("rare.com"))
    await trajectory_store.save(_llm_extract_record("rare.com"))  # only 2, threshold=3

    mock_synth = AsyncMock(spec=SkillSynthesizer)
    registry = SkillRegistry()
    forge = SkillForge(mock_synth, registry)
    loop = EvolutionLoop(trajectory_store, forge, registry, min_frequency=3)

    result = await loop.run_cycle()

    assert result.candidates_found == 0
    assert result.forge_succeeded == 0
    assert "extract:rare.com" not in registry
    mock_synth.synthesize.assert_not_awaited()
