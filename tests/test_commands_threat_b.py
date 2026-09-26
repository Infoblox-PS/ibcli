# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Chunk B supplement tests - Threat Protection profiles, profile_rule, rule, grid_rule.

Additional edge cases beyond the baseline coverage in test_commands_threat.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import threat  # noqa: F401
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _list(items: list) -> dict:
    return {"result": items}


def _ref(objtype: str, name: str) -> str:
    return f"{objtype}/ZG5z:{name}"


class TestTpProfileNotConnected:
    """Not-connected guard for all profile mutating commands."""

    async def test_delete_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_protection profile P delete", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_set_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_protection profile P set comment=x", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection profile", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpRuleNotConnected:
    async def test_rule_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection rule", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_grid_rule_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection grid_rule", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_grid_rule_set_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_protection grid_rule GR set comment=x", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_profile_rule_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection profile P rule", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpRuleShowEmpty:
    async def test_show_empty_no_filter(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule", ctx)

        # No output - just no crash
        assert capsys.readouterr().out == ""

    async def test_show_not_found_named(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule ghostrule", ctx)

        assert "No threat protection rule found" in capsys.readouterr().out


class TestTpGridRuleSetIntCoerce:
    """Verify int coercion passes through to the PUT body."""

    async def test_set_numeric_field(self):
        import json

        seen: list[httpx.Request] = []
        ref = _ref("threatprotection:grid:rule", "gr1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "GR1"}]))
            if req.method == "PUT" and ref in req.url.path:
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection grid_rule GR1 set sid=12345", ctx)

        puts = [r for r in seen if r.method == "PUT" and ref in r.url.path]
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["sid"] == 12345
