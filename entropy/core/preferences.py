"""Small per-user preferences shared by the desktop and terminal interfaces."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _preferences_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "entropy" / "settings.json"


def load_volume(default: int = 50) -> int:
    try:
        preferences: dict[str, Any] = json.loads(_preferences_path().read_text(encoding="utf-8"))
        if not isinstance(preferences, dict):
            return max(0, min(100, default))
        return max(0, min(100, int(preferences.get("volume", default))))
    except (OSError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        return max(0, min(100, default))


def save_volume(volume: int) -> None:
    temporary_path: str | None = None
    try:
        path = _preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        preferences: dict[str, Any] = {}
        try:
            preferences = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(preferences, dict):
                preferences = {}
        except FileNotFoundError:
            pass
        except OSError:
            return
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        preferences["volume"] = max(0, min(100, int(volume)))
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(json.dumps(preferences, indent=2) + "\n")
        os.replace(temporary_path, path)
    except OSError:
        pass
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass