# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

# Regex building blocks (ported from Perl $RE* globals, lines 89-107 of Perl ibcli)
_RE_COMM = r'("([^"]+)")|(\S+)'
_RE_ZONE = r"(\w|-|\.)+"
_RE_IP = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
_RE_CIDR = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}"
_RE_MAC = r"[\w:]+"
_RE_PARTIP = r"(\d{1,3})(\.[\d*]{1,3}){0,2}(\.[\d*]{1,3})"
# IPv6 literal in the grammar is intentionally permissive: any token that
# contains at least one colon and only hex / colon / dot characters (dots
# allow IPv4-mapped embeddings like ``::ffff:1.2.3.4``). The strict
# canonical check happens later in each command handler against
# ``ipaddress.IPv6Address`` - the parser just needs to pick v6 tokens out
# of v4 tokens.
_RE_IP6 = r"[0-9a-fA-F:.]*:[0-9a-fA-F:.]+"

# Special-token regex table. Keys must match the `<...>` tokens used in
# @command word lists.  Values are pre-compiled regexes.  Matches the Perl
# %SPECOPS hash at lines 109-138 of Perl ibcli.
SPECOPS: dict[str, re.Pattern[str]] = {
    "<mac>": re.compile(rf"^{_RE_MAC}$"),
    # <ipv6> originally aliased to _RE_MAC in the Perl port - a copy-
    # paste bug that silently accepted MAC-like inputs in IPv6 slots.
    # Fix to a proper IPv6 pattern (see _RE_IP6 above).
    "<ipv6>": re.compile(rf"^{_RE_IP6}$"),
    # <ipany> accepts either IPv4 (partial or full) or IPv6. Used by
    # commands whose target field is family-agnostic at the WAPI level,
    # like PTR records (ipv4addr vs ipv6addr).
    "<ipany>": re.compile(rf"^({_RE_PARTIP}|{_RE_IP6})$"),
    "<num>": re.compile(r"^\d+$"),
    "<svr>": re.compile(r"^\S+$"),
    "<file>": re.compile(r"^\S+$"),
    "<name>": re.compile(rf"^{_RE_COMM}$"),
    "<member>": re.compile(rf"^{_RE_COMM}$"),
    "<target>": re.compile(r"^\S+$"),
    "<value>": re.compile(rf"^{_RE_COMM}$"),
    "<object>": re.compile(r"^\S+$"),
    "<read,write,deny>": re.compile(r"^\S+$"),
    "<name=value>": re.compile(r"^\S+=\S+$"),
    "<canonical>": re.compile(r"^\S+$"),
    "<comment>": re.compile(rf"^{_RE_COMM}$"),
    "<name,ip>": re.compile(rf"^{_RE_ZONE},*({_RE_PARTIP})*$"),
    "<ip,ip>": re.compile(rf"{_RE_PARTIP}|,"),
    "<ip>": re.compile(rf"^{_RE_PARTIP}$"),
    "<startip>": re.compile(rf"^{_RE_PARTIP}$"),
    "<endip>": re.compile(rf"^{_RE_PARTIP}$"),
    "<ip_or_name>": re.compile(rf"^{_RE_COMM}$"),
    "<n.n.n.n/mm>": re.compile(rf"^({_RE_IP}/|{_RE_CIDR}|[0-9a-fA-F:]+/\d{{1,3}})$"),
    "<cidr>": re.compile(rf"^({_RE_PARTIP}|{_RE_IP}/|{_RE_CIDR})$"),
    "</cidr>": re.compile(r"^/\d{1,2}$"),
    "<zone>": re.compile(r"^\S+$"),
    "<priority>": re.compile(r"^\d+$"),
    "<weight>": re.compile(r"^\d+$"),
    "<port>": re.compile(r"^\d+$"),
    # Comma-separated list of return-field names used by the `show` handlers'
    # opt-in `fields=a,b,c` parameter. Must match at least one field name;
    # commas separate, no whitespace allowed.
    "<field1,field2,...>": re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:,[A-Za-z_][A-Za-z0-9_]*)*$"),
    "<cr>": re.compile(r"^$"),  # end-of-input terminator; matches the empty string only
    "<key>": re.compile(r"^\S+$"),
    "<serial>": re.compile(r"^\S+$"),
    "<license_type>": re.compile(r"^\S+$"),
}

# Line-prefix aliases applied by process_line before parsing. Keys must be
# simple tokens (no whitespace in the replaced prefix).
#
# The Perl ibcli originally had these aliases pointing at `configure file`
# and `show file` subtrees that were never implemented in the Python port.
# The surviving aliases map to the real `show debug …` subcommands, which
# provide the equivalent introspection.
ALIASES: dict[str, str] = {
    "pwd": "show debug pwd",
    "info": "show debug session",
}


if TYPE_CHECKING:
    from ibcli.context import Context

Handler = Callable[[str, "Context"], Awaitable[None] | None]


DynamicCompleter = Callable[["Context"], list[tuple[str, str]]]


@dataclass
class CommandEntry:
    words: str | None = None
    func: Handler | None = None
    help: str | None = None
    # Optional sync callable that returns [(value, meta), ...] completions,
    # used when the user tab-completes a <special> slot under this waypoint.
    dynamic: DynamicCompleter | None = None


COMMANDS: dict[str, CommandEntry] = {}


def _merge_words(existing: str | None, incoming: str) -> str:
    """Union the token sets of two word lists, preserving first-seen order."""
    if not existing:
        return incoming
    seen: dict[str, None] = {}
    for tok in existing.split():
        seen.setdefault(tok, None)
    for tok in incoming.split():
        seen.setdefault(tok, None)
    return " ".join(seen)


def register(
    match_line: str,
    *,
    words: str | None = None,
    help: str | None = None,
    dynamic: DynamicCompleter | None = None,
) -> None:
    """Register an intermediate command-tree waypoint (no handler).

    If `words` is provided, it is MERGED with any existing word list on the
    same match_line - this lets multiple domain modules contribute to shared
    waypoints (e.g. "configure" gets "server" from server.py and "zone" from
    zone.py).
    """
    entry = COMMANDS.setdefault(match_line, CommandEntry())
    if words is not None:
        entry.words = _merge_words(entry.words, words)
    if help is not None:
        entry.help = help
    if dynamic is not None:
        entry.dynamic = dynamic


def command(match_line: str, *, words: str | None = None, help: str | None = None):
    """Decorator registering a handler under `match_line`.

    Word lists are merged with any prior `register()` / `@command` on the
    same match_line; a non-None help overrides. The handler is set (last one
    wins for the same match_line - but two decorators targeting the same
    match_line is normally a bug and should be avoided).
    """

    def wrap(func: Handler) -> Handler:
        entry = COMMANDS.setdefault(match_line, CommandEntry())
        if words is not None:
            entry.words = _merge_words(entry.words, words)
        if help is not None:
            entry.help = help
        entry.func = func
        return func

    return wrap
