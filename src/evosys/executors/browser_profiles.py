"""Browser profile manager — named persistent Playwright contexts.

Maintains named browser profiles with cookie/session state persisted
to JSON files.  Profiles survive process restarts so the agent can
maintain logged-in sessions across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

_DEFAULT_PROFILES_DIR = "data/browser_profiles"


@dataclass(slots=True)
class BrowserProfile:
    """A named browser profile with its storage state."""

    name: str
    state_path: Path
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    @property
    def exists(self) -> bool:
        return self.state_path.exists()


class BrowserProfileManager:
    """Manage named browser profiles with persistent cookie state.

    Each profile corresponds to a Playwright ``storage_state`` JSON file.
    When fetching with a profile, the manager creates a
    ``persistent_context`` (or loads state into a new context) and
    saves state back after navigation.

    Parameters
    ----------
    profiles_dir:
        Directory to store profile state files.
    """

    def __init__(self, profiles_dir: str = _DEFAULT_PROFILES_DIR) -> None:
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, BrowserProfile] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        """Discover existing profile state files on disk."""
        for state_file in self._dir.glob("*.json"):
            name = state_file.stem
            self._profiles[name] = BrowserProfile(
                name=name, state_path=state_file
            )

    def get_or_create(self, name: str) -> BrowserProfile:
        """Return existing profile or create a new one."""
        if name not in self._profiles:
            state_path = self._dir / f"{name}.json"
            self._profiles[name] = BrowserProfile(
                name=name, state_path=state_path
            )
            log.info("browser_profiles.created", profile=name)
        return self._profiles[name]

    def list_profiles(self) -> list[str]:
        """Return names of all known profiles."""
        return sorted(self._profiles.keys())

    def delete_profile(self, name: str) -> bool:
        """Delete a profile and its state file. Returns True if it existed."""
        profile = self._profiles.pop(name, None)
        if profile is None:
            return False
        if profile.state_path.exists():
            profile.state_path.unlink()
        log.info("browser_profiles.deleted", profile=name)
        return True

    async def fetch_with_profile(
        self,
        url: str,
        profile_name: str,
        *,
        timeout_s: float = 30.0,
        max_body_bytes: int = 5_000_000,
    ) -> dict[str, Any]:
        """Fetch a URL using a named browser profile.

        Launches a Playwright browser, loads the profile's storage
        state (cookies, localStorage), navigates to the URL, saves
        updated state, and returns the HTML.

        Returns a dict with keys: html, status_code, url, fetch_method,
        profile, or error.
        """
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError:
            return {
                "error": (
                    "Playwright is not installed. "
                    "Run: uv sync --group browser && playwright install chromium"
                ),
            }

        profile = self.get_or_create(profile_name)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    # Create context with existing state if available
                    ctx_kwargs: dict[str, Any] = {
                        "user_agent": profile.user_agent,
                    }
                    if profile.exists:
                        ctx_kwargs["storage_state"] = str(profile.state_path)

                    context = await browser.new_context(**ctx_kwargs)
                    page = await context.new_page()

                    await page.goto(
                        url,
                        timeout=timeout_s * 1000,
                        wait_until="networkidle",
                    )

                    html = await page.content()
                    final_url = page.url

                    # Save updated state back to profile
                    await context.storage_state(path=str(profile.state_path))

                finally:
                    await browser.close()

            body = html[:max_body_bytes]
            return {
                "html": body,
                "status_code": 200,
                "url": final_url,
                "fetch_method": "browser_profile",
                "profile": profile_name,
            }
        except TimeoutError:
            return {"error": f"Browser timeout after {timeout_s}s fetching {url}"}
        except Exception as exc:
            return {"error": str(exc)}
