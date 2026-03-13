"""Ingest Claude Code conversation transcripts into EvoSys trajectories.

Claude Code stores every conversation as a JSONL file in
``~/.claude/projects/``.  Each line is a message with tool_use and
tool_result blocks that capture exactly what Claude Code did.

This module reads those transcripts, extracts tool-call pairs, and
converts them to :class:`TrajectoryRecord` instances so the evolution
loop can learn from Claude Code sessions the user ran independently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.memory_store import MemoryStore
from evosys.storage.trajectory_store import TrajectoryStore

log = structlog.get_logger()

_NAMESPACE = "_system:ingest_state"
_DEFAULT_CLAUDE_DIR = Path.home() / ".claude" / "projects"


@dataclass
class IngestStats:
    """Summary of an ingestion run."""

    files_scanned: int = 0
    files_new: int = 0
    tool_calls_ingested: int = 0
    sessions_ingested: int = 0
    errors: int = 0


@dataclass
class _ToolCallPair:
    """A matched tool_use + tool_result pair from a transcript."""

    tool_name: str
    tool_use_id: str
    input_data: dict[str, Any]
    output_text: str = ""
    success: bool = True
    timestamp: str = ""


class ClaudeCodeIngestor:
    """Ingest Claude Code transcripts into the EvoSys trajectory store."""

    def __init__(
        self,
        trajectory_store: TrajectoryStore,
        memory_store: MemoryStore,
        *,
        claude_dir: Path | None = None,
    ) -> None:
        self._store = trajectory_store
        self._memory = memory_store
        self._claude_dir = claude_dir or _DEFAULT_CLAUDE_DIR

    async def ingest_all(self) -> IngestStats:
        """Scan all Claude Code projects and ingest new transcripts."""
        stats = IngestStats()

        if not self._claude_dir.is_dir():
            log.warning(
                "ingest.claude_dir_not_found",
                path=str(self._claude_dir),
            )
            return stats

        # Find all JSONL transcript files
        jsonl_files = sorted(self._claude_dir.rglob("*.jsonl"))
        stats.files_scanned = len(jsonl_files)

        for filepath in jsonl_files:
            file_key = str(filepath.relative_to(self._claude_dir))

            # Compute content hash for crash-safe dedup
            try:
                content_bytes = filepath.read_bytes()
                content_hash = hashlib.sha256(content_bytes).hexdigest()[:16]
            except OSError:
                stats.errors += 1
                continue

            # Check if already ingested (by file key AND content hash)
            marker = await self._memory.get(
                file_key, namespace=_NAMESPACE
            )
            if marker is not None:
                try:
                    marker_data = json.loads(marker)
                    if marker_data.get("content_hash") == content_hash:
                        continue  # same file, same content → skip
                except (json.JSONDecodeError, TypeError):
                    continue  # marker exists but unparseable → skip

            stats.files_new += 1
            try:
                n_calls = await self._ingest_file(filepath)
                stats.tool_calls_ingested += n_calls
                if n_calls > 0:
                    stats.sessions_ingested += 1

                # Mark as ingested with content hash for crash recovery
                await self._memory.set(
                    file_key,
                    json.dumps({
                        "ingested_at": datetime.now(UTC).isoformat(),
                        "tool_calls": n_calls,
                        "content_hash": content_hash,
                    }),
                    namespace=_NAMESPACE,
                )
            except Exception:
                stats.errors += 1
                log.exception(
                    "ingest.file_failed", path=str(filepath)
                )

        log.info(
            "ingest.complete",
            files_scanned=stats.files_scanned,
            files_new=stats.files_new,
            tool_calls=stats.tool_calls_ingested,
            sessions=stats.sessions_ingested,
        )
        return stats

    async def _ingest_file(self, filepath: Path) -> int:
        """Parse a single JSONL transcript and store tool-call pairs."""
        messages = _parse_jsonl(filepath)
        if not messages:
            return 0

        # Extract session_id from first message
        session_id_str = ""
        for msg in messages:
            sid = msg.get("sessionId", "")
            if sid:
                session_id_str = sid
                break

        # Collect tool_use events from assistant messages
        tool_uses: dict[str, _ToolCallPair] = {}
        for msg in messages:
            if msg.get("type") == "assistant":
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                    ):
                        tool_id = block.get("id", "")
                        tool_uses[tool_id] = _ToolCallPair(
                            tool_name=block.get("name", "unknown"),
                            tool_use_id=tool_id,
                            input_data=(
                                block.get("input", {})
                                if isinstance(block.get("input"), dict)
                                else {}
                            ),
                        )

            # Match tool_results from user messages
            elif msg.get("type") == "user":
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_result"
                    ):
                        tool_id = block.get("tool_use_id", "")
                        if tool_id in tool_uses:
                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                # Extract text from content blocks
                                result_content = " ".join(
                                    b.get("text", "")
                                    for b in result_content
                                    if isinstance(b, dict)
                                )
                            tool_uses[tool_id].output_text = str(
                                result_content
                            )[:5000]
                            is_error = block.get("is_error", False)
                            tool_uses[tool_id].success = not is_error

            # Extract timestamps from progress messages
            elif msg.get("type") == "progress":
                tool_id = msg.get("toolUseID", "")
                ts = msg.get("timestamp", "")
                if tool_id in tool_uses and ts:
                    tool_uses[tool_id].timestamp = ts

        # Convert to TrajectoryRecords and save
        if not tool_uses:
            return 0

        session_ulid = new_ulid()
        records: list[TrajectoryRecord] = []

        for idx, pair in enumerate(tool_uses.values()):
            # Truncate large inputs for storage
            safe_params: dict[str, object] = {}
            for k, v in pair.input_data.items():
                sv = str(v)
                safe_params[k] = sv[:2000] if len(sv) > 2000 else v

            record = TrajectoryRecord(
                session_id=session_ulid,
                iteration_index=idx,
                action_name=f"tool:{pair.tool_name}",
                context_summary=(
                    f"Claude Code session {session_id_str[:12]}: "
                    f"{pair.tool_name}"
                ),
                action_params=safe_params,
                action_result={
                    "output": pair.output_text[:2000],
                    "source": "claude_code_ingest",
                },
                success=pair.success,
            )
            records.append(record)

        await self._store.save_many(records)
        return len(records)


def _parse_jsonl(filepath: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of message dicts."""
    messages: list[dict[str, Any]] = []
    try:
        with filepath.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return messages
