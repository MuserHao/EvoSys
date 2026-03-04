"""Evolution loop — ties reflection, forging, and registration together.

A single ``evolve_cycle`` call:
1. Runs the reflection daemon's pattern detector to discover patterns.
2. For each pattern, checks if a skill already covers the domain.
3. Attempts to forge new skills for uncovered domains.
4. Optionally shadow-evaluates forged skills against stored LLM outputs.
5. Returns a summary of what was discovered and forged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from ulid import ULID

from evosys.forge.forge import SkillForge
from evosys.reflection.pattern_detector import PatternCandidate, PatternDetector
from evosys.reflection.shadow_evaluator import ShadowEvaluator
from evosys.schemas._types import ForgeStatus, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.schemas.slice import SliceCandidate
from evosys.skills.registry import SkillRegistry
from evosys.storage.trajectory_store import TrajectoryStore

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class EvolveCycleResult:
    """Summary of a single evolution cycle."""

    candidates_found: int
    already_covered: int
    forge_attempted: int
    forge_succeeded: int
    new_skills: list[SkillRecord] = field(default_factory=list)


class EvolutionLoop:
    """Orchestrate the reflect → forge → register cycle."""

    def __init__(
        self,
        store: TrajectoryStore,
        forge: SkillForge,
        registry: SkillRegistry,
        *,
        min_frequency: int = 3,
        shadow_evaluator: ShadowEvaluator | None = None,
    ) -> None:
        self._store = store
        self._forge = forge
        self._registry = registry
        self._detector = PatternDetector(min_frequency=min_frequency)
        self._shadow = shadow_evaluator or ShadowEvaluator()

    async def run_cycle(self) -> EvolveCycleResult:
        """Execute one evolution cycle and return a summary."""
        # 1. Query trajectory store for LLM extractions grouped by domain
        records_by_domain = await self._store.get_llm_extractions_by_domain()

        if not records_by_domain:
            log.info("evolve.no_data")
            return EvolveCycleResult(
                candidates_found=0,
                already_covered=0,
                forge_attempted=0,
                forge_succeeded=0,
            )

        # 2. Detect patterns
        patterns = self._detector.detect(records_by_domain)

        if not patterns:
            log.info("evolve.no_patterns")
            return EvolveCycleResult(
                candidates_found=0,
                already_covered=0,
                forge_attempted=0,
                forge_succeeded=0,
            )

        already_covered = 0
        forge_attempted = 0
        forge_succeeded = 0
        new_skills: list[SkillRecord] = []

        for pattern in patterns:
            skill_name = f"extract:{pattern.domain}"

            if skill_name in self._registry:
                already_covered += 1
                log.info("evolve.already_covered", skill_name=skill_name)
                continue

            # Convert pattern to SliceCandidate for the forge
            candidate = SliceCandidate(
                candidate_id=new_ulid(),
                action_sequence=[pattern.action_name],
                frequency=pattern.frequency,
                occurrence_trace_ids=[
                    ULID.from_str(tid) for tid in pattern.trace_ids
                ],
                boundary_confidence=min(1.0, pattern.frequency / 10.0),
                forge_status=ForgeStatus.PENDING,
            )

            forge_attempted += 1
            record = await self._forge.forge(
                candidate, domain=pattern.domain
            )
            if record is not None:
                # Shadow-evaluate the forged skill
                await self._shadow_evaluate(record, pattern)

                forge_succeeded += 1
                new_skills.append(record)
                log.info(
                    "evolve.forged",
                    skill_name=record.name,
                    confidence=record.confidence_score,
                    shadow_agreement=record.shadow_agreement_rate,
                )

        result = EvolveCycleResult(
            candidates_found=len(patterns),
            already_covered=already_covered,
            forge_attempted=forge_attempted,
            forge_succeeded=forge_succeeded,
            new_skills=new_skills,
        )

        log.info(
            "evolve.cycle_complete",
            candidates=result.candidates_found,
            covered=result.already_covered,
            attempted=result.forge_attempted,
            succeeded=result.forge_succeeded,
        )

        return result

    async def _shadow_evaluate(
        self,
        record: SkillRecord,
        pattern: PatternCandidate,
    ) -> None:
        """Run shadow evaluation on a forged skill using stored samples.

        Compares the skill's output against the stored LLM outputs from
        the pattern's sample data. Updates the record's shadow metrics.
        """
        if not pattern.sample_params or not pattern.sample_results:
            return

        entry = self._registry.lookup(record.name)
        if entry is None:
            return

        total_comparisons = 0
        agreements = 0

        for params, llm_result in zip(
            pattern.sample_params, pattern.sample_results, strict=False
        ):
            try:
                skill_output = await entry.implementation.invoke(dict(params))
                comparison = await self._shadow.compare(
                    skill_output=skill_output,
                    llm_output=dict(llm_result),
                    output_schema=dict(record.output_schema),
                )
                total_comparisons += 1
                if comparison.agreement:
                    agreements += 1
            except Exception:
                total_comparisons += 1
                # Skill failed — counts as disagreement

        if total_comparisons > 0:
            agreement_rate = agreements / total_comparisons
            record.shadow_agreement_rate = round(agreement_rate, 4)
            record.total_shadow_comparisons = total_comparisons

            log.info(
                "evolve.shadow_eval",
                skill_name=record.name,
                agreement_rate=agreement_rate,
                comparisons=total_comparisons,
            )
