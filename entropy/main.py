"""Command-line launcher for the GUI and terminal interfaces."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
from types import FrameType

from entropy import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="entropy", description="Entropy Player, a local history-aware music player")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--gui", action="store_const", const="gui", dest="mode", help="launch the desktop interface")
    modes.add_argument("--cli", "--tui", action="store_const", const="tui", dest="mode", help="launch the terminal interface")
    parser.add_argument("--version", action="version", version=f"Entropy Player {__version__}")
    return parser


def main() -> int:
    args = _parser().parse_args()
    mode = args.mode or ("gui" if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") else "tui")

    from entropy.core.controller import PlayerController
    from entropy.core.database import LibraryDatabase

    database = LibraryDatabase()
    try:
        controller = PlayerController(database=database)
    except (ImportError, RuntimeError, OSError) as exc:
        database.close()
        print(f"Entropy Player could not start: {exc}", file=sys.stderr)
        return 1

    atexit.register(controller.close)

    def shutdown(signum: int, _frame: FrameType | None) -> None:
        controller.close()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        if mode == "gui":
            from entropy.gui.app import run

            return run(controller)
        from entropy.tui.app import run

        run(controller)
        return 0
    except (ImportError, RuntimeError) as exc:
        controller.close()
        print(f"Entropy Player could not start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())