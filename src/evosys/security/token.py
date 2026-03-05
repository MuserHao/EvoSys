"""Auto-generated Bearer token for API authentication.

On first startup (when no token exists), generates a random token
and persists it to a file.  Subsequent startups read from the file.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import structlog

log = structlog.get_logger()

_DEFAULT_TOKEN_PATH = "data/.evosys_token"


def get_or_create_token(
    token_path: str = _DEFAULT_TOKEN_PATH,
    *,
    explicit_token: str = "",
) -> str:
    """Return the API token, creating one if it doesn't exist.

    If *explicit_token* is set (e.g. from config), use that.
    Otherwise, check for persisted token at *token_path*.
    If neither exists, generate a random token and save it.
    """
    if explicit_token:
        return explicit_token

    p = Path(token_path)
    if p.exists():
        token = p.read_text().strip()
        if token:
            return token

    # Generate new token
    token = secrets.token_urlsafe(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token)
    log.info("auth.token_generated", path=str(p))
    return token
