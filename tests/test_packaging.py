# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Invariants that keep a release honest.

The version is recorded in three places and a release script moves all three
together. These tests fail if they ever drift, because the symptoms otherwise
appear only after a tag has been pushed: the release workflow rejects a tag
that disagrees with the packaged version, and on PyPI a filename can never be
reused.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import ibcli

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text())


def test_package_version_matches_pyproject():
    assert ibcli.__version__ == PYPROJECT["project"]["version"]


def test_changelog_documents_the_current_version():
    """`release_notes.sh` reads this heading; without it a release ships a bare commit list."""
    version = PYPROJECT["project"]["version"]
    changelog = (REPO / "CHANGELOG.md").read_text()
    assert f"## [{version}] - " in changelog


def test_no_direct_url_dependencies_declared():
    """PyPI rejects a distribution whose metadata carries a `name @ url` requirement."""
    project = PYPROJECT["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    offenders = [r for r in requirements if "@" in r]
    assert not offenders, f"direct URL requirements are unpublishable: {offenders}"


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", PYPROJECT["project"]["version"])
