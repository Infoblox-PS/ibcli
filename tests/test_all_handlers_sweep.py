# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Exhaustive sweep: dispatch *every* registered handler against a mock grid.

The hand-curated lists in ``test_connected_sweep.py`` and
``test_not_connected_sweep.py`` cover the interesting paths. This module
covers the *complete* set instead: it walks ``COMMANDS``, turns each
match-line into a concrete invocation by substituting a placeholder for every
``<token>``, and asserts the handler neither raises nor prints a traceback.

It is a crash guard, not a correctness check - it proves no command can
traceback at the operator, which for a REPL also means no command can kill
the session. It caught three ``delete`` handlers that passed a bare name into
an SDK call requiring a WAPI ``_ref``.

Every special token in ``registry.SPECOPS`` must have a placeholder here, so
adding a new token type to the grammar fails this module until it is listed.
"""

from __future__ import annotations

import contextlib
import io
import re

import httpx
import pytest

import ibcli.commands  # noqa: F401 - registers all command trees
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, SPECOPS
from tests.conftest import make_client

# A representative, grammar-valid value for each special token.
PLACEHOLDERS: dict[str, str] = {
    "<mac>": "00:11:22:33:44:55",
    "<ipv6>": "2001:db8::1",
    "<ipany>": "10.0.0.1",
    "<num>": "10",
    "<svr>": "grid.test",
    "<file>": "/dev/null",
    "<name>": "probe1",
    "<member>": "member1.example.com",
    "<target>": "tgt",
    "<value>": "val",
    "<object>": "network",
    "<read,write,deny>": "read",
    "<name=value>": "k=v",
    "<canonical>": "canon.example.com",
    "<comment>": "c",
    "<name,ip>": "host1,10.0.0.1",
    "<ip,ip>": "10.0.0.1,10.0.0.2",
    "<ip>": "10.0.0.1",
    "<startip>": "10.0.0.10",
    "<endip>": "10.0.0.20",
    "<ip_or_name>": "10.0.0.1",
    "<n.n.n.n/mm>": "10.0.0.0/24",
    "<cidr>": "10.0.0.0/24",
    "</cidr>": "/24",
    "<zone>": "probe.example.com",
    "<priority>": "10",
    "<weight>": "10",
    "<port>": "53",
    "<field1,field2,...>": "name,comment",
    "<key>": "k",
    "<serial>": "ABC123",
    "<license_type>": "DNS",
    "<cr>": "",  # terminator - never appears inside a match-line
}

# `exit`, `quit` and `bye` call sys.exit(0) by design.
_EXITING = {"exit", "quit", "bye"}

# The dispatcher's last-resort handler renders an unexpected exception as
# "  Error: <ClassName>: <message>". NIOS errors are printed as a cleaned
# message with no class prefix, so this pattern only matches a handler that
# leaked something it should have dealt with itself.
_LEAKED_EXCEPTION = re.compile(r"^\s*Error: \w*(?:Error|Exception): ", re.M)


def test_every_specop_has_a_placeholder():
    """A new grammar token must be given a sweep value, or this fails."""
    missing = sorted(set(SPECOPS) - set(PLACEHOLDERS))
    assert not missing, f"add sweep placeholders for: {missing}"


def _concretize(match_line: str) -> str:
    return " ".join(PLACEHOLDERS[tok] if tok.startswith("<") else tok for tok in match_line.split())


def _all_handler_lines() -> list[str]:
    return sorted(
        key
        for key, entry in COMMANDS.items()
        if entry.func and key != "NULL" and key not in _EXITING
    )


def _permissive_handler(request: httpx.Request) -> httpx.Response | None:
    """Answer anything: empty lists for reads, plausible refs for writes."""
    if b"_schema=1" in request.url.query or request.url.path.endswith("/grid/session"):
        return None
    if request.method == "GET":
        return httpx.Response(200, json=[])
    if request.method == "POST":
        obj = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        return httpx.Response(201, json=f"{obj}/abc:x/default")
    if request.method in ("PUT", "DELETE"):
        return httpx.Response(200, json=request.url.path)
    return httpx.Response(200, json={})


@pytest.mark.parametrize("match_line", _all_handler_lines())
async def test_handler_does_not_crash(match_line):
    """Every handler must fail gracefully, never with an escaping exception."""
    line = _concretize(match_line)
    client = make_client(_permissive_handler)
    ctx = Context(client=client, online=True, host="grid.test")
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            await process_line(line, ctx)
    finally:
        await client.aclose()
    out = buf.getvalue()
    assert "Traceback" not in out, out[-1000:]
    # Without this the dispatcher's safety net would hide the very bugs this
    # sweep exists to find: a graceful "Error:" line is fine, an exception
    # class name reaching the operator is not.
    leak = _LEAKED_EXCEPTION.search(out)
    assert leak is None, f"handler leaked an exception: {out.strip()[:500]}"
