"""GitHub release lookup for optional update notifications."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from entropy import __version__

REPOSITORY = "luffy3006/entropy-player"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"


@dataclass(frozen=True)
class UpdateResult:
    latest_version: str | None
    release_url: str
    error: str | None = None

    @property
    def update_available(self) -> bool:
        return self.latest_version is not None and _version_key(self.latest_version) > _version_key(__version__)


def _version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version.lstrip("vV"))
    values = [int(part) for part in parts[:4]]
    return tuple((values + [0] * 4)[:4])


def check_for_update(timeout: float = 5.0) -> UpdateResult:
    request = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Entropy-Player"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        version = str(payload.get("tag_name", "")).strip()
        if not version:
            return UpdateResult(None, RELEASES_PAGE, "The latest release has no version tag.")
        return UpdateResult(version, str(payload.get("html_url") or RELEASES_PAGE))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateResult(None, RELEASES_PAGE, "No published release is available yet.")
        return UpdateResult(None, RELEASES_PAGE, f"GitHub returned HTTP {exc.code}.")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return UpdateResult(None, RELEASES_PAGE, f"Could not check for updates: {exc}")