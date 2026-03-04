"""EvoSys — A self-evolving autonomous agent ecosystem."""

from evosys.agents import Agent, AgentResult, ExtractionAgent, ExtractionError, ExtractionResult
from evosys.bootstrap import EvoSysRuntime, bootstrap
from evosys.config import EvoSysConfig
from evosys.executors import HttpExecutor, SkillExecutor
from evosys.forge import SkillForge, SkillSynthesizer
from evosys.llm import LLMClient, LLMError, LLMResponse, LLMToolCallResponse
from evosys.loop import EvolutionLoop, EvolveCycleResult
from evosys.orchestration import ExtractionOrchestrator, RoutingOrchestrator
from evosys.reflection import PatternCandidate, PatternDetector, ReflectionDaemon, ShadowEvaluator
from evosys.schemas import SkillRecord, SliceCandidate, TrajectoryRecord
from evosys.skills import SkillEntry, SkillRegistry
from evosys.storage import TrajectoryStore, init_engine, make_session_factory
from evosys.tools import SkillToolAdapter, ToolRegistry
from evosys.trajectory import TrajectoryLogger

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "AgentResult",
    "EvoSysConfig",
    "EvoSysRuntime",
    "EvolutionLoop",
    "EvolveCycleResult",
    "ExtractionAgent",
    "ExtractionError",
    "ExtractionOrchestrator",
    "ExtractionResult",
    "HttpExecutor",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMToolCallResponse",
    "PatternCandidate",
    "PatternDetector",
    "ReflectionDaemon",
    "RoutingOrchestrator",
    "ShadowEvaluator",
    "SkillEntry",
    "SkillExecutor",
    "SkillForge",
    "SkillRecord",
    "SkillRegistry",
    "SkillSynthesizer",
    "SkillToolAdapter",
    "SliceCandidate",
    "ToolRegistry",
    "TrajectoryLogger",
    "TrajectoryRecord",
    "TrajectoryStore",
    "__version__",
    "bootstrap",
    "init_engine",
    "make_session_factory",
]
