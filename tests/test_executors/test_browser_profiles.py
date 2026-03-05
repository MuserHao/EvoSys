"""Tests for BrowserProfileManager."""

from __future__ import annotations

from pathlib import Path

from evosys.executors.browser_profiles import BrowserProfile, BrowserProfileManager


class TestBrowserProfile:
    def test_profile_exists_false_for_new(self, tmp_path: Path) -> None:
        profile = BrowserProfile(name="test", state_path=tmp_path / "test.json")
        assert profile.exists is False

    def test_profile_exists_true_when_file_present(self, tmp_path: Path) -> None:
        state_path = tmp_path / "test.json"
        state_path.write_text("{}")
        profile = BrowserProfile(name="test", state_path=state_path)
        assert profile.exists is True


class TestBrowserProfileManager:
    def test_get_or_create(self, tmp_path: Path) -> None:
        mgr = BrowserProfileManager(str(tmp_path))
        profile = mgr.get_or_create("my-profile")
        assert profile.name == "my-profile"
        assert profile.state_path.parent == tmp_path

    def test_list_profiles_empty(self, tmp_path: Path) -> None:
        mgr = BrowserProfileManager(str(tmp_path))
        assert mgr.list_profiles() == []

    def test_list_profiles_with_existing(self, tmp_path: Path) -> None:
        (tmp_path / "alpha.json").write_text("{}")
        (tmp_path / "beta.json").write_text("{}")
        mgr = BrowserProfileManager(str(tmp_path))
        profiles = mgr.list_profiles()
        assert set(profiles) == {"alpha", "beta"}

    def test_delete_profile(self, tmp_path: Path) -> None:
        (tmp_path / "to-delete.json").write_text("{}")
        mgr = BrowserProfileManager(str(tmp_path))
        assert "to-delete" in mgr.list_profiles()

        deleted = mgr.delete_profile("to-delete")
        assert deleted is True
        assert "to-delete" not in mgr.list_profiles()
        assert not (tmp_path / "to-delete.json").exists()

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        mgr = BrowserProfileManager(str(tmp_path))
        assert mgr.delete_profile("nope") is False

    def test_get_or_create_idempotent(self, tmp_path: Path) -> None:
        mgr = BrowserProfileManager(str(tmp_path))
        p1 = mgr.get_or_create("same")
        p2 = mgr.get_or_create("same")
        assert p1.state_path == p2.state_path
