"""TrajectoryRecord — the atomic log unit for all agent actions."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field, field_validator

from ._types import EvoBaseModel, UlidType, new_ulid, utc_now


class TrajectoryRecord(EvoBaseModel):
    """A single logged step in an agent's execution trajectory."""

    SCHEMA_VERSION: ClassVar[int] = 1

    schema_version: int = 1
    trace_id: UlidType = Field(default_factory=new_ulid)
    session_id: UlidType
    parent_task_id: UlidType | None = None
    timestamp_utc: datetime = Field(default_factory=utc_now)
    iteration_index: int = Field(ge=0)
    context_summary: str = Field(min_length=1, max_length=10_000)
    llm_reasoning: str = ""
    action_name: str = Field(min_length=1, max_length=256)
    action_params: dict[str, object] = Field(default_factory=dict)
    action_result: dict[str, object] = Field(default_factory=dict)
    token_cost: int = Field(ge=0, default=0)
    latency_ms: float = Field(ge=0, default=0)
    skill_used: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _reject_future_versions(cls, v: int) -> int:
        if v > cls.SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {v} is from a newer EvoSys release "
                f"(current: {cls.SCHEMA_VERSION}). Please upgrade."
            )
        return v
