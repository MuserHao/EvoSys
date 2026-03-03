"""PII and secrets redaction for trajectory data.

All regex patterns are compiled at module import time for maximum
performance in the trajectory logger hot path.  The sanitizer operates
on raw ``dict`` / ``str`` / ``list`` values and has **no** schema
dependencies.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Compiled regex patterns — evaluated once at import
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys (generic hex/base64 tokens ≥ 20 chars preceded by common prefixes)
    (re.compile(r"(?i)(sk|pk|api[_-]?key|key)[_\-]?[a-z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    # Bearer tokens
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"), "[REDACTED_BEARER_TOKEN]"),
    # AWS access key IDs  (AKIA…)
    (re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"), "[REDACTED_AWS_KEY]"),
    # AWS secret access keys (40-char base64)
    (
        re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
        "[REDACTED_AWS_SECRET]",
    ),
    # Email addresses
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    # Phone numbers (US / international with optional country code)
    (
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
    # Credit card numbers (13-19 digits, optionally separated)
    (
        re.compile(r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,7}(?!\d)"),
        "[REDACTED_CC]",
    ),
    # US Social Security Numbers
    (
        re.compile(r"(?<!\d)\d{3}[-\s]?\d{2}[-\s]?\d{4}(?!\d)"),
        "[REDACTED_SSN]",
    ),
]

# ---------------------------------------------------------------------------
# Sensitive key names — O(1) membership test
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "secret",
        "secret_key",
        "secretkey",
        "password",
        "passwd",
        "token",
        "access_token",
        "accesstoken",
        "refresh_token",
        "auth",
        "authorization",
        "credential",
        "credentials",
        "private_key",
        "privatekey",
        "ssn",
        "credit_card",
        "creditcard",
        "card_number",
    }
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sanitize_string(text: str) -> str:
    """Apply all regex redaction patterns to *text*."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_value(value: Any) -> Any:
    """Recursively sanitize a value (str, dict, list, or pass-through)."""
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, dict):
        return sanitize_dict(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a dictionary: redact sensitive keys entirely, scan all values."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        else:
            result[key] = sanitize_value(value)
    return result
