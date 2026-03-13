"""Evolution loop — ties reflection, forging, and registration together.

A single ``evolve_cycle`` call:
1. Runs the reflection daemon's pattern detector to discover domain patterns.
2. For each pattern, checks if a skill already covers the domain.
3. Attempts to forge new skills for uncovered domains.
4. Detects recurring tool-call sequences across agent sessions.
5. Forges composite skills for frequent sequences.
6. Returns a summary of what was discovered and forged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog
from ulid import ULID

from evosys.core.types import IOPair
from evosys.forge.composite_forge import CompositeForge
from evosys.forge.failure_tracker import ForgeFailureTracker
from evosys.forge.forge import SkillForge
from evosys.reflection.pattern_detector import PatternCandidate, PatternDetector
from evosys.reflection.sequence_detector import SequenceDetector
from evosys.reflection.shadow_evaluator import ShadowEvaluator
from evosys.reflection.strategy_extractor import StrategyExtractor
from evosys.schemas._types import ForgeStatus, SkillStatus, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.schemas.slice import SliceCandidate
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from evosys.storage.skill_store import SkillStore

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class EvolveCycleResult:
    """Summary of a single evolution cycle."""

    candidates_found: int
    already_covered: int
    forge_attempted: int
    forge_succeeded: int
    new_skills: list[SkillRecord] = field(default_factory=list)
    # Phase 9: tool-call sequence detection
    sequences_detected: int = 0
    composites_forged: int = 0
    # Skills whose shadow agreement dropped below threshold this cycle
    skills_degraded: int = 0
    # Strategy extraction from expensive sessions
    strategies_extracted: int = 0
    # Semantic clustering of tool trajectories
    semantic_clusters_found: int = 0


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
        tool_registry: ToolRegistry | None = None,
        composite_forge: CompositeForge | None = None,
        sequence_detector: SequenceDetector | None = None,
        shadow_degradation_threshold: float = 0.5,
        max_forge_per_cycle: int = 5,
        skill_store: SkillStore | None = None,
        reforge_enabled: bool = True,
        reforge_min_samples: int = 3,
        failure_tracker: ForgeFailureTracker | None = None,
        strategy_extractor: StrategyExtractor | None = None,
        semantic_detector: object | None = None,  # SemanticPatternDetector
    ) -> None:
        self._store = store
        self._forge = forge
        self._registry = registry
        self._detector = PatternDetector(min_frequency=min_frequency)
        self._shadow = shadow_evaluator or ShadowEvaluator()
        self._tool_registry = tool_registry
        self._composite_forge = composite_forge
        self._sequence_detector = sequence_detector or SequenceDetector(
            min_frequency=min_frequency
        )
        # Skills with shadow_agreement_rate below this threshold are marked
        # DEGRADED so the routing layer stops sending traffic to them.
        self._shadow_degradation_threshold = shadow_degradation_threshold
        # Cap LLM synthesis calls per cycle to bound API cost.
        # Patterns above the cap are deferred to the next cycle.
        self._max_forge_per_cycle = max_forge_per_cycle
        self._skill_store = skill_store
        self._reforge_enabled = reforge_enabled
        self._reforge_min_samples = reforge_min_samples
        self._failure_tracker = failure_tracker
        self._strategy_extractor = strategy_extractor
        self._semantic_detector = semantic_detector

    async def run_cycle(self) -> EvolveCycleResult:
        """Execute one evolution cycle and return a summary."""
        # Path 1: domain-based pattern detection (existing)
        records_by_domain = await self._store.get_llm_extractions_by_domain()

        patterns: list[PatternCandidate] = []
        if records_by_domain:
            patterns = self._detector.detect(records_by_domain)

        already_covered = 0
        forge_attempted = 0
        forge_succeeded = 0
        skills_degraded = 0
        new_skills: list[SkillRecord] = []

        for pattern in patterns:
            if forge_attempted >= self._max_forge_per_cycle:
                log.info(
                    "evolve.cycle_cap_reached",
                    cap=self._max_forge_per_cycle,
                    remaining=len(patterns) - already_covered - forge_attempted,
                )
                break

            skill_name = f"extract:{pattern.domain}"

            if skill_name in self._registry:
                already_covered += 1
                log.info("evolve.already_covered", skill_name=skill_name)
                continue

            # Skip domains that have been abandoned due to repeated failures
            if (
                self._failure_tracker is not None
                and await self._failure_tracker.should_skip(pattern.domain)
            ):
                log.info(
                    "evolve.domain_abandoned",
                    domain=pattern.domain,
                )
                continue

            # Convert pattern to SliceCandidate for the forge.
            # boundary_confidence is a heuristic: we treat 10+ observations
            # as "fully confident" in the pattern (score = 1.0) and scale
            # linearly below that.  This caps the prior so that a small number
            # of observations can't produce a high-confidence skill; the
            # forge's own pass_rate test provides the second quality gate.
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

            # Build IOPairs from stored trajectory samples.
            # action_params now contains {"html": ..., "url": ..., "target_schema": ...}
            # action_result is the structured JSON the LLM produced.
            # Only include pairs where html is actually present — older records
            # that predate the data-feed fix will have no html key and are
            # skipped so the synthesizer isn't misled by empty inputs.
            sample_io: list[IOPair] = [
                IOPair(
                    input_data={
                        "html": p.get("html", ""),
                        "url": p.get("url", ""),
                    },
                    output_data=dict(r),
                )
                for p, r in zip(
                    pattern.sample_params, pattern.sample_results, strict=False
                )
                if p.get("html")
            ]

            record = await self._forge.forge(
                candidate, domain=pattern.domain, sample_io=sample_io or None
            )
            if record is not None:
                # Record success to clear any prior failure history
                if self._failure_tracker is not None:
                    await self._failure_tracker.record_success(pattern.domain)

                # Shadow-evaluate the forged skill; degrade it if agreement
                # is below threshold so it won't be routed to.
                degraded = await self._shadow_evaluate(record, pattern)
                if degraded:
                    skills_degraded += 1

                forge_succeeded += 1
                new_skills.append(record)
                log.info(
                    "evolve.forged",
                    skill_name=record.name,
                    confidence=record.confidence_score,
                    shadow_agreement=record.shadow_agreement_rate,
                )
            else:
                # Record forge failure
                if self._failure_tracker is not None:
                    await self._failure_tracker.record_failure(
                        pattern.domain, self._forge.last_forge_error
                    )

        # Fetch tool trajectories once for strategy extraction + sequence detection
        tool_records: list[TrajectoryRecord] = []
        if self._strategy_extractor is not None or (
            self._composite_forge is not None and self._tool_registry is not None
        ):
            tool_records = await self._store.get_tool_trajectories()

        # Path 2: strategy extraction from expensive claude_code sessions
        strategies_extracted = 0
        if self._strategy_extractor is not None and tool_records:
            # Group by session and find sessions with claude_code calls
            sessions: dict[str, list[TrajectoryRecord]] = {}
            for rec in tool_records:
                sid = str(rec.session_id)
                sessions.setdefault(sid, []).append(rec)

            for _sid, recs in sessions.items():
                cc_recs = [
                    r
                    for r in recs
                    if "claude_code" in r.action_name
                ]
                if not cc_recs:
                    continue
                cost = sum(
                    float(
                        r.action_result.get("cost_usd", 0)
                    )
                    for r in cc_recs
                )
                record = (
                    await self._strategy_extractor.extract_from_session(
                        recs, cost
                    )
                )
                if record is not None:
                    strategies_extracted += 1
                    new_skills.append(record)

        # Path 2c: semantic clustering of tool trajectories
        semantic_clusters_found = 0
        if self._semantic_detector is not None and tool_records:
            try:
                clusters = await self._semantic_detector.detect(tool_records)
                semantic_clusters_found = len(clusters)
                if clusters:
                    log.info(
                        "evolve.semantic_clusters",
                        count=len(clusters),
                        top_label=clusters[0].label if clusters else "",
                        top_size=len(clusters[0].records) if clusters else 0,
                    )
            except Exception:
                log.exception("evolve.semantic_detection_error")

        # Path 3: tool-call sequence detection (Phase 9)
        sequences_detected = 0
        composites_forged = 0

        if (
            self._composite_forge is not None
            and self._tool_registry is not None
            and tool_records
        ):
                seq_candidates = self._sequence_detector.detect(tool_records)
                sequences_detected = len(seq_candidates)

                for seq_candidate in seq_candidates:
                    record = await self._composite_forge.forge(seq_candidate)
                    if record is not None:
                        composites_forged += 1
                        new_skills.append(record)
                        log.info(
                            "evolve.composite_forged",
                            skill_name=record.name,
                            sequence=seq_candidate.canonical_form,
                        )

                # Path 2b: detect fallback patterns and forge branching composites
                fallbacks = self._sequence_detector.detect_fallbacks(
                    tool_records
                )
                if fallbacks:
                    from evosys.forge.composite_forge import CompositeStep, OnError

                    for failed_tool, fallback_tool in fallbacks.items():
                        step = CompositeStep(
                            tool_name=failed_tool,
                            on_error=OnError.SKIP,
                            fallback_tool=fallback_tool,
                        )
                        record = await self._composite_forge.forge_branching(
                            [step],
                            frequency=0,
                        )
                        if record is not None:
                            composites_forged += 1
                            new_skills.append(record)
                            log.info(
                                "evolve.branching_forged",
                                skill_name=record.name,
                                failed_tool=failed_tool,
                                fallback=fallback_tool,
                            )

        result = EvolveCycleResult(
            candidates_found=len(patterns),
            already_covered=already_covered,
            forge_attempted=forge_attempted,
            forge_succeeded=forge_succeeded,
            new_skills=new_skills,
            sequences_detected=sequences_detected,
            composites_forged=composites_forged,
            skills_degraded=skills_degraded,
            strategies_extracted=strategies_extracted,
            semantic_clusters_found=semantic_clusters_found,
        )

        # Path 4: Re-forge degraded skills; archive if re-forge also fails
        if self._reforge_enabled and skills_degraded > 0:
            try:
                from evosys.forge.reforger import SkillReforger
                reforger = SkillReforger(
                    self._store,
                    self._forge,
                    self._registry,
                    self._skill_store,
                    min_samples=self._reforge_min_samples,
                )
                reforged_count = await reforger.reforge_degraded()
                if reforged_count > 0:
                    log.info("evolve.reforged", count=reforged_count)
            except Exception:
                log.exception("evolve.reforge_error")

        # Path 5: Archive skills that stayed DEGRADED after re-forge attempt
        await self._archive_stale_degraded()

        log.info(
            "evolve.cycle_complete",
            candidates=result.candidates_found,
            covered=result.already_covered,
            attempted=result.forge_attempted,
            succeeded=result.forge_succeeded,
            degraded=result.skills_degraded,
            sequences=result.sequences_detected,
            composites=result.composites_forged,
            strategies=result.strategies_extracted,
        )

        return result

    async def _shadow_evaluate(
        self,
        record: SkillRecord,
        pattern: PatternCandidate,
    ) -> bool:
        """Run shadow evaluation on a forged skill using stored samples.

        Compares the skill's output against the stored LLM outputs from
        the pattern's sample data.  Updates the record's shadow metrics
        in-place and marks the skill DEGRADED if its agreement rate falls
        below ``shadow_degradation_threshold``.

        Returns ``True`` if the skill was degraded, ``False`` otherwise.
        """
        if not pattern.sample_params or not pattern.sample_results:
            return False

        entry = self._registry.lookup(record.name)
        if entry is None:
            return False

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
                    critical_fields=list(record.critical_output_fields),
                )
                total_comparisons += 1
                if comparison.agreement:
                    agreements += 1
            except Exception:
                total_comparisons += 1
                # Skill failed — counts as disagreement

        if total_comparisons == 0:
            return False

        agreement_rate = agreements / total_comparisons
        record.shadow_agreement_rate = round(agreement_rate, 4)
        record.total_shadow_comparisons = total_comparisons

        degraded = agreement_rate < self._shadow_degradation_threshold
        if degraded:
            record.status = SkillStatus.DEGRADED
            log.warning(
                "evolve.skill_degraded",
                skill_name=record.name,
                agreement_rate=agreement_rate,
                threshold=self._shadow_degradation_threshold,
            )
        else:
            log.info(
                "evolve.shadow_eval",
                skill_name=record.name,
                agreement_rate=agreement_rate,
                comparisons=total_comparisons,
            )

        # Persist the updated metrics and status back to the DB.
        if self._skill_store is not None:
            try:
                await self._skill_store.update_shadow(
                    record.name, agreement_rate, total_comparisons
                )
                if degraded:
                    await self._skill_store.update_status(
                        record.name, SkillStatus.DEGRADED
                    )
            except Exception:
                log.warning(
                    "evolve.shadow_persist_failed", skill_name=record.name
                )

        return degraded

    async def _archive_stale_degraded(self) -> None:
        """Archive DEGRADED skills with high shadow comparison counts.

        Skills that have been degraded for a while (10+ comparisons and
        still below threshold) are moved to ARCHIVED so they stop being
        loaded on bootstrap, evaluated, or cluttering the registry.
        """
        for entry in list(self._registry.list_all()):
            record = entry.record
            if (
                record.status == SkillStatus.DEGRADED
                and record.total_shadow_comparisons >= 10
                and (record.shadow_agreement_rate or 0) < self._shadow_degradation_threshold
            ):
                record.status = SkillStatus.ARCHIVED
                import contextlib
                with contextlib.suppress(KeyError):
                    self._registry.unregister(record.name)
                if self._skill_store is not None:
                    with contextlib.suppress(Exception):
                        await self._skill_store.update_status(
                            record.name, SkillStatus.ARCHIVED
                        )
                log.info(
                    "evolve.skill_archived",
                    skill_name=record.name,
                    agreement_rate=record.shadow_agreement_rate,
                )
