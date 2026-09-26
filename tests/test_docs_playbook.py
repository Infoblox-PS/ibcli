# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""The playbook's commands must actually work.

`docs/commands/playbook.md` shows each task twice - abbreviated and full -
and an abbreviation is only unambiguous against the commands registered
today. Adding a sibling command can silently make a published abbreviation
ambiguous, turning a copy-pasteable recipe into a `^--- Ambiguous argument`.
These tests parse the page and check both halves against the real grammar,
so the docs fail the build rather than the operator's terminal.

Runs in a fresh interpreter for the same reason as
``test_grammar_reachability``: ``COMMANDS`` is process-global and other test
modules leave a cut-down registry behind.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAYBOOK = REPO / "docs" / "commands" / "playbook.md"

_PREAMBLE = """
import re, sys
sys.path.insert(0, %r)
import ibcli.commands  # noqa: F401 - registers every command tree
from ibcli.parser import expand_line

TEXT = open(%r).read()

def table_pairs():
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r"^\\|[^|]*\\|\\s*`([^`]+)`\\s*\\|\\s*`([^`]+)`\\s*\\|", TEXT, re.M)]

def block_lines():
    out = []
    for b in re.findall(r"```(?:\\w+)?\\n(.*?)```", TEXT, re.S):
        joined = re.sub(r"\\\\\\n\\s*", " ", b)
        for raw in joined.splitlines():
            line = raw.split("#")[0].strip()
            if line:
                out.append(line)
    return out
"""


def _probe(body: str) -> str:
    script = (_PREAMBLE % (str(REPO / "src"), str(PLAYBOOK))) + textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=str(REPO)
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_playbook_exists_and_is_not_empty():
    assert PLAYBOOK.is_file(), f"missing {PLAYBOOK}"
    assert PLAYBOOK.stat().st_size > 1000


def test_every_playbook_command_parses():
    out = _probe(
        """
        VERBS = ("show ", "configure ", "restart ", "upload ", "download ",
                 "generate ", "s ", "c ", "r ", "u ", "d ")
        cmds = [ln for ln in block_lines() if ln.startswith(VERBS)]
        for a, f in table_pairs():
            cmds += [a, f]
        assert cmds, "no commands found in the playbook"
        bad = []
        for c in cmds:
            _, err, _ = expand_line(c)
            if err:
                bad.append(c + "  ->  " + err.strip().splitlines()[-1].strip())
        print("\\n".join(bad))
        """
    )
    assert out == "", "playbook commands that do not parse:\n  " + out.replace("\n", "\n  ")


def test_abbreviated_and_full_forms_resolve_identically():
    """The whole premise of the page: both columns are the same command."""
    out = _probe(
        """
        pairs = table_pairs()
        lines = block_lines()
        for a, f in zip(lines, lines[1:]):
            if a == f or a.startswith("ibcli"):
                continue
            if len(a.split()) == len(f.split()) and len(a) < len(f):
                pairs.append((a, f))
        assert pairs, "no abbreviated/full pairs found"
        bad = []
        for short, full in pairs:
            sa, ea, ma = expand_line(short)
            sf, ef, mf = expand_line(full)
            if ea or ef or (sa, ma) != (sf, mf):
                bad.append(short + "  !=  " + full)
        print("\\n".join(bad))
        """
    )
    assert out == "", "abbreviations that no longer match their full form:\n  " + out.replace(
        "\n", "\n  "
    )
