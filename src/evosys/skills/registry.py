"""In-memory skill registry — pairs metadata with implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from evosys.core.interfaces import BaseSkill
from evosys.schemas._types import SkillStatus, utc_now
from evosys.schemas.skill import SkillRecord


@dataclass(slots=True)
class SkillEntry:
    """A registry entry pairing a :class:`SkillRecord` with its implementation."""

    record: SkillRecord
    implementation: BaseSkill


class SkillRegistry:
    """In-memory registry of named skills.

    Each skill is stored as a :class:`SkillEntry` keyed by
    ``record.name``.
    """

    def __init__(self) -> None:
        self._entries: dict[str, SkillEntry] = {}

    def register(self, record: SkillRecord, implementation: BaseSkill) -> None:
        """Register a skill.

        Raises:
            ValueError: if the name is already taken or the skill fails
                its internal health check.
        """
        if record.name in self._entries:
            raise ValueError(f"Skill already registered: {record.name!r}")
        if not implementation.validate():
            raise ValueError(
                f"Skill {record.name!r} failed its validate() health check"
            )
        self._entries[record.name] = SkillEntry(
            record=record, implementation=implementation
        )

    def unregister(self, name: str) -> SkillRecord:
        """Remove and return the record for *name*.

        Raises:
            KeyError: if the name is not registered.
        """
        entry = self._entries.pop(name)  # raises KeyError if missing
        return entry.record

    def lookup(self, name: str) -> SkillEntry | None:
        """Return the entry for *name*, or ``None`` if not registered."""
        return self._entries.get(name)

    def lookup_active(
        self, name: str, min_confidence: float = 0.0
    ) -> SkillEntry | None:
        """Return the entry only if it is ACTIVE and above *min_confidence*.

        Returns ``None`` if missing, not ACTIVE, or below the threshold.
        """
        entry = self._entries.get(name)
        if entry is None:
            return None
        if entry.record.status != SkillStatus.ACTIVE:
            return None
        if entry.record.confidence_score < min_confidence:
            return None
        return entry

    def list_all(self) -> list[SkillEntry]:
        """Return all registered entries."""
        return list(self._entries.values())

    def list_active(self) -> list[SkillEntry]:
        """Return only entries with ACTIVE status."""
        return [
            e for e in self._entries.values()
            if e.record.status == SkillStatus.ACTIVE
        ]

    def record_invocation(
        self, name: str, timestamp: datetime | None = None
    ) -> None:
        """Increment invocation count and set last_invoked.

        No-op if *name* is not registered.
        """
        entry = self._entries.get(name)
        if entry is None:
            return
        ts = timestamp or utc_now()
        # SkillRecord is a Pydantic model — rebuild with updated fields.
        entry.record = entry.record.model_copy(
            update={
                "invocation_count": entry.record.invocation_count + 1,
                "last_invoked": ts,
            }
        )

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:  # type: ignore[override]
        return name in self._entries
