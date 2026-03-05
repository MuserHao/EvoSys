"""Skill re-forger — detect degraded skills and re-synthesize.

When a forged skill's shadow agreement drops below threshold, the
re-forger collects fresh trajectory samples and attempts to forge
a replacement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from evosys.core.types import IOPair
from evosys.schemas._types import SkillStatus

if TYPE_CHECKING:
    from evosys.forge.forge import SkillForge
    from evosys.skills.registry import SkillRegistry
    from evosys.storage.skill_store import SkillStore
    from evosys.storage.trajectory_store import TrajectoryStore

log = structlog.get_logger()


class SkillReforger:
    """Detect degraded skills and attempt to re-forge them.

    Works as a post-processing step after the main evolution cycle.
    Finds skills marked DEGRADED, gathers fresh trajectory data,
    and asks the forge to produce a better version.

    Parameters
    ----------
    trajectory_store:
        Source of trajectory records for re-training.
    forge:
        The skill forge for synthesis.
    registry:
        Skill registry to update after re-forging.
    skill_store:
        Persistent storage for skills.
    min_samples:
        Minimum trajectory samples needed before attempting re-forge.
    """

    def __init__(
        self,
        trajectory_store: TrajectoryStore,
        forge: SkillForge,
        registry: SkillRegistry,
        skill_store: SkillStore | None = None,
        *,
        min_samples: int = 3,
    ) -> None:
        self._store = trajectory_store
        self._forge = forge
        self._registry = registry
        self._skill_store = skill_store
        self._min_samples = min_samples

    async def reforge_degraded(self) -> int:
        """Find and re-forge degraded skills. Returns count of re-forged skills."""
        degraded_entries = [
            e for e in self._registry.list_all()
            if e.record.status == SkillStatus.DEGRADED
        ]

        if not degraded_entries:
            return 0

        reforged = 0
        for entry in degraded_entries:
            record = entry.record
            domain = record.name.removeprefix("extract:")

            try:
                # Gather fresh trajectory samples for this domain
                records_by_domain = await self._store.get_llm_extractions_by_domain()
                domain_records = records_by_domain.get(domain, [])

                if len(domain_records) < self._min_samples:
                    log.debug(
                        "reforger.insufficient_samples",
                        skill=record.name,
                        samples=len(domain_records),
                        needed=self._min_samples,
                    )
                    continue

                # Build fresh IOPairs
                sample_io: list[IOPair] = []
                for rec in domain_records:
                    params = rec.get("action_params", {})
                    result = rec.get("action_result", {})
                    html = params.get("html", "")
                    if html:
                        sample_io.append(IOPair(
                            input_data={"html": html, "url": params.get("url", "")},
                            output_data=dict(result),
                        ))

                if len(sample_io) < self._min_samples:
                    continue

                # Unregister old skill
                self._registry.unregister(record.name)

                # Re-forge
                from evosys.schemas._types import ForgeStatus, new_ulid
                from evosys.schemas.slice import SliceCandidate

                candidate = SliceCandidate(
                    candidate_id=new_ulid(),
                    action_sequence=[f"llm_extract:{domain}"],
                    frequency=len(domain_records),
                    occurrence_trace_ids=[],
                    boundary_confidence=min(1.0, len(domain_records) / 10.0),
                    forge_status=ForgeStatus.PENDING,
                )

                new_record = await self._forge.forge(
                    candidate, domain=domain, sample_io=sample_io
                )

                if new_record is not None:
                    reforged += 1
                    log.info(
                        "reforger.success",
                        skill=record.name,
                        new_confidence=new_record.confidence_score,
                    )
                else:
                    # Re-register old skill if re-forge failed
                    self._registry.register(record, entry.implementation)
                    log.warning("reforger.failed", skill=record.name)

            except Exception:
                log.exception("reforger.error", skill=record.name)

        return reforged
