"""SkillRecord — the micro-skill registry entry."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field, field_validator, model_validator

from ._types import (
    EvoBaseModel,
    ImplementationType,
    MaturationStage,
    SemverStr,
    SkillStatus,
    UlidType,
    new_ulid,
    utc_now,
)


class SkillRecord(EvoBaseModel):
    """A registered micro-skill in the EvoSys skill registry."""

    SCHEMA_VERSION: ClassVar[int] = 1

    schema_version: int = 1
    skill_id: UlidType = Field(default_factory=new_ulid)
    name: str = Field(min_length=1, max_length=256)
    version: SemverStr = "0.1.0"
    parent_skill_id: UlidType | None = None
    description: str = Field(min_length=1, max_length=5_000)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    implementation_type: ImplementationType
    implementation_path: str = Field(min_length=1)
    created_from_traces: list[UlidType] = Field(default_factory=list)
    test_suite_path: str = Field(min_length=1)
    pass_rate: float = Field(ge=0, le=1, default=1.0)
    invocation_count: int = Field(ge=0, default=0)
    last_invoked: datetime | None = None
    confidence_score: float = Field(ge=0, le=1, default=1.0)
    status: SkillStatus = SkillStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

    # Maturation & shadow-mode tracking
    maturation_stage: MaturationStage = MaturationStage.OBSERVED
    shadow_sample_rate: float = Field(ge=0, le=1, default=1.0)
    shadow_agreement_rate: float | None = Field(ge=0, le=1, default=None)
    total_shadow_comparisons: int = Field(ge=0, default=0)
    tier_demotion_attempts: int = Field(ge=0, default=0)
    current_tier: ImplementationType | None = None

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
    def _active_needs_passing_rate(self) -> SkillRecord:
        if self.status == SkillStatus.ACTIVE and self.pass_rate < 0.5:
            raise ValueError(
                f"Active skills must have pass_rate >= 0.5, got {self.pass_rate}"
            )
        return self
