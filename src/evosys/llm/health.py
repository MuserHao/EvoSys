"""Model health tracking — per-model cooldown and success/failure counters.

Used by :class:`ModelRouter` to decide which model to try next.
A model that fails repeatedly enters cooldown and is skipped until
the cooldown expires.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class ModelHealth:
    """Health state for a single LLM model.

    Tracks success/failure counts and applies a cooldown period after
    consecutive failures.  The router checks ``is_healthy`` before
    attempting a model.

    Parameters
    ----------
    model:
        LiteLLM model identifier.
    cooldown_s:
        Seconds to wait after ``max_consecutive_failures`` before retrying.
    max_consecutive_failures:
        Number of consecutive failures before entering cooldown.
    """

    model: str
    cooldown_s: float = 60.0
    max_consecutive_failures: int = 3

    successes: int = field(default=0, init=False)
    failures: int = field(default=0, init=False)
    consecutive_failures: int = field(default=0, init=False)
    last_failure_at: float = field(default=0.0, init=False)

    @property
    def is_healthy(self) -> bool:
        """Return ``True`` if the model is available (not in cooldown)."""
        if self.consecutive_failures < self.max_consecutive_failures:
            return True
        # In cooldown — check if enough time has passed
        elapsed = time.monotonic() - self.last_failure_at
        return elapsed >= self.cooldown_s

    def record_success(self) -> None:
        """Record a successful call — resets consecutive failure counter."""
        self.successes += 1
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed call — increments failure counters."""
        self.failures += 1
        self.consecutive_failures += 1
        self.last_failure_at = time.monotonic()

    def reset(self) -> None:
        """Reset all counters (e.g. after manual intervention)."""
        self.successes = 0
        self.failures = 0
        self.consecutive_failures = 0
        self.last_failure_at = 0.0
