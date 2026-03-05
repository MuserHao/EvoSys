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

    # --- Embedding memory (Phase 1.1) ---
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_search_top_k: int = 5

    # --- LLM failover (Phase 1.2) ---
    # Comma-separated fallback model list. Primary model is llm_model above.
    llm_fallback_models: str = ""
    llm_retry_attempts: int = 2
    llm_cooldown_s: float = 60.0

    # --- Sub-agent (Phase 1.3) ---
    sub_agent_max_depth: int = 2
    sub_agent_max_concurrent: int = 3

    # --- Browser profiles (Phase 1.4) ---
    browser_profiles_dir: str = "data/browser_profiles"

    # --- Slack (Phase 2.1) ---
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_enabled: bool = False
    slack_reply_in_thread: bool = True

    # --- Web chat (Phase 2.2) ---
    web_chat_enabled: bool = False

    # --- Local models (Phase 3.1) ---
    local_model_enabled: bool = False
    local_model_ollama_base: str = "http://localhost:11434"

    # --- Skill re-forge (Phase 3.2) ---
    reforge_enabled: bool = True
    reforge_min_samples: int = 3

    # --- Auth (Phase 4.2) ---
    auth_enabled: bool = False
    auth_token: str = ""

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
        # Embedding memory
        if v := os.environ.get("EVOSYS_EMBEDDING_MODEL"):
            kwargs["embedding_model"] = v
        if v := os.environ.get("EVOSYS_EMBEDDING_DIMENSIONS"):
            kwargs["embedding_dimensions"] = int(v)
        if v := os.environ.get("EVOSYS_EMBEDDING_SEARCH_TOP_K"):
            kwargs["embedding_search_top_k"] = int(v)
        # LLM failover
        if v := os.environ.get("EVOSYS_LLM_FALLBACK_MODELS"):
            kwargs["llm_fallback_models"] = v
        if v := os.environ.get("EVOSYS_LLM_RETRY_ATTEMPTS"):
            kwargs["llm_retry_attempts"] = int(v)
        if v := os.environ.get("EVOSYS_LLM_COOLDOWN_S"):
            kwargs["llm_cooldown_s"] = float(v)
        # Sub-agent
        if v := os.environ.get("EVOSYS_SUB_AGENT_MAX_DEPTH"):
            kwargs["sub_agent_max_depth"] = int(v)
        if v := os.environ.get("EVOSYS_SUB_AGENT_MAX_CONCURRENT"):
            kwargs["sub_agent_max_concurrent"] = int(v)
        # Browser profiles
        if v := os.environ.get("EVOSYS_BROWSER_PROFILES_DIR"):
            kwargs["browser_profiles_dir"] = v
        # Slack
        if v := os.environ.get("EVOSYS_SLACK_BOT_TOKEN"):
            kwargs["slack_bot_token"] = v
        if v := os.environ.get("EVOSYS_SLACK_APP_TOKEN"):
            kwargs["slack_app_token"] = v
        if v := os.environ.get("EVOSYS_SLACK_ENABLED"):
            kwargs["slack_enabled"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_SLACK_REPLY_IN_THREAD"):
            kwargs["slack_reply_in_thread"] = v.lower() in {"1", "true", "yes"}
        # Web chat
        if v := os.environ.get("EVOSYS_WEB_CHAT_ENABLED"):
            kwargs["web_chat_enabled"] = v.lower() in {"1", "true", "yes"}
        # Local models
        if v := os.environ.get("EVOSYS_LOCAL_MODEL_ENABLED"):
            kwargs["local_model_enabled"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_LOCAL_MODEL_OLLAMA_BASE"):
            kwargs["local_model_ollama_base"] = v
        # Skill re-forge
        if v := os.environ.get("EVOSYS_REFORGE_ENABLED"):
            kwargs["reforge_enabled"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_REFORGE_MIN_SAMPLES"):
            kwargs["reforge_min_samples"] = int(v)
        # Auth
        if v := os.environ.get("EVOSYS_AUTH_ENABLED"):
            kwargs["auth_enabled"] = v.lower() in {"1", "true", "yes"}
        if v := os.environ.get("EVOSYS_AUTH_TOKEN"):
            kwargs["auth_token"] = v
        return cls(**kwargs)  # type: ignore[arg-type]
