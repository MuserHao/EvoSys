"""Application-level configuration for EvoSys."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvoSysConfig:
    """Plain configuration object — no pydantic-settings dependency."""

    db_url: str = "sqlite+aiosqlite:///data/evosys.db"
    llm_model: str = "anthropic/claude-sonnet-4-20250514"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    http_timeout_s: float = 30.0
    http_max_body_bytes: int = 5_000_000
    skill_confidence_threshold: float = 0.7
    agent_max_iterations: int = 20
    agent_system_prompt: str = (
        "You are a capable general-purpose assistant with access to tools. "
        "You can read and write local files, execute Python code for data "
        "analysis and processing, run shell commands, search the web, and "
        "remember information across sessions. "
        "Always use tools to accomplish tasks — read files before summarising "
        "them, write Python to analyse data rather than reasoning about it "
        "verbally, use shell commands to inspect the system. "
        "Think step by step. When you have enough information to answer, "
        "respond directly without calling more tools."
    )
    mcp_servers: str = "[]"
    # Opt-in flags for tools that can execute arbitrary code or shell commands.
    # Disabled by default to avoid accidental destructive operations.
    enable_shell_tool: bool = False
    enable_python_eval_tool: bool = False
    # Use Playwright for fetching JavaScript-rendered pages.
    # Requires: uv sync --group browser && playwright install chromium
    enable_browser_fetch: bool = False
    # Wall-clock timeout for a single agent.run() call (seconds).
    # None means no timeout.
    agent_timeout_s: float | None = None

    @classmethod
    def from_env(cls) -> EvoSysConfig:
        """Build config from ``EVOSYS_*`` environment variables."""
        kwargs: dict[str, object] = {}
        if v := os.environ.get("EVOSYS_DB_URL"):
            kwargs["db_url"] = v
        if v := os.environ.get("EVOSYS_LLM_MODEL"):
            kwargs["llm_model"] = v
        if v := os.environ.get("EVOSYS_LLM_TEMPERATURE"):
            kwargs["llm_temperature"] = float(v)
        if v := os.environ.get("EVOSYS_LLM_MAX_TOKENS"):
            kwargs["llm_max_tokens"] = int(v)
        if v := os.environ.get("EVOSYS_HTTP_TIMEOUT_S"):
            kwargs["http_timeout_s"] = float(v)
        if v := os.environ.get("EVOSYS_HTTP_MAX_BODY_BYTES"):
            kwargs["http_max_body_bytes"] = int(v)
        if v := os.environ.get("EVOSYS_SKILL_CONFIDENCE_THRESHOLD"):
            kwargs["skill_confidence_threshold"] = float(v)
        if v := os.environ.get("EVOSYS_AGENT_MAX_ITERATIONS"):
            kwargs["agent_max_iterations"] = int(v)
        if v := os.environ.get("EVOSYS_AGENT_SYSTEM_PROMPT"):
            kwargs["agent_system_prompt"] = v
        if v := os.environ.get("EVOSYS_MCP_SERVERS"):
            kwargs["mcp_servers"] = v
        if v := os.environ.get("EVOSYS_ENABLE_SHELL_TOOL"):
            kwargs["enable_shell_tool"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_ENABLE_PYTHON_EVAL_TOOL"):
            kwargs["enable_python_eval_tool"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_ENABLE_BROWSER_FETCH"):
            kwargs["enable_browser_fetch"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_AGENT_TIMEOUT_S"):
            kwargs["agent_timeout_s"] = float(v)
        return cls(**kwargs)  # type: ignore[arg-type]
