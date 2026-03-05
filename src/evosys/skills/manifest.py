"""Skill manifest — portable format for skill import/export."""

from __future__ import annotations

from typing import Any

import orjson
from pydantic import BaseModel


class SkillManifest(BaseModel):
    """Portable skill manifest for marketplace exchange.

    Contains everything needed to import a skill into another
    EvoSys instance: metadata, source code, and sample I/O.
    """

    version: str = "1.0"
    name: str
    description: str
    domain: str = ""
    source_code: str
    record_json: str  # Serialized SkillRecord
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    sample_inputs: list[dict[str, Any]] = []
    sample_outputs: list[dict[str, Any]] = []
    tags: list[str] = []
    author: str = ""
    created_at: str = ""

    def to_file(self, path: str) -> str:
        """Write manifest to a JSON file. Returns the file path."""
        import json
        from pathlib import Path

        p = Path(path)
        if p.is_dir():
            p = p / f"{self.name}.evoskill.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.model_dump(), indent=2, default=str))
        return str(p)

    @classmethod
    def from_file(cls, path: str) -> SkillManifest:
        """Load manifest from a JSON file."""
        from pathlib import Path

        data = orjson.loads(Path(path).read_bytes())
        return cls.model_validate(data)
