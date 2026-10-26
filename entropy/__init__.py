"""Entropy Player: a local music player with history-aware shuffle."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("entropy-player")
except PackageNotFoundError:
    __version__ = "0+local"