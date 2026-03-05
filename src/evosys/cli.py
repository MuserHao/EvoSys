"""EvoSys CLI — the primary user interface."""

from __future__ import annotations

import asyncio
import json
import sys

import structlog
import typer
from rich.console import Console
from rich.table import Table

from evosys.agents.agent import AgentResult
from evosys.agents.extraction_agent import ExtractionResult
from evosys.bootstrap import bootstrap
from evosys.config import EvoSysConfig
from evosys.loop import EvolveCycleResult

log = structlog.get_logger()
app = typer.Typer(name="evosys", help="EvoSys — self-evolving general-purpose agent.")
console = Console()


# ---------------------------------------------------------------------------
# evosys run
# ---------------------------------------------------------------------------

@app.command("run")
def run_task(
    task: str = typer.Argument(help="Task description for the agent."),
    output_format: str = typer.Option(
        "pretty",
        "--format",
        "-f",
        help="Output format: json or pretty.",
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db",
        "--db",
        help="Database URL.",
    ),
    max_iterations: int = typer.Option(
        20,
        "--max-iter",
        help="Maximum agent loop iterations.",
    ),
    no_shell: bool = typer.Option(
        False,
        "--no-shell",
        help="Disable shell command execution.",
    ),
    no_python: bool = typer.Option(
        False,
        "--no-python",
        help="Disable Python code execution.",
    ),
    browser: bool = typer.Option(
        False,
        "--browser",
        help="Use a headless browser for web fetching (requires playwright).",
    ),
    session: str = typer.Option(
        "",
        "--session",
        help="Session name to load prior memory context from.",
    ),
) -> None:
    """Run the general-purpose agent on a task.

    Shell and Python execution are enabled by default for local use.
    Use --no-shell or --no-python to restrict the agent's capabilities.
    Use --browser for JavaScript-rendered sites
    (requires: uv sync --group browser && playwright install chromium).
    Use --session NAME to carry over memory from a previous named session.
    """
    cfg = EvoSysConfig(
        db_url=db_url,
        agent_max_iterations=max_iterations,
        enable_shell_tool=not no_shell,
        enable_python_eval_tool=not no_python,
        enable_browser_fetch=browser,
    )

    try:
        result = asyncio.run(_run_agent(cfg, task, session=session))
    except Exception as exc:
        console.print(f"[red]Agent failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if output_format == "pretty":
        console.print()
        console.print("[bold]Answer:[/bold]")
        console.print(result.answer)
        console.print()
        console.print(f"[dim]Session:[/dim]    {result.session_id}")
        console.print(f"[dim]Tokens:[/dim]     {result.total_tokens}")
        console.print(f"[dim]Latency:[/dim]    {result.total_latency_ms:.0f}ms")
        console.print(f"[dim]Iterations:[/dim] {result.iterations}")
        console.print(f"[dim]Tool calls:[/dim] {len(result.tool_calls_made)}")
    else:
        output = {
            "answer": result.answer,
            "total_tokens": result.total_tokens,
            "total_latency_ms": round(result.total_latency_ms, 1),
            "session_id": result.session_id,
            "iterations": result.iterations,
            "tool_calls_count": len(result.tool_calls_made),
        }
        sys.stdout.write(json.dumps(output, default=str, indent=2) + "\n")


async def _run_agent(cfg: EvoSysConfig, task: str, *, session: str = "") -> AgentResult:
    runtime = await bootstrap(cfg)
    try:
        context: dict[str, object] | None = None
        if session:
            # Load all keys from the named session namespace into context so
            # the agent starts with prior memory without explicit recall calls.
            keys = await runtime.memory_store.list_keys(namespace=session)
            if keys:
                remembered: dict[str, object] = {}
                for key in keys:
                    val = await runtime.memory_store.get(key, namespace=session)
                    if val is not None:
                        remembered[key] = val
                if remembered:
                    context = {"session": session, "memory": remembered}
        return await runtime.general_agent.run(task=task, context=context)
    finally:
        await runtime.shutdown()


# ---------------------------------------------------------------------------
# evosys extract
# ---------------------------------------------------------------------------

@app.command()
def extract(
    url: str = typer.Argument(help="URL to extract data from."),
    schema: str = typer.Option(
        "{}",
        "--schema",
        "-s",
        help="Target JSON schema description (string or @file path).",
    ),
    system_prompt: str | None = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Custom system prompt for the LLM.",
    ),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json or pretty.",
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db",
        "--db",
        help="Database URL.",
    ),
) -> None:
    """Extract structured data from a URL."""
    # Load schema from file if prefixed with @
    if schema.startswith("@"):
        path = schema[1:]
        try:
            with open(path) as f:
                schema = f.read()
        except FileNotFoundError as exc:
            console.print(f"[red]Schema file not found:[/red] {path}")
            raise typer.Exit(code=1) from exc

    cfg = EvoSysConfig(db_url=db_url)

    try:
        result = asyncio.run(_run_extract(cfg, url, schema, system_prompt))
    except Exception as exc:
        console.print(f"[red]Extraction failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if output_format == "pretty":
        console.print()
        if result.skill_used:
            console.print(f"[green]Skill used:[/green] {result.skill_used}")
        else:
            console.print("[yellow]Path:[/yellow] LLM extraction")
        console.print(f"[dim]URL:[/dim]        {result.url}")
        console.print(f"[dim]Tokens:[/dim]     {result.token_cost}")
        console.print(f"[dim]Latency:[/dim]    {result.total_latency_ms:.0f}ms")
        console.print(f"[dim]Session:[/dim]    {result.session_id}")
        console.print()
        console.print_json(json.dumps(result.data, default=str))
    else:
        output = {
            "data": result.data,
            "url": result.url,
            "token_cost": result.token_cost,
            "total_latency_ms": round(result.total_latency_ms, 1),
            "session_id": result.session_id,
            "skill_used": result.skill_used,
        }
        sys.stdout.write(json.dumps(output, default=str, indent=2) + "\n")


async def _run_extract(
    cfg: EvoSysConfig,
    url: str,
    schema: str,
    system_prompt: str | None,
) -> ExtractionResult:
    runtime = await bootstrap(cfg)
    try:
        return await runtime.agent.extract(
            url=url,
            target_schema=schema,
            system_prompt=system_prompt,
        )
    finally:
        await runtime.shutdown()


# ---------------------------------------------------------------------------
# evosys skills
# ---------------------------------------------------------------------------

skills_app = typer.Typer(name="skills", help="Manage the skill registry.")
app.add_typer(skills_app)


@skills_app.command("list")
def skills_list(
    active_only: bool = typer.Option(False, "--active", help="Show only active skills."),
) -> None:
    """List all registered skills."""
    from evosys.skills.loader import register_builtin_skills
    from evosys.skills.registry import SkillRegistry

    registry = SkillRegistry()
    register_builtin_skills(registry)

    entries = registry.list_active() if active_only else registry.list_all()
    if not entries:
        console.print("[dim]No skills registered.[/dim]")
        return

    table = Table(title="Skill Registry")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Confidence", justify="right")
    table.add_column("Type")
    table.add_column("Invocations", justify="right")

    for entry in sorted(entries, key=lambda e: e.record.name):
        table.add_row(
            entry.record.name,
            entry.record.status.value,
            f"{entry.record.confidence_score:.2f}",
            entry.record.implementation_type.value,
            str(entry.invocation_count),
        )

    console.print(table)


@skills_app.command("export")
def skills_export(
    name: str = typer.Argument(help="Skill name to export."),
    output_dir: str = typer.Option(".", "--output", "-o", help="Output directory."),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
    ),
) -> None:
    """Export a skill as a portable manifest."""
    try:
        result = asyncio.run(_export_skill(db_url, name, output_dir))
        console.print(f"[green]Exported:[/green] {result}")
    except Exception as exc:
        console.print(f"[red]Export failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


async def _export_skill(db_url: str, name: str, output_dir: str) -> str:
    from evosys.skills.marketplace import SkillMarketplace

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        mp = SkillMarketplace(runtime.skill_store, runtime.skill_registry)
        return await mp.export_skill(name, output_dir)
    finally:
        await runtime.shutdown()


@skills_app.command("import")
def skills_import(
    path: str = typer.Argument(help="Path to skill manifest file."),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
    ),
) -> None:
    """Import a skill from a manifest file."""
    try:
        result = asyncio.run(_import_skill(db_url, path))
        console.print(f"[green]Imported:[/green] {result}")
    except Exception as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


async def _import_skill(db_url: str, path: str) -> str:
    from evosys.skills.marketplace import SkillMarketplace

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        mp = SkillMarketplace(runtime.skill_store, runtime.skill_registry)
        return await mp.import_skill(path)
    finally:
        await runtime.shutdown()


@skills_app.command("search")
def skills_search(
    query: str = typer.Argument(help="Search query for skills."),
) -> None:
    """Search for skills (placeholder — searches local registry)."""
    from evosys.skills.loader import register_builtin_skills
    from evosys.skills.registry import SkillRegistry

    registry = SkillRegistry()
    register_builtin_skills(registry)

    q = query.lower()
    entries = [
        e for e in registry.list_all()
        if q in e.record.name.lower() or q in e.record.description.lower()
    ]

    if not entries:
        console.print(f"[dim]No skills matching '{query}'.[/dim]")
        return

    for e in entries:
        console.print(f"[cyan]{e.record.name}[/cyan] — {e.record.description}")


# ---------------------------------------------------------------------------
# evosys reflect
# ---------------------------------------------------------------------------

@app.command()
def reflect(
    min_frequency: int = typer.Option(
        3, "--min-freq", help="Minimum occurrences to consider a pattern."
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db",
        "--db",
        help="Database URL.",
    ),
) -> None:
    """Run a reflection cycle to discover skill candidates."""
    cfg = EvoSysConfig(db_url=db_url)

    try:
        candidates = asyncio.run(_run_reflect(cfg, min_frequency))
    except Exception as exc:
        console.print(f"[red]Reflection failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not candidates:
        console.print("[dim]No patterns found.[/dim]")
        return

    table = Table(title="Discovered Patterns")
    table.add_column("Domain", style="cyan")
    table.add_column("Frequency", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Status")

    for c in candidates:
        table.add_row(
            ", ".join(c.action_sequence),
            str(c.frequency),
            f"{c.boundary_confidence:.2f}",
            c.forge_status.value,
        )

    console.print(table)
    console.print(f"\n[green]{len(candidates)}[/green] candidate(s) found.")


async def _run_reflect(
    cfg: EvoSysConfig, min_frequency: int
) -> list:
    from evosys.reflection.daemon import ReflectionDaemon

    runtime = await bootstrap(cfg)
    try:
        daemon = ReflectionDaemon(
            runtime.trajectory_store, min_frequency=min_frequency
        )
        return await daemon.run_cycle()
    finally:
        await runtime.shutdown()


# ---------------------------------------------------------------------------
# evosys evolve
# ---------------------------------------------------------------------------

@app.command()
def evolve(
    min_frequency: int = typer.Option(
        3, "--min-freq", help="Minimum occurrences to consider a pattern."
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db",
        "--db",
        help="Database URL.",
    ),
) -> None:
    """Run one evolution cycle: reflect -> forge -> register."""
    cfg = EvoSysConfig(db_url=db_url)

    try:
        result = asyncio.run(_run_evolve(cfg, min_frequency))
    except Exception as exc:
        console.print(f"[red]Evolution cycle failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print()
    console.print("[bold]Evolution Cycle Complete[/bold]")
    console.print(f"  Patterns found:   {result.candidates_found}")
    console.print(f"  Already covered:  {result.already_covered}")
    console.print(f"  Forge attempted:  {result.forge_attempted}")
    console.print(f"  Forge succeeded:  {result.forge_succeeded}")

    if result.new_skills:
        console.print()
        table = Table(title="New Skills Forged")
        table.add_column("Name", style="cyan")
        table.add_column("Confidence", justify="right")
        table.add_column("Pass Rate", justify="right")

        for skill in result.new_skills:
            table.add_row(
                skill.name,
                f"{skill.confidence_score:.2f}",
                f"{skill.pass_rate:.2f}",
            )

        console.print(table)
    elif result.candidates_found == 0:
        console.print("\n[dim]No patterns found. Run more extractions first.[/dim]")
    else:
        console.print("\n[dim]No new skills forged this cycle.[/dim]")


async def _run_evolve(
    cfg: EvoSysConfig, min_frequency: int
) -> EvolveCycleResult:
    runtime = await bootstrap(cfg)
    try:
        return await runtime.evolution_loop.run_cycle()
    finally:
        await runtime.shutdown()


# ---------------------------------------------------------------------------
# evosys info
# ---------------------------------------------------------------------------

@app.command()
def info() -> None:
    """Show EvoSys version and configuration."""
    from evosys import __version__

    cfg = EvoSysConfig.from_env()
    console.print(f"[bold]EvoSys[/bold] v{__version__}")
    console.print(f"  LLM model:      {cfg.llm_model}")
    console.print(f"  DB URL:         {cfg.db_url}")
    console.print(f"  HTTP timeout:   {cfg.http_timeout_s}s")
    console.print(f"  Skill threshold:{cfg.skill_confidence_threshold}")
    if cfg.llm_fallback_models:
        console.print(f"  Fallback models:{cfg.llm_fallback_models}")
    console.print(f"  Slack enabled:  {cfg.slack_enabled}")
    console.print(f"  Web chat:       {cfg.web_chat_enabled}")


# ---------------------------------------------------------------------------
# evosys serve
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address."),
    port: int = typer.Option(8000, "--port", help="Listen port."),
    evolve_interval: int = typer.Option(
        300,
        "--evolve-interval",
        help="Seconds between background evolution cycles.",
    ),
) -> None:
    """Start the EvoSys HTTP server with background evolution."""
    import uvicorn

    console.print("[bold]Starting EvoSys server...[/bold]")
    console.print(f"  Host:             {host}:{port}")
    console.print(f"  Evolve interval:  {evolve_interval}s")
    console.print()
    console.print("Endpoints:")
    console.print("  POST /extract    — extract structured data from a URL")
    console.print("  POST /agent/run  — run the general-purpose agent")
    console.print("  GET  /skills     — list registered skills")
    console.print("  GET  /status     — system health & evolution metrics")
    console.print("  POST /evolve     — manually trigger an evolution cycle")
    console.print("  WS   /ws/chat    — real-time WebSocket chat")
    console.print()

    uvicorn.run(
        "evosys.server:app",
        host=host,
        port=port,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# evosys slack
# ---------------------------------------------------------------------------

@app.command()
def slack() -> None:
    """Start the Slack bot (Socket Mode).

    Requires EVOSYS_SLACK_BOT_TOKEN and EVOSYS_SLACK_APP_TOKEN env vars.
    """
    cfg = EvoSysConfig.from_env()
    if not cfg.slack_bot_token or not cfg.slack_app_token:
        console.print(
            "[red]Missing Slack tokens.[/red] Set EVOSYS_SLACK_BOT_TOKEN "
            "and EVOSYS_SLACK_APP_TOKEN environment variables."
        )
        raise typer.Exit(code=1)

    console.print("[bold]Starting EvoSys Slack bot...[/bold]")
    asyncio.run(_run_slack(cfg))


async def _run_slack(cfg: EvoSysConfig) -> None:
    from evosys.channels.slack.bot import SlackBot

    runtime = await bootstrap(cfg)
    bot = SlackBot(cfg, runtime.general_agent)
    try:
        await bot.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.stop()
        await runtime.shutdown()


# ---------------------------------------------------------------------------
# evosys chat
# ---------------------------------------------------------------------------

@app.command()
def chat(
    session_name: str = typer.Option(
        "",
        "--session",
        help="Session name to persist conversation history.",
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db",
        "--db",
        help="Database URL.",
    ),
) -> None:
    """Start an interactive conversation with EvoSys.

    Messages accumulate in context. Use --session to persist across restarts.
    """
    try:
        asyncio.run(_run_chat(db_url, session_name))
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Goodbye![/dim]")


async def _run_chat(db_url: str, session_name: str) -> None:
    from evosys.channels.cli_chat import CLIChatSession

    cfg = EvoSysConfig(
        db_url=db_url,
        enable_shell_tool=True,
        enable_python_eval_tool=True,
    )
    runtime = await bootstrap(cfg)
    try:
        session = CLIChatSession(
            agent=runtime.general_agent,
            memory_store=runtime.memory_store,
            session_name=session_name,
        )
        await session.run()
    finally:
        await runtime.shutdown()


def main() -> None:
    """Entry point for the CLI."""
    app()
