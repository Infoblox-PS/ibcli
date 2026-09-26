# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import re
from collections.abc import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML

from ibcli import parser
from ibcli.registry import COMMANDS

# ---------------------------------------------------------------------------
# Human-friendly labels for special tokens (surfaced as grey placeholders in
# the dropdown so users know what value is expected next).
# ---------------------------------------------------------------------------

_SPECIAL_LABEL = {
    "<zone>": "zone (fqdn or cidr)",
    "<name>": "name",
    "<member>": "member host_name",
    "<comment>": "comment",
    "<value>": "value",
    "<ip>": "ip address",
    "<n.n.n.n/mm>": "cidr (v4 or v6)",
    "<cidr>": "cidr",
    "</cidr>": "/prefix",
    "<mac>": "mac address",
    "<ipv6>": "ipv6 address",
    "<num>": "integer",
    "<file>": "local path",
    "<name=value>": "key=value",
    "<cr>": "(press Enter)",
}


def _candidate_match_line(check_line: str, word: str) -> str:
    """Join a waypoint and a candidate word into a COMMANDS key.

    ``NULL`` is the synthetic root node, not a real first word - the top-level
    commands are registered as ``show``, ``configure``, … not ``NULL show``.
    Joining it blindly produced a key that never exists, so every top-level
    command came up with an empty description while deeper levels showed
    theirs.
    """
    if check_line in ("", "NULL"):
        return word
    return f"{check_line} {word}"


def _meta_for(match_line: str) -> str:
    """Return the `help=` text for a registered match-line, else ''."""
    entry = COMMANDS.get(match_line)
    return (entry.help or "").strip() if entry else ""


def _display_for(word: str) -> HTML:
    """Format a completion word as pretty HTML for the dropdown."""
    if word.startswith("<") and word.endswith(">"):
        label = _SPECIAL_LABEL.get(word, word.strip("<>"))
        return HTML(f"<ansigray>⟨{label}⟩</ansigray>")
    return HTML(f"<b>{word}</b>")


class IbcliCompleter(Completer):
    """Wrap the parser so prompt_toolkit can call it for tab completion."""

    def __init__(self, ctx=None):
        self._ctx = ctx

    def _dynamic_items(self, check_line: str) -> list[tuple[str, str]]:
        """Ask the current waypoint for dynamic completions, if any."""
        if self._ctx is None:
            return []
        entry = COMMANDS.get(check_line)
        if entry is None or entry.dynamic is None:
            return []
        try:
            return list(entry.dynamic(self._ctx))
        except Exception:
            return []

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        line = document.text_before_cursor
        expanded, error, match_line = parser.expand_line(line)
        if error and "Unknown" in error:
            return

        prearg, last = parser.lastarg(line)
        if prearg == "NULL":
            check_line = "NULL"
        elif last:
            check_line = re.sub(r"\s\S+$", "", match_line).strip() or "NULL"
        else:
            check_line = match_line or "NULL"

        words = parser.get_context(check_line)
        if not words:
            return
        done, sptype, expword, matches = parser.expand_word(last, words)

        # Single unambiguous completion - fill it in and describe it.
        if done and expword:
            stripped = expword.rstrip()
            candidate_ml = _candidate_match_line(check_line, stripped)
            yield Completion(
                stripped,
                start_position=-len(last),
                display=_display_for(stripped),
                display_meta=_meta_for(candidate_ml),
            )
            return

        # Menu of literals (and pseudo-entries for <special> next-tokens).
        if matches:
            dynamic = self._dynamic_items(check_line)
            # Real dynamic values first (filtered by what the user has typed)
            for value, meta in dynamic:
                if last and not value.startswith(last):
                    continue
                yield Completion(
                    value,
                    start_position=-len(last),
                    display=HTML(f"<b>{value}</b>"),
                    display_meta=meta,
                )
            for w in matches:
                if w.startswith("<"):
                    # Surface the special slot as a non-inserting hint so the
                    # user can see "⟨cidr (v4 or v6)⟩" in the menu. Yielding an
                    # empty text with display_meta gives a hint-only row.
                    if w == "<cr>":
                        yield Completion(
                            "",
                            start_position=0,
                            display=_display_for(w),
                            display_meta=_meta_for(check_line) or "execute",
                        )
                    elif not dynamic:
                        yield Completion(
                            "",
                            start_position=0,
                            display=_display_for(w),
                            display_meta=f"expects {w.strip('<>')}",
                        )
                    continue

                candidate_ml = _candidate_match_line(check_line, w)
                yield Completion(
                    w,
                    start_position=-len(last),
                    display=_display_for(w),
                    display_meta=_meta_for(candidate_ml),
                )
            return

        # No literal matches, but we may still have a dynamic list for a
        # <special> slot (e.g. member IPs for `... member <ip>`).
        if sptype:
            for value, meta in self._dynamic_items(check_line):
                if last and not value.startswith(last):
                    continue
                yield Completion(
                    value,
                    start_position=-len(last),
                    display=HTML(f"<b>{value}</b>"),
                    display_meta=meta,
                )
            return
