"""EvoSys CLI — the primary user interface.

Three modes:
  evosys                      → interactive chat (default)
  evosys "do something"       → one-shot agent, prints answer, exits
  evosys serve [--port]       → long-running server (HTTP + Slack + WebSocket)

Subcommands:
  evosys info                 → version and configuration
  evosys evolve               → run one evolution cycle
  evosys reflect              → discover skill candidates
  evosys skills list|export|import|search → manage skill registry

Use ``--`` to force task mode when the first word collides with a subcommand:
  evosys -- serve me a joke   → one-shot task, NOT the serve command
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import click
import structlog
import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from evosys.agents.agent import AgentResult
from evosys.bootstrap import bootstrap
from evosys.config import EvoSysConfig
from evosys.loop import EvolveCycleResult

log = structlog.get_logger()
console = Console()

# ---------------------------------------------------------------------------
# API key detection helpers
# ---------------------------------------------------------------------------

_API_KEY_PROVIDERS: list[tuple[str, str]] = [
    ("ANTHROPIC_API_KEY", "Claude"),
    ("GOOGLE_API_KEY", "Gemini"),
    ("OPENAI_API_KEY", "GPT"),
]


def _detect_api_keys() -> list[tuple[str, str, bool]]:
    """Return (env_var, label, is_set) for each known provider."""
    return [
        (env_var, label, bool(os.environ.get(env_var)))
        for env_var, label in _API_KEY_PROVIDERS
    ]


# ---------------------------------------------------------------------------
# Custom Click group: treats unrecognised positional args as a task string
# ---------------------------------------------------------------------------

class TaskOrCommandGroup(TyperGroup):
    """Click group that dispatches known subcommands normally and captures
    everything else as a one-shot task string in ``ctx.obj["task"]``.

    This lets ``evosys "any text here"`` work without conflicting with
    ``evosys serve`` or ``evosys info``.

    The ``--`` separator forces task mode — everything after it becomes the
    task string, even if the first word is a known subcommand.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If no args at all, let Click dispatch to the callback (chat mode).
        if not args:
            return super().parse_args(ctx, args)

        # If --help / -h is present, let Click handle it natively.
        if "--help" in args or "-h" in args:
            return super().parse_args(ctx, args)

        # Handle ``--`` separator: everything after it is the task string.
        if "--" in args:
            sep_idx = args.index("--")
            before = args[:sep_idx]
            after = args[sep_idx + 1:]
            if after:
                ctx.ensure_object(dict)
                ctx.obj["task"] = " ".join(after)
                # Parse only the tokens before ``--`` so Click handles options.
                return super().parse_args(ctx, before)
            # ``--`` with nothing after it — fall through to normal dispatch.

        # Build a lookup of known option flags and whether they consume a value.
        opt_info: dict[str, bool] = {}  # flag_string -> consumes_value
        for p in self.params or []:
            if isinstance(p, click.Option):
                consumes = p.nargs > 0 and not p.is_flag
                for name in p.opts + p.secondary_opts:
                    opt_info[name] = consumes

        # Separate all tokens into option tokens and positional tokens.
        option_tokens: list[str] = []
        positional_tokens: list[str] = []
        i = 0
        while i < len(args):
            token = args[i]
            if token.startswith("-") and token in opt_info:
                option_tokens.append(token)
                if opt_info[token]:
                    # This option consumes the next arg as its value.
                    i += 1
                    if i < len(args):
                        option_tokens.append(args[i])
            elif token.startswith("-") and "=" in token:
                # Handle --key=value form
                key = token.split("=", 1)[0]
                if key in opt_info:
                    option_tokens.append(token)
                else:
                    positional_tokens.append(token)
            elif token.startswith("-"):
                # Unknown flag — treat as positional (part of task text)
                positional_tokens.append(token)
            else:
                positional_tokens.append(token)
            i += 1

        # If first positional is a known subcommand, dispatch normally.
        if positional_tokens and positional_tokens[0] in (self.commands or {}):
            return super().parse_args(ctx, args)

        # If there are positional tokens that aren't subcommands, treat as task.
        if positional_tokens:
            ctx.ensure_object(dict)
            ctx.obj["task"] = " ".join(positional_tokens)
            # Parse only the option tokens so Click handles --db etc.
            return super().parse_args(ctx, option_tokens)

        # All tokens were options → normal dispatch (callback will enter chat)
        return super().parse_args(ctx, args)


# ---------------------------------------------------------------------------
# Top-level app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="evosys",
    cls=TaskOrCommandGroup,
    help="EvoSys — self-evolving general-purpose agent.",
    invoke_without_command=True,
    no_args_is_help=False,
)


# ---------------------------------------------------------------------------
# Skills sub-app (directly on top-level, no admin prefix)
# ---------------------------------------------------------------------------

skills_app = typer.Typer(name="skills", help="Manage the skill registry.")
app.add_typer(skills_app)


# ---------------------------------------------------------------------------
# --version callback
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        from evosys import __version__

        typer.echo(f"evosys {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Unified callback — chat or one-shot
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    output_format: str = typer.Option(
        "pretty", "--format", "-f", help="Output format: json or pretty."
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
    ),
    session: str = typer.Option(
        "", "--session", help="Session name to load prior memory context from."
    ),
    no_shell: bool = typer.Option(
        False, "--no-shell", help="Disable shell command execution."
    ),
    no_python: bool = typer.Option(
        False, "--no-python", help="Disable Python code execution."
    ),
    browser: bool = typer.Option(
        False,
        "--browser",
        help="Use a headless browser for web fetching (requires playwright).",
    ),
    max_iterations: int = typer.Option(
        20, "--max-iter", help="Maximum agent loop iterations."
    ),
) -> None:
    """Talk to EvoSys.

    With no arguments, starts an interactive chat session.
    With a task string, runs the agent once and exits.

    Examples:
      evosys                        # interactive chat
      evosys "summarize this repo"  # one-shot agent
      evosys --format json "2+2"   # one-shot, JSON output
      evosys -- serve me a joke    # force task mode (not the serve command)
    """
    # If a subcommand was invoked, do nothing here.
    if ctx.invoked_subcommand is not None:
        return

    ctx.ensure_object(dict)
    task: str | None = ctx.obj.get("task")

    if task:
        # --- One-shot mode ---
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
            _handle_run_error(exc)

        _print_agent_result(result, output_format)
    else:
        # --- Interactive chat mode ---
        _show_welcome()
        try:
            asyncio.run(_run_chat(db_url, session))
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")


# ---------------------------------------------------------------------------
# evosys serve
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address."),
    port: int = typer.Option(8000, "--port", help="Listen port."),
    evolve_interval: int = typer.Option(
        300, "--evolve-interval", help="Seconds between background evolution cycles."
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
# evosys mcp-serve
# ---------------------------------------------------------------------------

@app.command("mcp-serve")
def mcp_serve(
    db_url: str = typer.Option(
        "", "--db", help="Database URL (empty = use env/default)."
    ),
) -> None:
    """Start an MCP server on stdio for external agent integration.

    Exposes EvoSys skills and tools via the Model Context Protocol so
    that Claude Code, Cursor, or any MCP client can use them.  Every
    invocation logs a trajectory, feeding the evolution loop.

    Configure in Claude Code settings.json:

      "mcpServers": {
        "evosys": {"command": "evosys", "args": ["mcp-serve"]}
      }
    """
    from evosys.mcp_server import run_mcp_server

    asyncio.run(run_mcp_server(db_url))


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
# evosys status
# ---------------------------------------------------------------------------

@app.command()
def status(
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
    ),
) -> None:
    """Show learning status: skills, trajectory stats, and evolution metrics."""
    from evosys import __version__

    try:
        data = asyncio.run(_run_status(db_url))
    except Exception as exc:
        console.print(f"[red]Status failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print()
    console.print(f"[bold]EvoSys[/bold] v{__version__} — Learning Status")
    console.print()

    console.print("[bold]Skills[/bold]")
    console.print(f"  Active:       {data['active_skills']}")
    console.print(f"  Forged:       {data['forged_skills']}")
    console.print(f"  Built-in:     {data['builtin_skills']}")
    console.print()

    console.print("[bold]Trajectories[/bold]")
    console.print(f"  Total records: {data['total_trajectories']}")
    console.print(f"  Tool calls:    {data['tool_trajectories']}")
    console.print(f"  Domains seen:  {data['domains_seen']}")
    console.print()

    console.print("[bold]Learning[/bold]")
    if data['top_domains']:
        for domain, count in data['top_domains'][:5]:
            console.print(f"  {domain}: {count} extractions")
    else:
        console.print("  [dim]No extraction patterns yet.[/dim]")
    console.print()

    if data['forged_skill_names']:
        console.print("[bold]Forged Skills[/bold]")
        for name, conf in data['forged_skill_names']:
            console.print(
                f"  [cyan]{name}[/cyan] "
                f"(confidence: {conf:.2f})"
            )
        console.print()


# ---------------------------------------------------------------------------
# evosys ingest
# ---------------------------------------------------------------------------

@app.command()
def ingest(
    claude_dir: str = typer.Option(
        "",
        "--claude-dir",
        help="Claude Code projects directory (default: ~/.claude/projects).",
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
    ),
    evolve: bool = typer.Option(
        True, "--evolve/--no-evolve",
        help="Run evolution cycle after ingestion.",
    ),
) -> None:
    """Ingest Claude Code conversation logs into EvoSys.

    Reads JSONL transcripts from ~/.claude/projects/, extracts tool
    calls, and converts them to trajectory records.  The evolution
    loop can then learn from your Claude Code sessions.

    Only new (previously un-ingested) files are processed.
    """
    try:
        asyncio.run(_run_ingest(db_url, claude_dir, evolve))
    except Exception as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# evosys reflect
# ---------------------------------------------------------------------------

@app.command()
def reflect(
    min_frequency: int = typer.Option(
        3, "--min-freq", help="Minimum occurrences to consider a pattern."
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
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


# ---------------------------------------------------------------------------
# evosys evolve
# ---------------------------------------------------------------------------

@app.command()
def evolve(
    min_frequency: int = typer.Option(
        3, "--min-freq", help="Minimum occurrences to consider a pattern."
    ),
    db_url: str = typer.Option(
        "sqlite+aiosqlite:///data/evosys.db", "--db", help="Database URL."
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


# ---------------------------------------------------------------------------
# evosys skills *
# ---------------------------------------------------------------------------

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
        e
        for e in registry.list_all()
        if q in e.record.name.lower() or q in e.record.description.lower()
    ]

    if not entries:
        console.print(f"[dim]No skills matching '{query}'.[/dim]")
        return

    for e in entries:
        console.print(f"[cyan]{e.record.name}[/cyan] — {e.record.description}")


# ---------------------------------------------------------------------------
# Helpers (shared async runners)
# ---------------------------------------------------------------------------

def _handle_run_error(exc: Exception) -> None:
    """Print a user-friendly error and exit.

    Catches LLM authentication errors (missing API key) specially.
    """
    msg = str(exc)
    if "AuthenticationError" in type(exc).__name__ or "AuthenticationError" in msg:
        console.print(
            "[red]No API key found.[/red] "
            "Set one of: ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY"
        )
        raise typer.Exit(code=1) from exc

    console.print(f"[red]Agent failed:[/red] {exc}")
    raise typer.Exit(code=1) from exc


def _print_agent_result(result: AgentResult, output_format: str) -> None:
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
        # Show which tools were used
        if result.tool_calls_made:
            tool_names = [tc.tool_name for tc in result.tool_calls_made]
            tool_summary = ", ".join(dict.fromkeys(tool_names))
            console.print(f"[dim]Tools used:[/dim] {tool_summary}")
        # Highlight skill usage
        skill_tools = [
            tc.tool_name for tc in result.tool_calls_made
            if tc.tool_name.startswith(("extract:", "composite:", "strategy:"))
        ]
        if skill_tools:
            console.print(
                f"[green]Skills used:[/green] {', '.join(skill_tools)} "
                f"[dim](forged — $0 LLM cost)[/dim]"
            )
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


def _show_welcome() -> None:
    """Show a status-aware welcome banner on every chat entry."""
    from evosys import __version__

    cfg = EvoSysConfig.from_env()
    keys = _detect_api_keys()
    any_set = any(is_set for _, _, is_set in keys)

    console.print()
    console.print(f"[bold]EvoSys[/bold] v{__version__} — self-evolving general-purpose agent")
    console.print()

    console.print("  LLM providers (set any one):")
    for env_var, label, is_set in keys:
        mark = "[green]\u2713[/green]" if is_set else "[dim]\u2717[/dim]"
        pad = " " * (24 - len(env_var))
        console.print(f"    {mark} {env_var}{pad}{label}")

    if not any_set:
        console.print()
        console.print(
            "  [yellow]Warning:[/yellow] No API key set. "
            "Set one of the above to get started."
        )

    console.print()
    console.print(f"  Model: {cfg.llm_model}")
    console.print()
    console.print("  Quick start:")
    console.print('    evosys "what can you do?"   run a task')
    console.print("    evosys                       interactive chat")
    console.print("    evosys serve                 HTTP + WebSocket server")
    console.print()
    console.print("  Docs: [link]https://github.com/MuserHao/EvoSys[/link]")
    console.print()


async def _run_agent(
    cfg: EvoSysConfig, task: str, *, session: str = ""
) -> AgentResult:
    runtime = await bootstrap(cfg)
    try:
        context: dict[str, object] | None = None
        if session:
            keys = await runtime.memory_store.list_keys(namespace=session)
            if keys:
                remembered: dict[str, object] = {}
                for key in keys:
                    val = await runtime.memory_store.get(key, namespace=session)
                    if val is not None:
                        remembered[key] = val
                if remembered:
                    context = {"session": session, "memory": remembered}
        result = await runtime.general_agent.run(task=task, context=context)

        # Opportunistic evolution: after each task, try to evolve
        try:
            evolve_result = await runtime.evolution_loop.run_cycle()
            if evolve_result.forge_succeeded > 0:
                console.print()
                console.print(
                    f"[bold cyan]Learned:[/bold cyan] "
                    f"Forged {evolve_result.forge_succeeded} new skill(s)"
                )
                for skill in evolve_result.new_skills:
                    console.print(
                        f"  [cyan]{skill.name}[/cyan] "
                        f"(confidence: {skill.confidence_score:.2f})"
                    )
            if evolve_result.strategies_extracted > 0:
                console.print(
                    f"  + {evolve_result.strategies_extracted} "
                    f"strategy(ies) extracted"
                )
        except Exception:
            pass  # evolution failure is non-fatal

        return result
    finally:
        await runtime.shutdown()


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


async def _run_reflect(cfg: EvoSysConfig, min_frequency: int) -> list[Any]:
    from evosys.reflection.daemon import ReflectionDaemon

    runtime = await bootstrap(cfg)
    try:
        daemon = ReflectionDaemon(
            runtime.trajectory_store, min_frequency=min_frequency
        )
        return await daemon.run_cycle()
    finally:
        await runtime.shutdown()


async def _run_evolve(cfg: EvoSysConfig, min_frequency: int) -> EvolveCycleResult:
    runtime = await bootstrap(cfg)
    try:
        return await runtime.evolution_loop.run_cycle()
    finally:
        await runtime.shutdown()


async def _export_skill(db_url: str, name: str, output_dir: str) -> str:
    from evosys.skills.marketplace import SkillMarketplace

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        mp = SkillMarketplace(runtime.skill_store, runtime.skill_registry)
        return await mp.export_skill(name, output_dir)
    finally:
        await runtime.shutdown()


async def _import_skill(db_url: str, path: str) -> str:
    from evosys.skills.marketplace import SkillMarketplace

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        mp = SkillMarketplace(runtime.skill_store, runtime.skill_registry)
        return await mp.import_skill(path)
    finally:
        await runtime.shutdown()


async def _run_status(db_url: str) -> dict[str, Any]:
    """Gather learning status data."""
    from datetime import timedelta

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        all_entries = runtime.skill_registry.list_all()
        active_entries = runtime.skill_registry.list_active()

        forged = [
            e for e in all_entries
            if e.record.implementation_path.startswith("forge:")
        ]
        builtin = len(all_entries) - len(forged)

        # Trajectory stats
        from datetime import UTC, datetime
        since = datetime.now(UTC) - timedelta(days=365)
        recent = await runtime.trajectory_store.get_recent(since=since, limit=50000)
        tool_recs = [r for r in recent if r.action_name.startswith("tool:")]

        # Domain extraction stats
        domains = await runtime.trajectory_store.get_llm_extractions_by_domain()
        top_domains = sorted(
            [(d, len(recs)) for d, recs in domains.items()],
            key=lambda x: x[1],
            reverse=True,
        )

        forged_names = [
            (e.record.name, e.record.confidence_score)
            for e in forged
        ]

        return {
            "active_skills": len(active_entries),
            "forged_skills": len(forged),
            "builtin_skills": builtin,
            "total_trajectories": len(recent),
            "tool_trajectories": len(tool_recs),
            "domains_seen": len(domains),
            "top_domains": top_domains,
            "forged_skill_names": forged_names,
        }
    finally:
        await runtime.shutdown()


async def _run_ingest(db_url: str, claude_dir: str, run_evolve: bool) -> None:
    """Run Claude Code log ingestion."""
    from pathlib import Path

    from evosys.ingest.claude_code_ingest import ClaudeCodeIngestor

    cfg = EvoSysConfig(db_url=db_url)
    runtime = await bootstrap(cfg)
    try:
        kwargs: dict[str, Any] = {}
        if claude_dir:
            kwargs["claude_dir"] = Path(claude_dir)

        ingestor = ClaudeCodeIngestor(
            runtime.trajectory_store,
            runtime.memory_store,
            **kwargs,
        )

        console.print("[bold]Ingesting Claude Code logs...[/bold]")
        stats = await ingestor.ingest_all()

        console.print()
        console.print(f"  Files scanned:  {stats.files_scanned}")
        console.print(f"  New files:      {stats.files_new}")
        console.print(f"  Tool calls:     {stats.tool_calls_ingested}")
        console.print(f"  Sessions:       {stats.sessions_ingested}")
        if stats.errors > 0:
            console.print(f"  [yellow]Errors:[/yellow]  {stats.errors}")

        if stats.tool_calls_ingested == 0:
            if stats.files_new == 0:
                console.print(
                    "\n[dim]All files already ingested. "
                    "Use Claude Code to create new sessions.[/dim]"
                )
            else:
                console.print(
                    "\n[dim]No tool calls found in new files.[/dim]"
                )
            return

        # Run evolution cycle after ingestion
        if run_evolve:
            console.print("\n[bold]Running evolution cycle...[/bold]")
            result = await runtime.evolution_loop.run_cycle()
            console.print(f"  Patterns found: {result.candidates_found}")
            console.print(f"  Forge attempted: {result.forge_attempted}")
            console.print(f"  Forge succeeded: {result.forge_succeeded}")
            if result.new_skills:
                console.print()
                for skill in result.new_skills:
                    console.print(
                        f"  [bold cyan]New skill:[/bold cyan] "
                        f"[cyan]{skill.name}[/cyan] "
                        f"(confidence: {skill.confidence_score:.2f})"
                    )
    finally:
        await runtime.shutdown()


def main() -> None:
    """Entry point for the CLI."""
    app()
