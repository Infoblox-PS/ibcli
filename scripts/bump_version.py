#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.
"""Apply a version bump across every file that records the version.

The version lives in three places that must never disagree: ``pyproject.toml``,
``ibcli.__version__`` and the CHANGELOG heading. A tag that disagrees with the
packaged version is caught by the release workflow, but only after the tag has
been pushed - this moves all three together so the mismatch cannot happen.

Run through ``scripts/release.sh`` rather than directly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/Infoblox-PS/ibcli"
PLACEHOLDER = "Nothing yet."


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text()
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match for {pattern!r}, found {count}")
    path.write_text(new)


def bump_project_files(version: str) -> None:
    _replace_once(REPO / "pyproject.toml", r'^version = "[^"]+"$', f'version = "{version}"')
    _replace_once(
        REPO / "src" / "ibcli" / "__init__.py",
        r'^__version__ = "[^"]+"$',
        f'__version__ = "{version}"',
    )


def roll_changelog(version: str, today: str) -> None:
    """Date the Unreleased section as `version` and open a fresh one above it."""
    path = REPO / "CHANGELOG.md"
    text = path.read_text()

    start = text.find("## [Unreleased]")
    if start == -1:
        raise SystemExit("CHANGELOG.md: no '## [Unreleased]' heading to release")
    body_start = start + len("## [Unreleased]")
    next_heading = text.find("\n## [", body_start)
    body = text[body_start : next_heading if next_heading != -1 else len(text)]
    if not body.strip() or body.strip() == PLACEHOLDER:
        raise SystemExit(
            "CHANGELOG.md: the Unreleased section is empty - there is nothing to release"
        )

    text = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n{PLACEHOLDER}\n\n## [{version}] - {today}",
        1,
    )

    # Link refs: Unreleased compares against the new tag, and the new version
    # gets its own. Both live at the end of the file.
    text = _sub_link(
        text, r"^\[Unreleased\]: .*$", f"[Unreleased]: {REPO_URL}/compare/v{version}...HEAD"
    )
    marker = f"[Unreleased]: {REPO_URL}/compare/v{version}...HEAD"
    text = text.replace(marker, f"{marker}\n[{version}]: {REPO_URL}/releases/tag/v{version}", 1)
    path.write_text(text)


def _sub_link(text: str, pattern: str, replacement: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"CHANGELOG.md: expected one {pattern!r}, found {count}")
    return new


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", help="the version to release, without a leading v (e.g. 1.1.0)")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="release date (ISO)")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-.a-z0-9]+)?", args.version):
        raise SystemExit(f"not a version: {args.version!r} (expected e.g. 1.1.0)")

    bump_project_files(args.version)
    roll_changelog(args.version, args.date)
    print(f"bumped to {args.version} ({args.date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
