"""Supporting types used by the core interface ABCs."""

from __future__ import annotations

from pydantic import Field

from evosys.schemas._types import EvoBaseModel, ImplementationType, UlidType, new_ulid


class Action(EvoBaseModel):
    """A single planned action within an ActionPlan."""

    action_id: UlidType = Field(default_factory=new_ulid)
    name: str = Field(min_length=1, max_length=256)
    params: dict[str, object] = Field(default_factory=dict)
    depends_on: list[UlidType] = Field(default_factory=list)


class ActionPlan(EvoBaseModel):
    """An ordered plan of actions produced by the orchestrator."""

    plan_id: UlidType = Field(default_factory=new_ulid)
    task_description: str = Field(min_length=1)
    actions: list[Action] = Field(min_length=1)
    reasoning: str = ""


class Observation(EvoBaseModel):
    """The result of executing a single Action."""

    action_id: UlidType
    success: bool
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float = Field(ge=0, default=0)
    token_cost: int = Field(ge=0, default=0)


class IOPair(EvoBaseModel):
    """A single input/output example used for skill training and evaluation."""

    input_data: dict[str, object] = Field(default_factory=dict)
    output_data: dict[str, object] = Field(default_factory=dict)
    trace_id: UlidType | None = None


class ShadowComparison(EvoBaseModel):
    """Result of comparing a skill's output against the cloud LLM ground truth."""

    skill_output: dict[str, object] = Field(default_factory=dict)
    llm_output: dict[str, object] = Field(default_factory=dict)
    agreement: bool
    similarity_score: float = Field(ge=0, le=1)
    notes: str = ""


class LearnabilityAssessment(EvoBaseModel):
    """Result of estimating a SliceCandidate's learnability."""

    determinism_ratio: float = Field(ge=0, le=1)
    schema_consistency: float = Field(ge=0, le=1)
    avg_output_tokens: int = Field(ge=0)
    recommended_tier: ImplementationType
    learnability_score: float = Field(ge=0, le=1)
    reasoning: str = ""
