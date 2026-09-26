# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Every word the completion dropdown offers must lead somewhere.

The dropdown is built from each waypoint's ``words``, so a word with no node
behind it advertises a command that does not exist. Three were shipping:
``test`` sat in the root menu and answered "Unknown command: test", while
``show server error`` and ``configure auth network_user`` answered
"Incomplete" and then re-offered the same dead words - a loop.

These assert a property of the *whole* registered grammar, so they run in a
fresh interpreter. ``COMMANDS`` is process-global and several test modules
replace ``COMMANDS["NULL"]`` with a cut-down word list; conftest's
``reset_commands_registry`` fixture restores whatever it snapshotted at
setup, so a reduced registry propagates to every later test. Checking the
grammar in-process would assert against that debris rather than what ibcli
actually ships.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _in_fresh_interpreter(body: str) -> str:
    """Run `body` against a pristine command registry; return its stdout."""
    script = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        import ibcli.commands  # noqa: F401 - registers every command tree
        from ibcli.registry import COMMANDS
        """
    ) % str(REPO / "src") + textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_no_waypoint_offers_a_word_that_leads_nowhere():
    out = _in_fresh_interpreter(
        """
        dead = []
        for key, entry in COMMANDS.items():
            parent_tokens = set(key.split()) if key != "NULL" else set()
            for word in (entry.words or "").split():
                # Placeholders and inline key=value options are parsed by the
                # handler, not registered as their own nodes.
                if word.startswith("<") or "=" in word:
                    continue
                for alt in filter(None, word.split("|")):
                    # A word already present in the parent key is a repeat
                    # chain (`... member <ip> member <ip>`, `... comment
                    # <comment>`) truncated by the set-chain depth cap - see
                    # docs/development/known-quirks.md - not a dead end.
                    if alt in parent_tokens:
                        continue
                    child = alt if key == "NULL" else key + " " + alt
                    if child not in COMMANDS:
                        dead.append(repr(key) + " offers " + repr(alt))
        print("\\n".join(sorted(dead)))
        """
    )
    assert out == "", "dead grammar branches:\n  " + out.replace("\n", "\n  ")


def test_every_root_command_has_a_description():
    """The root dropdown is the first thing an operator sees."""
    out = _in_fresh_interpreter(
        """
        missing = []
        for word in (COMMANDS["NULL"].words or "").split():
            for alt in filter(None, word.split("|")):
                entry = COMMANDS.get(alt)
                if entry is None or not (entry.help or "").strip():
                    missing.append(alt)
        print(" ".join(sorted(missing)))
        """
    )
    assert out == "", f"root commands with no help text: {out}"


def test_root_completions_carry_their_help_text():
    """Regression: the completer built the lookup key as 'NULL show', which
    never exists, so every top-level command showed a blank description."""
    out = _in_fresh_interpreter(
        """
        from prompt_toolkit.document import Document
        from ibcli.completer import IbcliCompleter
        from ibcli.context import Context

        comps = list(IbcliCompleter(Context()).get_completions(Document("", 0), None))
        if not comps:
            print("NO-COMPLETIONS")
        else:
            blank = [c.text for c in comps if not c.display_meta_text.strip()]
            print(" ".join(sorted(blank)))
        """
    )
    assert out != "NO-COMPLETIONS", "root completion produced nothing"
    assert out == "", f"root completions with no description: {out}"
