"""FastAPI server — exposes EvoSys as a self-evolving HTTP service.

Starts a server with:
- POST /extract — structured data extraction from URLs
- POST /agent/run — general-purpose agent task execution
- GET /skills — list registered skills
- GET /status — system health and evolution metrics

A background task periodically runs evolution cycles.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from evosys.bootstrap import EvoSysRuntime, bootstrap
from evosys.config import EvoSysConfig
from evosys.loop import EvolutionLoop, EvolveCycleResult

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Shared runtime state (initialised in lifespan)
# ---------------------------------------------------------------------------

_runtime: EvoSysRuntime | None = None
_evolution_loop: EvolutionLoop | None = None
_evolution_task: asyncio.Task[None] | None = None
_last_evolve_result: EvolveCycleResult | None = None
_total_evolve_cycles: int = 0
_total_skills_forged: int = 0


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    url: str
    schema_description: str = "{}"
    system_prompt: str | None = None


class ExtractResponse(BaseModel):
    data: dict[str, Any]
    url: str
    token_cost: int
    total_latency_ms: float
    session_id: str
    skill_used: str | None = None


class AgentRunRequest(BaseModel):
    task: str
    context: dict[str, Any] | None = None


class AgentRunResponse(BaseModel):
    answer: str
    total_tokens: int
    total_latency_ms: float
    session_id: str
    iterations: int
    tool_calls_count: int


class SkillInfo(BaseModel):
    name: str
    status: str
    confidence_score: float
    implementation_type: str
    invocation_count: int
    description: str


class StatusResponse(BaseModel):
    version: str
    total_skills: int
    active_skills: int
    total_evolve_cycles: int
    total_skills_forged: int
    last_evolve_result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Background evolution scheduler
# ---------------------------------------------------------------------------


async def _evolution_worker(
    interval_seconds: float,
    min_frequency: int,
) -> None:
    """Periodically run evolution cycles in the background."""
    global _last_evolve_result, _total_evolve_cycles, _total_skills_forged

    while True:
        await asyncio.sleep(interval_seconds)

        if _evolution_loop is None:
            continue

        try:
            result = await _evolution_loop.run_cycle()
            _last_evolve_result = result
            _total_evolve_cycles += 1
            _total_skills_forged += result.forge_succeeded

            if result.forge_succeeded > 0:
                log.info(
                    "serve.evolution_forged",
                    new_skills=result.forge_succeeded,
                    total_forged=_total_skills_forged,
                    cycle=_total_evolve_cycles,
                )
            else:
                log.debug(
                    "serve.evolution_cycle",
                    candidates=result.candidates_found,
                    cycle=_total_evolve_cycles,
                )
        except Exception:
            log.exception("serve.evolution_error")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap EvoSys on startup, tear down on shutdown."""
    global _runtime, _evolution_loop, _evolution_task

    cfg = EvoSysConfig.from_env()
    _runtime = await bootstrap(cfg)

    # Reuse the EvolutionLoop already wired in bootstrap so there is only
    # ever one loop instance sharing the registry — avoids "already registered"
    # races when the background worker and POST /evolve run concurrently.
    _evolution_loop = _runtime.evolution_loop

    # Start background evolution (every 5 minutes)
    _evolution_task = asyncio.create_task(
        _evolution_worker(interval_seconds=300, min_frequency=3)
    )

    log.info(
        "serve.started",
        skills=len(_runtime.skill_registry),
        db=cfg.db_url,
    )

    yield

    # Shutdown
    if _evolution_task is not None:
        _evolution_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _evolution_task

    if _runtime is not None:
        await _runtime.shutdown()

    log.info("serve.stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EvoSys",
    description="Self-evolving general-purpose agent",
    version="0.1.0",
    lifespan=lifespan,
)


def _require_runtime() -> EvoSysRuntime:
    """Return the runtime or raise 503 if not yet initialised."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Server is still starting up.")
    return _runtime


def _require_evolution_loop() -> EvolutionLoop:
    if _evolution_loop is None:
        raise HTTPException(status_code=503, detail="Evolution loop not initialised.")
    return _evolution_loop


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest) -> ExtractResponse:
    """Extract structured data from a URL."""
    from evosys.agents.extraction_agent import ExtractionError

    rt = _require_runtime()
    try:
        result = await rt.extraction_agent.extract(
            url=req.url,
            target_schema=req.schema_description,
            system_prompt=req.system_prompt,
        )
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExtractResponse(
        data=dict(result.data),
        url=result.url,
        token_cost=result.token_cost,
        total_latency_ms=result.total_latency_ms,
        session_id=result.session_id,
        skill_used=result.skill_used,
    )


@app.post("/agent/run", response_model=AgentRunResponse)
async def agent_run(req: AgentRunRequest) -> AgentRunResponse:
    """Run the general-purpose agent on a task."""
    rt = _require_runtime()
    result = await rt.general_agent.run(
        task=req.task,
        context=req.context,
    )
    return AgentRunResponse(
        answer=result.answer,
        total_tokens=result.total_tokens,
        total_latency_ms=result.total_latency_ms,
        session_id=result.session_id,
        iterations=result.iterations,
        tool_calls_count=len(result.tool_calls_made),
    )


@app.get("/skills", response_model=list[SkillInfo])
async def list_skills() -> list[SkillInfo]:
    """List all registered skills."""
    rt = _require_runtime()
    entries = rt.skill_registry.list_all()
    return [
        SkillInfo(
            name=e.record.name,
            status=e.record.status.value,
            confidence_score=e.record.confidence_score,
            implementation_type=e.record.implementation_type.value,
            invocation_count=e.invocation_count,  # live counter on SkillEntry
            description=e.record.description,
        )
        for e in sorted(entries, key=lambda e: e.record.name)
    ]


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """System health and evolution metrics."""
    rt = _require_runtime()

    from evosys import __version__

    last = None
    if _last_evolve_result is not None:
        last = {
            "candidates_found": _last_evolve_result.candidates_found,
            "already_covered": _last_evolve_result.already_covered,
            "forge_attempted": _last_evolve_result.forge_attempted,
            "forge_succeeded": _last_evolve_result.forge_succeeded,
        }

    return StatusResponse(
        version=__version__,
        total_skills=len(rt.skill_registry),
        active_skills=len(rt.skill_registry.list_active()),
        total_evolve_cycles=_total_evolve_cycles,
        total_skills_forged=_total_skills_forged,
        last_evolve_result=last,
    )


@app.post("/evolve")
async def trigger_evolve() -> dict[str, Any]:
    """Manually trigger an evolution cycle."""
    loop = _require_evolution_loop()

    global _last_evolve_result, _total_evolve_cycles, _total_skills_forged

    result = await loop.run_cycle()
    _last_evolve_result = result
    _total_evolve_cycles += 1
    _total_skills_forged += result.forge_succeeded

    return {
        "candidates_found": result.candidates_found,
        "already_covered": result.already_covered,
        "forge_attempted": result.forge_attempted,
        "forge_succeeded": result.forge_succeeded,
        "new_skills": [s.name for s in result.new_skills],
    }
