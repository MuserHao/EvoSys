"""Slack thread context resolution."""

from __future__ import annotations

from typing import Any


def resolve_thread_id(event: dict[str, Any], reply_in_thread: bool) -> str | None:
    """Determine the thread_ts to reply to.

    If *reply_in_thread* is True, always reply in the message's thread.
    For messages already in a thread, use the existing thread_ts.
    For top-level messages, use the message's ts to start a new thread.

    Returns ``None`` if threading is disabled and the message is top-level.
    """
    # If the message is already in a thread, always reply there
    thread_ts = event.get("thread_ts")
    if thread_ts:
        return str(thread_ts)

    # Top-level message — thread if configured, else reply at top level
    if reply_in_thread:
        return str(event.get("ts", ""))

    return None
