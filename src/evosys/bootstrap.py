"""System bootstrap — assembles a fully wired EvoSys runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evosys.agents.agent import Agent
from evosys.agents.extraction_agent import ExtractionAgent
from evosys.agents.sub_agent import SubAgentManager
from evosys.config import EvoSysConfig
from evosys.executors.browser_profiles import BrowserProfileManager
from evosys.executors.http_executor import HttpExecutor
from evosys.executors.skill_executor import SkillExecutor
from evosys.forge.failure_tracker import ForgeFailureTracker
from evosys.forge.forge import SkillForge
from evosys.forge.synthesizer import SkillSynthesizer
from evosys.llm.client import LLMClient
from evosys.llm.embeddings import LiteLLMEmbeddingProvider
from evosys.llm.router import ModelRouter
from evosys.loop import EvolutionLoop
from evosys.orchestration.routing_orchestrator import RoutingOrchestrator
from evosys.reflection.shadow_evaluator import ShadowEvaluator
from evosys.reflection.strategy_extractor import StrategyExtractor
from evosys.skills.loader import register_builtin_skills
from evosys.skills.registry import SkillRegistry
from evosys.storage.embedding_store import EmbeddingMemoryStore
from evosys.storage.engine import dispose_engine, init_engine, make_session_factory
from evosys.storage.memory_store import MemoryStore
from evosys.storage.schedule_store import ScheduleStore
from evosys.storage.skill_store import SkillStore
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.tools.builtins import (
    ExtractStructuredTool,
    FileListTool,
    FileReadTool,
    FileWriteTool,
    HttpApiTool,
    InboxTool,
    PythonEvalTool,
    RecallTool,
    RememberTool,
    SemanticRecallTool,
    SendEmailTool,
    ShellExecTool,
    WatchTool,
    WebFetchTool,
)
from evosys.tools.mcp import MCPManager, MCPServerConfig
from evosys.tools.registry import ToolRegistry
from evosys.tools.sub_agent_tool import SubAgentTool
from evosys.trajectory.logger import TrajectoryLogger

log = structlog.get_logger()


@dataclass(slots=True)
class EvoSysRuntime:
    """Holds all wired components for a running EvoSys instance."""

    config: EvoSysConfig
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    trajectory_store: TrajectoryStore
    memory_store: MemoryStore
    schedule_store: ScheduleStore
    skill_store: SkillStore
    trajectory_logger: TrajectoryLogger
    llm: LLMClient | ModelRouter
    http_executor: HttpExecutor
    skill_registry: SkillRegistry
    skill_executor: SkillExecutor
    routing_orchestrator: RoutingOrchestrator
    extraction_agent: ExtractionAgent
    synthesizer: SkillSynthesizer
    forge: SkillForge
    evolution_loop: EvolutionLoop
    tool_registry: ToolRegistry
    general_agent: Agent
    mcp_manager: MCPManager
    # New components
    embedding_store: EmbeddingMemoryStore | None = None
    sub_agent_manager: SubAgentManager | None = None
    browser_profile_manager: BrowserProfileManager | None = None

    # Backward compat alias
    @property
    def agent(self) -> ExtractionAgent:
        return self.extraction_agent

    async def shutdown(self) -> None:
        """Dispose of the database engine and MCP connections."""
        await self.mcp_manager.disconnect_all()
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
    memory_store = MemoryStore(session_factory)
    schedule_store = ScheduleStore(session_factory)
    skill_store = SkillStore(session_factory)
    trajectory_logger = TrajectoryLogger(trajectory_store)

    # --- LLM: use ModelRouter if fallback models are configured ---
    llm: LLMClient | ModelRouter
    fallback_models = [
        m.strip() for m in cfg.llm_fallback_models.split(",") if m.strip()
    ]
    if fallback_models:
        all_models = [cfg.llm_model, *fallback_models]
        llm = ModelRouter(
            all_models,
            temperature=cfg.llm_temperature,
            max_tokens=cfg.llm_max_tokens,
            cooldown_s=cfg.llm_cooldown_s,
            max_consecutive_failures=cfg.llm_retry_attempts,
        )
        log.info("bootstrap.model_router", models=all_models)
    else:
        llm = LLMClient(
            model=cfg.llm_model,
            temperature=cfg.llm_temperature,
            max_tokens=cfg.llm_max_tokens,
        )

    http_executor = HttpExecutor(
        timeout_s=cfg.http_timeout_s,
        max_body_bytes=cfg.http_max_body_bytes,
        browser_fetch=cfg.enable_browser_fetch,
    )
    if cfg.enable_browser_fetch:
        log.info("bootstrap.browser_fetch_enabled")

    # --- Embedding memory ---
    embedding_provider = LiteLLMEmbeddingProvider(
        model=cfg.embedding_model,
        dimensions=cfg.embedding_dimensions,
    )
    embedding_store = EmbeddingMemoryStore(
        session_factory, embedding_provider
    )

    # --- Browser profiles ---
    browser_profile_manager: BrowserProfileManager | None = None
    if cfg.enable_browser_fetch:
        browser_profile_manager = BrowserProfileManager(cfg.browser_profiles_dir)
        log.info("bootstrap.browser_profiles_enabled")

    skill_registry = SkillRegistry()
    if load_builtin_skills:
        register_builtin_skills(skill_registry)

    # Reload forged skills persisted from previous runs.
    # Built-in skills already registered above take precedence — any DB row
    # whose name collides with a builtin is silently skipped.
    reloaded = await _reload_forged_skills(skill_store, skill_registry)
    if reloaded:
        log.info("bootstrap.skills_reloaded", count=reloaded)

    skill_executor = SkillExecutor(
        skill_registry,
        shadow_evaluator=ShadowEvaluator(),
        llm=llm,
        skill_store=skill_store,
    )
    routing_orchestrator = RoutingOrchestrator(
        registry=skill_registry,
        confidence_threshold=cfg.skill_confidence_threshold,
    )

    extraction_agent = ExtractionAgent(
        llm=llm,
        http=http_executor,
        trajectory_logger=trajectory_logger,
        orchestrator=routing_orchestrator,
        skill_executor=skill_executor,
    )

    synthesizer = SkillSynthesizer(llm)
    forge = SkillForge(synthesizer, skill_registry, skill_store=skill_store)
    failure_tracker = ForgeFailureTracker(memory_store)
    strategy_extractor = StrategyExtractor(
        llm, skill_registry, skill_store=skill_store
    )
    evolution_loop = EvolutionLoop(
        trajectory_store, forge, skill_registry,
        skill_store=skill_store,
        failure_tracker=failure_tracker,
        strategy_extractor=strategy_extractor,
    )

    # Tool registry + built-in tools
    tool_registry = ToolRegistry(
        skill_registry, min_confidence=cfg.skill_confidence_threshold
    )
    web_fetch_tool = WebFetchTool(http_executor)
    extract_tool = ExtractStructuredTool(extraction_agent)
    tool_registry.register_external(web_fetch_tool)
    tool_registry.register_external(extract_tool)
    tool_registry.register_external(FileReadTool())
    tool_registry.register_external(FileWriteTool())
    tool_registry.register_external(FileListTool())
    tool_registry.register_external(RememberTool(memory_store))
    tool_registry.register_external(RecallTool(memory_store))
    tool_registry.register_external(WatchTool(schedule_store))
    tool_registry.register_external(InboxTool(schedule_store))
    tool_registry.register_external(HttpApiTool())
    # Semantic recall via embedding store
    tool_registry.register_external(
        SemanticRecallTool(embedding_store, top_k=cfg.embedding_search_top_k)
    )
    # SendEmailTool only registers when SMTP is configured — self-checks env vars
    email_tool = SendEmailTool()
    if email_tool._is_configured():
        tool_registry.register_external(email_tool)
        log.info("bootstrap.email_tool_enabled")
    # ShellExecTool and PythonEvalTool execute arbitrary code/commands — only
    # register them when explicitly opted-in via config or env var.
    if cfg.enable_shell_tool:
        tool_registry.register_external(ShellExecTool())
        log.info("bootstrap.shell_tool_enabled")
    if cfg.enable_python_eval_tool:
        tool_registry.register_external(PythonEvalTool())
        log.info("bootstrap.python_eval_tool_enabled")

    # Claude Code external agent
    if cfg.enable_claude_code:
        from evosys.tools.external_agent import ClaudeCodeTool, _find_claude_binary
        claude_path = cfg.claude_code_path or _find_claude_binary()
        if claude_path:
            tool_registry.register_external(ClaudeCodeTool(
                claude_path=claude_path,
                timeout_s=cfg.claude_code_timeout_s,
                max_budget_usd=cfg.claude_code_max_budget_usd,
                model=cfg.claude_code_model,
                trajectory_logger=trajectory_logger,
            ))
            log.info("bootstrap.claude_code_enabled", path=claude_path)
        else:
            log.warning("bootstrap.claude_code_not_found")

    # MCP integration
    mcp_manager = MCPManager()
    try:
        mcp_configs = json.loads(cfg.mcp_servers)
        if isinstance(mcp_configs, list):
            for mcp_cfg_dict in mcp_configs:
                try:
                    mcp_config = MCPServerConfig(**mcp_cfg_dict)
                    tools = await mcp_manager.connect(mcp_config)
                    for tool in tools:
                        tool_registry.register_external(tool)
                except Exception:
                    log.exception("bootstrap.mcp_connect_failed")
    except (json.JSONDecodeError, TypeError):
        pass  # No valid MCP config

    # --- Sub-agent manager ---
    def _agent_factory(depth: int = 0) -> Agent:
        """Create a child agent at the given depth."""
        child_logger = TrajectoryLogger(trajectory_store)
        return Agent(
            llm=llm,
            tool_registry=tool_registry,
            trajectory_logger=child_logger,
            max_iterations=cfg.agent_max_iterations,
            system_prompt=cfg.agent_system_prompt,
            timeout_s=cfg.agent_timeout_s,
        )

    sub_agent_manager = SubAgentManager(
        _agent_factory,
        max_depth=cfg.sub_agent_max_depth,
        max_concurrent=cfg.sub_agent_max_concurrent,
    )
    tool_registry.register_external(SubAgentTool(sub_agent_manager))
    log.info(
        "bootstrap.sub_agent_enabled",
        max_depth=cfg.sub_agent_max_depth,
        max_concurrent=cfg.sub_agent_max_concurrent,
    )

    # General agent
    agent_logger = TrajectoryLogger(trajectory_store)
    general_agent = Agent(
        llm=llm,
        tool_registry=tool_registry,
        trajectory_logger=agent_logger,
        max_iterations=cfg.agent_max_iterations,
        system_prompt=cfg.agent_system_prompt,
        timeout_s=cfg.agent_timeout_s,
    )

    return EvoSysRuntime(
        config=cfg,
        engine=engine,
        session_factory=session_factory,
        trajectory_store=trajectory_store,
        memory_store=memory_store,
        schedule_store=schedule_store,
        skill_store=skill_store,
        trajectory_logger=trajectory_logger,
        llm=llm,
        http_executor=http_executor,
        skill_registry=skill_registry,
        skill_executor=skill_executor,
        routing_orchestrator=routing_orchestrator,
        extraction_agent=extraction_agent,
        synthesizer=synthesizer,
        forge=forge,
        evolution_loop=evolution_loop,
        tool_registry=tool_registry,
        general_agent=general_agent,
        mcp_manager=mcp_manager,
        embedding_store=embedding_store,
        sub_agent_manager=sub_agent_manager,
        browser_profile_manager=browser_profile_manager,
    )


async def _reload_forged_skills(
    skill_store: SkillStore,
    registry: SkillRegistry,
) -> int:
    """Reload previously forged skills from the DB into *registry*.

    Each persisted skill's source code is recompiled through the same
    ``_compile_extract`` path used by :class:`SkillForge`.  Skills whose
    name is already taken (built-ins loaded first) are silently skipped.
    Rows with corrupted code or incompatible schemas are skipped too —
    they will be re-forged naturally on the next evolution cycle.

    Returns the number of skills successfully reloaded.
    """
    from evosys.forge.forge import _compile_extract, _SynthesizedSkill

    persisted = await skill_store.load_all()
    reloaded = 0

    for ps in persisted:
        if ps.record.name in registry:
            # Built-in or already registered — skip without warning
            continue
        if not ps.source_code:
            continue

        extract_fn = _compile_extract(ps.source_code)
        if extract_fn is None:
            log.warning(
                "bootstrap.skill_recompile_failed",
                skill_name=ps.record.name,
            )
            continue

        skill = _SynthesizedSkill(extract_fn)
        try:
            registry.register(ps.record, skill)
            reloaded += 1
        except ValueError:
            # Shouldn't happen given the name check above, but be safe
            pass

    return reloaded
