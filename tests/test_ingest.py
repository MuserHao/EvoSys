"""Tests for Claude Code log ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from evosys.ingest.claude_code_ingest import (
    ClaudeCodeIngestor,
    _parse_jsonl,
)
from evosys.storage.memory_store import MemoryStore
from evosys.storage.models import Base
from evosys.storage.trajectory_store import TrajectoryStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def stores(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    yield TrajectoryStore(factory), MemoryStore(factory)
    await engine.dispose()


def _write_transcript(
    directory: Path,
    project: str,
    session_id: str,
    tool_calls: list[tuple[str, dict, str, bool]],
) -> Path:
    """Write a fake Claude Code transcript JSONL file.

    tool_calls: list of (tool_name, input_dict, output_text, success)
    """
    proj_dir = directory / project
    proj_dir.mkdir(parents=True, exist_ok=True)
    filepath = proj_dir / f"{session_id}.jsonl"

    lines = []
    # User message with task
    lines.append(json.dumps({
        "type": "user",
        "sessionId": session_id,
        "message": {"role": "user", "content": "Do something"},
        "uuid": "u1",
    }))

    for i, (name, inp, output, success) in enumerate(tool_calls):
        tool_id = f"toolu_{i}"
        # Assistant with tool_use
        lines.append(json.dumps({
            "type": "assistant",
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": name,
                        "input": inp,
                    }
                ],
            },
            "uuid": f"a{i}",
        }))
        # User with tool_result
        lines.append(json.dumps({
            "type": "user",
            "sessionId": session_id,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": output,
                        "is_error": not success,
                    }
                ],
            },
            "uuid": f"r{i}",
        }))

    filepath.write_text("\n".join(lines))
    return filepath


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseJsonl:
    def test_parses_valid_file(self, tmp_path: Path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"type": "user", "text": "hello"}\n'
            '{"type": "assistant", "text": "hi"}\n'
        )
        messages = _parse_jsonl(f)
        assert len(messages) == 2

    def test_skips_invalid_lines(self, tmp_path: Path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"valid": true}\n'
            'not json\n'
            '{"also_valid": true}\n'
        )
        messages = _parse_jsonl(f)
        assert len(messages) == 2

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert _parse_jsonl(f) == []

    def test_missing_file(self, tmp_path: Path):
        f = tmp_path / "missing.jsonl"
        assert _parse_jsonl(f) == []


class TestClaudeCodeIngestor:
    async def test_ingests_tool_calls(self, stores, tmp_path: Path):
        traj_store, mem_store = stores
        _write_transcript(
            tmp_path, "proj", "sess1",
            [
                ("Read", {"file_path": "/tmp/x.py"}, "file contents", True),
                ("Bash", {"command": "ls"}, "file.py", True),
            ],
        )
        ingestor = ClaudeCodeIngestor(
            traj_store, mem_store, claude_dir=tmp_path
        )
        stats = await ingestor.ingest_all()
        assert stats.files_scanned == 1
        assert stats.files_new == 1
        assert stats.tool_calls_ingested == 2
        assert stats.sessions_ingested == 1

    async def test_skips_already_ingested(self, stores, tmp_path: Path):
        traj_store, mem_store = stores
        _write_transcript(
            tmp_path, "proj", "sess1",
            [("Read", {}, "ok", True)],
        )
        ingestor = ClaudeCodeIngestor(
            traj_store, mem_store, claude_dir=tmp_path
        )
        stats1 = await ingestor.ingest_all()
        assert stats1.files_new == 1

        stats2 = await ingestor.ingest_all()
        assert stats2.files_new == 0
        assert stats2.tool_calls_ingested == 0

    async def test_records_success_and_failure(
        self, stores, tmp_path: Path
    ):
        traj_store, mem_store = stores
        _write_transcript(
            tmp_path, "proj", "sess1",
            [
                ("Read", {}, "ok", True),
                ("Bash", {}, "error", False),
            ],
        )
        ingestor = ClaudeCodeIngestor(
            traj_store, mem_store, claude_dir=tmp_path
        )
        await ingestor.ingest_all()

        # Verify records were stored with correct success flags
        from datetime import UTC, datetime, timedelta
        records = await traj_store.get_recent(
            since=datetime.now(UTC) - timedelta(hours=1)
        )
        assert len(records) == 2
        by_name = {r.action_name: r for r in records}
        assert by_name["tool:Read"].success is True
        assert by_name["tool:Bash"].success is False

    async def test_missing_claude_dir(self, stores, tmp_path: Path):
        traj_store, mem_store = stores
        ingestor = ClaudeCodeIngestor(
            traj_store, mem_store,
            claude_dir=tmp_path / "nonexistent",
        )
        stats = await ingestor.ingest_all()
        assert stats.files_scanned == 0

    async def test_multiple_projects(self, stores, tmp_path: Path):
        traj_store, mem_store = stores
        _write_transcript(
            tmp_path, "proj_a", "s1",
            [("Read", {}, "ok", True)],
        )
        _write_transcript(
            tmp_path, "proj_b", "s2",
            [("Write", {}, "ok", True), ("Bash", {}, "ok", True)],
        )
        ingestor = ClaudeCodeIngestor(
            traj_store, mem_store, claude_dir=tmp_path
        )
        stats = await ingestor.ingest_all()
        assert stats.files_scanned == 2
        assert stats.files_new == 2
        assert stats.tool_calls_ingested == 3
        assert stats.sessions_ingested == 2
