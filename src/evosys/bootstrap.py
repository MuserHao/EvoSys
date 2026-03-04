"""System bootstrap — assembles a fully wired EvoSys runtime."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evosys.agents.extraction_agent import ExtractionAgent
from evosys.config import EvoSysConfig
from evosys.executors.http_executor import HttpExecutor
from evosys.executors.skill_executor import SkillExecutor
from evosys.llm.client import LLMClient
from evosys.orchestration.routing_orchestrator import RoutingOrchestrator
from evosys.skills.loader import register_builtin_skills
from evosys.skills.registry import SkillRegistry
from evosys.storage.engine import dispose_engine, init_engine, make_session_factory
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.trajectory.logger import TrajectoryLogger


@dataclass(slots=True)
class EvoSysRuntime:
    """Holds all wired components for a running EvoSys instance."""

    config: EvoSysConfig
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    trajectory_store: TrajectoryStore
    trajectory_logger: TrajectoryLogger
    llm: LLMClient
    http_executor: HttpExecutor
    skill_registry: SkillRegistry
    skill_executor: SkillExecutor
    routing_orchestrator: RoutingOrchestrator
    agent: ExtractionAgent

    async def shutdown(self) -> None:
        """Dispose of the database engine."""
        await dispose_engine(self.engine)


async def bootstrap(
    config: EvoSysConfig | None = None,
    *,
    load_builtin_skills: bool = True,
) -> EvoSysRuntime:
    """Create a fully wired EvoSys runtime from *config*.

    If *config* is ``None``, reads from environment variables.
    Set *load_builtin_skills* to ``False`` to start with an empty registry.
    """
    cfg = config or EvoSysConfig.from_env()

    engine = await init_engine(cfg.db_url)
    session_factory = make_session_factory(engine)
    trajectory_store = TrajectoryStore(session_factory)
    trajectory_logger = TrajectoryLogger(trajectory_store)

    llm = LLMClient(
        model=cfg.llm_model,
        temperature=cfg.llm_temperature,
        max_tokens=cfg.llm_max_tokens,
    )
    http_executor = HttpExecutor(
        timeout_s=cfg.http_timeout_s,
        max_body_bytes=cfg.http_max_body_bytes,
    )

    skill_registry = SkillRegistry()
    if load_builtin_skills:
        register_builtin_skills(skill_registry)
    skill_executor = SkillExecutor(skill_registry)
    routing_orchestrator = RoutingOrchestrator(
        registry=skill_registry,
        confidence_threshold=cfg.skill_confidence_threshold,
    )

    agent = ExtractionAgent(
        llm=llm,
        http=http_executor,
        trajectory_logger=trajectory_logger,
        orchestrator=routing_orchestrator,
        skill_executor=skill_executor,
    )

    return EvoSysRuntime(
        config=cfg,
        engine=engine,
        session_factory=session_factory,
        trajectory_store=trajectory_store,
        trajectory_logger=trajectory_logger,
        llm=llm,
        http_executor=http_executor,
        skill_registry=skill_registry,
        skill_executor=skill_executor,
        routing_orchestrator=routing_orchestrator,
        agent=agent,
    )
