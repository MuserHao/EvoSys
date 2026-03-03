"""Foundation types, enums, and base model for all EvoSys schemas."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Self

import orjson
from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer
from ulid import ULID

# ---------------------------------------------------------------------------
# ULID helpers
# ---------------------------------------------------------------------------


def _parse_ulid(value: Any) -> ULID:
    """Coerce str / bytes / int / ULID → ULID."""
    if isinstance(value, ULID):
        return value
    if isinstance(value, str):
        return ULID.from_str(value)
    if isinstance(value, bytes):
        return ULID.from_bytes(value)
    if isinstance(value, int):
        return ULID.from_int(value)
    raise ValueError(f"Cannot coerce {type(value).__name__} to ULID")


def _serialize_ulid(value: ULID) -> str:
    return str(value)


UlidType = Annotated[ULID, BeforeValidator(_parse_ulid), PlainSerializer(_serialize_ulid)]


def new_ulid() -> ULID:
    """Generate a fresh ULID."""
    return ULID()


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# SemverStr
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*))?$"
)


def _validate_semver(value: Any) -> str:
    s = str(value)
    if not _SEMVER_RE.match(s):
        raise ValueError(f"Invalid semver string: {s!r}")
    return s


SemverStr = Annotated[str, BeforeValidator(_validate_semver)]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ImplementationType(StrEnum):
    PYTHON_FN = "python_fn"
    PROMPT_CACHE = "prompt_cache"
    TINY_MODEL = "tiny_model"
    COMPOSITE = "composite"


class SkillStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ForgeStatus(StrEnum):
    PENDING = "pending"
    FORGING = "forging"
    PASSED = "passed"
    FAILED = "failed"
    ABANDONED = "abandoned"


# ---------------------------------------------------------------------------
# EvoBaseModel
# ---------------------------------------------------------------------------


class EvoBaseModel(BaseModel):
    """Shared Pydantic base for all EvoSys models."""

    SCHEMA_VERSION: ClassVar[int] = 1

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        ser_json_bytes="base64",
    )

    def model_dump_orjson(self, **kwargs: Any) -> bytes:
        """Serialize to JSON bytes via orjson for speed."""
        return orjson.dumps(self.model_dump(mode="json", **kwargs))

    @classmethod
    def model_validate_orjson(cls, data: bytes | str) -> Self:
        """Deserialize from JSON bytes/str via orjson for speed."""
        return cls.model_validate(orjson.loads(data))
