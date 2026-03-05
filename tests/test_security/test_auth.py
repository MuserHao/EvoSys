"""Tests for authentication middleware and token management."""

from __future__ import annotations

from pathlib import Path

from evosys.security.token import get_or_create_token


class TestTokenManagement:
    def test_explicit_token_returned(self, tmp_path: Path) -> None:
        token = get_or_create_token(
            str(tmp_path / "token"),
            explicit_token="my-secret-token",
        )
        assert token == "my-secret-token"

    def test_generates_token_on_first_call(self, tmp_path: Path) -> None:
        token_path = str(tmp_path / "new_token")
        token = get_or_create_token(token_path)
        assert len(token) > 20
        # Should be persisted
        assert Path(token_path).read_text().strip() == token

    def test_reads_existing_token(self, tmp_path: Path) -> None:
        token_path = tmp_path / "existing"
        token_path.write_text("persistent-token")
        token = get_or_create_token(str(token_path))
        assert token == "persistent-token"

    def test_regenerates_if_empty_file(self, tmp_path: Path) -> None:
        token_path = tmp_path / "empty"
        token_path.write_text("")
        token = get_or_create_token(str(token_path))
        assert len(token) > 20

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        token_path = str(tmp_path / "nested" / "dir" / "token")
        token = get_or_create_token(token_path)
        assert len(token) > 20
        assert Path(token_path).exists()
