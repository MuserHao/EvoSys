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
        return cls(**kwargs)  # type: ignore[arg-type]
