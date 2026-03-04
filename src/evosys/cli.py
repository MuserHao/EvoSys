"""EvoSys CLI — the primary user interface."""

from __future__ import annotations

import asyncio
import json
import sys

import structlog
import typer
from rich.console import Console
from rich.table import Table

from evosys.agents.extraction_agent import ExtractionResult
from evosys.bootstrap import bootstrap
from evosys.config import EvoSysConfig

log = structlog.get_logger()
app = typer.Typer(name="evosys", help="EvoSys — self-evolving extraction agent.")
console = Console()


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
            str(entry.record.invocation_count),
        )

    console.print(table)


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


def main() -> None:
    """Entry point for the CLI."""
    app()
