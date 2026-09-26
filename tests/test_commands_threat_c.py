# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Chunk C supplement tests - Threat Protection rulesets, rule_templates, rule_categories, statistics.

Additional edge cases beyond baseline coverage in test_commands_threat.py.
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


class TestTpRulesetNotConnected:
    async def test_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection ruleset", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_set_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_protection ruleset v1 set comment=x", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpRuletemplateNotConnected:
    async def test_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection rule_template", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpRulecategoryNotConnected:
    async def test_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection rule_category", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpStatisticsNotConnected:
    async def test_show_not_connected_explicit(self, capsys):
        # Redundant with baseline - confirms guard present in this chunk too
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection statistics", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpRulesetDoNotDelete:
    """Verify do_not_delete bool coercion flows through PUT body."""

    async def test_set_do_not_delete_true(self):
        import json

        seen: list[httpx.Request] = []
        ref = _ref("threatprotection:ruleset", "rs1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "version": "v1.0"}]))
            if req.method == "PUT" and ref in req.url.path:
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure threat_protection ruleset v1.0 set do_not_delete=true", ctx
            )

        puts = [r for r in seen if r.method == "PUT" and ref in r.url.path]
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["do_not_delete"] is True


class TestTpRuletemplateShowEmpty:
    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruletemplate" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_template", ctx)

        assert capsys.readouterr().out == ""


class TestTpRulecategoryShowMultiple:
    async def test_show_multiple(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rulecategory" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:rulecategory", "c1"),
                                "name": "DNS",
                                "ruleset": "v1",
                            },
                            {
                                "_ref": _ref("threatprotection:rulecategory", "c2"),
                                "name": "HTTP",
                                "ruleset": "v1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_category", ctx)

        out = capsys.readouterr().out
        assert "name=DNS" in out
        assert "name=HTTP" in out


class TestTpStatisticsMultiMember:
    async def test_show_multiple_members(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:statistics" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:statistics", "s1"),
                                "member": "m1.test",
                            },
                            {
                                "_ref": _ref("threatprotection:statistics", "s2"),
                                "member": "m2.test",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection statistics", ctx)

        out = capsys.readouterr().out
        assert "member=m1.test" in out
        assert "member=m2.test" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:statistics" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection statistics", ctx)

        assert capsys.readouterr().out == ""
