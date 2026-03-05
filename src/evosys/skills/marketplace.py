"""Skill marketplace — export, import, and search skills.

Lightweight skill exchange using portable manifest files.  Skills
can be exported from one EvoSys instance and imported into another.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from evosys.skills.manifest import SkillManifest

if TYPE_CHECKING:
    from evosys.skills.registry import SkillRegistry
    from evosys.storage.skill_store import SkillStore

log = structlog.get_logger()


class SkillMarketplace:
    """Export and import skills as portable manifest files.

    Parameters
    ----------
    skill_store:
        Persistent storage for skills.
    registry:
        In-memory skill registry.
    """

    def __init__(
        self,
        skill_store: SkillStore,
        registry: SkillRegistry,
    ) -> None:
        self._store = skill_store
        self._registry = registry

    async def export_skill(self, name: str, output_dir: str) -> str:
        """Export a skill to a manifest file.

        Returns the path to the created file.
        Raises ValueError if the skill doesn't exist.
        """
        # Check in-memory registry first
        entry = self._registry.lookup(name)
        if entry is None:
            raise ValueError(f"Skill '{name}' not found in registry")

        record = entry.record

        # Try to get source code from persistent store
        source_code = ""
        try:
            persisted = await self._store.load_all()
            for ps in persisted:
                if ps.record.name == name:
                    source_code = ps.source_code or ""
                    break
        except Exception:
            pass

        manifest = SkillManifest(
            name=record.name,
            description=record.description,
            domain=record.name.removeprefix("extract:"),
            source_code=source_code,
            record_json=json.dumps(record.model_dump(), default=str),
            input_schema=dict(record.input_schema) if hasattr(record, "input_schema") else {},
            output_schema=dict(record.output_schema) if hasattr(record, "output_schema") else {},
            tags=[],
            author="evosys",
            created_at=datetime.now(UTC).isoformat(),
        )

        path = manifest.to_file(output_dir)
        log.info("marketplace.exported", skill=name, path=path)
        return path

    async def import_skill(self, path: str) -> str:
        """Import a skill from a manifest file.

        Returns the name of the imported skill.
        Raises ValueError if the manifest is invalid or the skill
        already exists.
        """
        manifest = SkillManifest.from_file(path)

        if manifest.name in self._registry:
            raise ValueError(
                f"Skill '{manifest.name}' already exists. "
                "Unregister it first or use a different name."
            )

        if not manifest.source_code:
            raise ValueError("Manifest has no source code — cannot import")

        # Compile the source code
        from evosys.forge.forge import _compile_extract, _SynthesizedSkill

        extract_fn = _compile_extract(manifest.source_code)
        if extract_fn is None:
            raise ValueError("Failed to compile skill source code")

        # Reconstruct the SkillRecord
        import orjson

        from evosys.schemas.skill import SkillRecord

        record = SkillRecord.model_validate(orjson.loads(manifest.record_json))
        skill = _SynthesizedSkill(extract_fn)

        # Register in memory
        self._registry.register(record, skill)

        # Persist to DB
        try:
            await self._store.save(record, manifest.source_code)
        except Exception:
            log.warning("marketplace.persist_failed", skill=manifest.name)

        log.info("marketplace.imported", skill=manifest.name, path=path)
        return manifest.name

    def search_local(self, query: str) -> list[dict[str, str]]:
        """Search local registry for skills matching query."""
        q = query.lower()
        results = []
        for entry in self._registry.list_all():
            if q in entry.record.name.lower() or q in entry.record.description.lower():
                results.append({
                    "name": entry.record.name,
                    "description": entry.record.description,
                    "status": entry.record.status.value,
                    "confidence": f"{entry.record.confidence_score:.2f}",
                })
        return results
