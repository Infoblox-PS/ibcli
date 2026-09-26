# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Structural invariants for the Markdown corpus.

These exist because an automated Markdown rewrite once silently destroyed a
page. `pymarkdown` has no notion of pymdownx admonitions, so it reads the
4-space-indented body of a `!!! note` block as an indented code block; its
`fix` subcommand then "corrects" that by un-indenting the body and wrapping
it in bare fences. The page still builds and still lints - it just renders as
something else entirely.

The repo config disables that rule (see `plugins.code-block-style` in
pyproject.toml), so the current toolchain is safe. These tests are the
backstop for the case the config does not cover: a contributor, a stale
checkout, or a different tool doing the same thing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FENCE = re.compile(r"^\s*(```|~~~)")
ADMONITION = re.compile(r"^(?P<indent>\s*)(?:!!!|\?\?\?\+?)\s+\S")


def _markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [REPO / f for f in out]


def test_code_fences_are_balanced():
    """An unclosed fence swallows the rest of the page into a code block."""
    unbalanced = []
    for path in _markdown_files():
        opens = sum(1 for line in path.read_text().splitlines() if FENCE.match(line))
        if opens % 2:
            unbalanced.append(f"{path.relative_to(REPO)} ({opens} fence markers)")
    assert not unbalanced, "Unbalanced code fences in: " + ", ".join(unbalanced)


def test_admonition_bodies_stay_indented():
    """An admonition's body must be indented past the `!!!` marker.

    This is the exact signature of the corruption described in the module
    docstring: the body is left at column 0 and wrapped in bare fences, so the
    block silently stops being an admonition.
    """
    broken = []
    for path in _markdown_files():
        lines = path.read_text().splitlines()
        inside_fence = False
        for i, line in enumerate(lines):
            if FENCE.match(line):
                inside_fence = not inside_fence
                continue
            if inside_fence:
                continue
            m = ADMONITION.match(line)
            if not m:
                continue
            marker_indent = len(m.group("indent"))
            # Find the next non-blank line; it is the start of the body.
            body = next(
                (line_ for line_ in lines[i + 1 :] if line_.strip()),
                None,
            )
            if body is None:
                continue  # trailing admonition with no body is valid
            body_indent = len(body) - len(body.lstrip())
            # A sibling block (another admonition, a heading, the next
            # paragraph) is fine - only a body that lost its indentation and
            # became a fence is the failure we are guarding against.
            if body_indent <= marker_indent and FENCE.match(body):
                broken.append(
                    f"{path.relative_to(REPO)}:{i + 1}: admonition body un-indented into a fence"
                )
    assert not broken, "Corrupted admonition blocks:\n  " + "\n  ".join(broken)


def test_no_typographic_dashes():
    """The corpus is plain ASCII by convention; see the dash-sweep commits."""
    offenders = []
    for path in _markdown_files():
        text = path.read_text()
        if "—" in text or "–" in text:
            n = text.count("—") + text.count("–")
            offenders.append(f"{path.relative_to(REPO)} ({n})")
    assert not offenders, "Em/en dashes found in: " + ", ".join(offenders)
