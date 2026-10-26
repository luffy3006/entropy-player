#!/usr/bin/env python3
"""Check that distro package versions match the project version."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def check_versions(project_root: Path = PROJECT_ROOT) -> str:
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    project_section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", pyproject)
    if project_section is None:
        raise ValueError("pyproject.toml is missing its [project] section")
    project_version = re.search(
        r'(?m)^version\s*=\s*"([^"]+)"\s*$',
        project_section.group(1),
    )
    if project_version is None:
        raise ValueError("pyproject.toml is missing [project].version")
    expected = project_version.group(1)

    pkgbuild = (project_root / "packaging" / "arch" / "PKGBUILD").read_text(encoding="utf-8")
    arch_version = re.search(r"(?m)^pkgver=([^\s#]+)\s*$", pkgbuild)
    changelog = (project_root / "debian" / "changelog").read_text(encoding="utf-8")
    debian_version = re.match(r"^entropy-player \(([^)]+)\)", changelog)

    actual_versions = {
        "packaging/arch/PKGBUILD pkgver": arch_version.group(1) if arch_version else None,
        "top debian/changelog entry": debian_version.group(1).split("-", 1)[0] if debian_version else None,
    }
    mismatches = [
        f"{source} is {actual!r}, expected {expected!r}"
        for source, actual in actual_versions.items()
        if actual != expected
    ]
    if mismatches:
        raise ValueError("; ".join(mismatches))
    return expected


def main() -> int:
    try:
        version = check_versions()
    except (OSError, ValueError) as error:
        print(f"Version check failed: {error}", file=sys.stderr)
        return 1
    print(f"Release versions agree: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
