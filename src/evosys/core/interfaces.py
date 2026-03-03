"""Abstract base classes defining the core EvoSys component contracts.

All methods are ``async def`` because the runtime uses ``anyio`` and LLM
calls are inherently asynchronous.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from evosys.core.types import (
    Action,
    ActionPlan,
    IOPair,
    LearnabilityAssessment,
    Observation,
    ShadowComparison,
)
from evosys.schemas.skill import SkillRecord
from evosys.schemas.slice import SliceCandidate


class BaseOrchestrator(ABC):
    """Plans a task into an ordered sequence of actions."""

    @abstractmethod
    async def plan(self, task: str) -> ActionPlan:
        """Decompose *task* into an ActionPlan."""


class BaseSkill(ABC):
    """A registered micro-skill that can be invoked on structured input."""

    @abstractmethod
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        """Execute the skill on *input_data* and return structured output."""

    @abstractmethod
    def validate(self) -> bool:
        """Return True if the skill passes its internal health check."""


class BaseExecutor(ABC):
    """Executes a single Action and returns an Observation."""

    @abstractmethod
    async def execute(self, action: Action) -> Observation:
        """Execute *action* and return an Observation."""


class BaseReflectionDaemon(ABC):
    """Mines trajectory data for recurring patterns that can become skills."""

    @abstractmethod
    async def run_cycle(self) -> list[SliceCandidate]:
        """Analyse recent trajectories and return discovered slice candidates."""


class BaseForge(ABC):
    """Synthesises, evaluates, and promotes a SliceCandidate into a SkillRecord."""

    @abstractmethod
    async def forge(self, candidate: SliceCandidate) -> SkillRecord | None:
        """Attempt to forge *candidate*. Return the new SkillRecord on success."""


class BaseShadowEvaluator(ABC):
    """Compares a skill's output against cloud LLM ground truth."""

    @abstractmethod
    async def compare(
        self,
        skill_output: dict[str, object],
        llm_output: dict[str, object],
        output_schema: dict[str, object],
    ) -> ShadowComparison:
        """Compare *skill_output* against *llm_output* and return a verdict."""


class BaseLearnabilityEstimator(ABC):
    """Estimates how learnable a SliceCandidate is and recommends a tier."""

    @abstractmethod
    async def estimate(
        self,
        candidate: SliceCandidate,
        examples: list[IOPair],
    ) -> LearnabilityAssessment:
        """Score *candidate*'s learnability and recommend an implementation tier."""
