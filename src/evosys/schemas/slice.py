"""SliceCandidate — output of the reflection daemon's pattern detection."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field, field_validator, model_validator

from ._types import EvoBaseModel, ForgeStatus, UlidType, new_ulid, utc_now


class SliceCandidate(EvoBaseModel):
    """A candidate action sub-sequence identified for potential skill forging."""

    SCHEMA_VERSION: ClassVar[int] = 1

    schema_version: int = 1
    candidate_id: UlidType = Field(default_factory=new_ulid)
    action_sequence: list[str] = Field(min_length=1)
    frequency: int = Field(ge=1)
    occurrence_trace_ids: list[UlidType] = Field(min_length=1)
    input_schema_inferred: dict[str, object] = Field(default_factory=dict)
    output_schema_inferred: dict[str, object] = Field(default_factory=dict)
    boundary_confidence: float = Field(ge=0, le=1)
    forge_status: ForgeStatus = ForgeStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("schema_version")
    @classmethod
    def _reject_future_versions(cls, v: int) -> int:
        if v > cls.SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {v} is from a newer EvoSys release "
                f"(current: {cls.SCHEMA_VERSION}). Please upgrade."
            )
        return v

    @model_validator(mode="after")
    def _frequency_matches_traces(self) -> SliceCandidate:
        if self.frequency != len(self.occurrence_trace_ids):
            raise ValueError(
                f"frequency ({self.frequency}) must equal "
                f"len(occurrence_trace_ids) ({len(self.occurrence_trace_ids)})"
            )
        return self
