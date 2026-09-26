# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.threat - Phase 18.

Covers:
  Chunk A: Threat Insight - allowlist (add/delete/show)
           Threat Insight - cloud client (show/set)
           Threat Insight - insight_allowlist (show, read-only)
           Threat Insight - moduleset (show, read-only)
  Chunk B: Threat Protection - profiles (add/delete/set/show)
           Threat Protection - profile rules (show via profile)
           Threat Protection - member-level rules (show)
           Threat Protection - grid-level rules (show/set)
  Chunk C: Threat Protection - rulesets (show/set)
           Threat Protection - rule templates (show, read-only)
           Threat Protection - rule categories (show, read-only)
           Threat Protection - statistics (show, read-only)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- ctx.client.threatinsight.* / ctx.client.threatprotection.* are SDK entry points.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import threat  # noqa: F401  ensures module registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so configure/show are recognised."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# Request-inspection helpers
# ---------------------------------------------------------------------------


def _posts_to(seen: list, fragment: str) -> list:
    return [
        r
        for r in seen
        if r.method == "POST" and fragment in r.url.path and "/logout" not in r.url.path
    ]


def _gets_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "GET" and fragment in r.url.path]


def _deletes_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "DELETE" and fragment in r.url.path]


def _puts_to(seen: list, fragment: str) -> list:
    return [r for r in seen if r.method == "PUT" and fragment in r.url.path]


def _ref(objtype: str, name: str) -> str:
    return f"{objtype}/ZG5z:{name}"


def _list(items: list) -> dict:
    return {"result": items}


# ===========================================================================
# Chunk A: Threat Insight - allowlist
# ===========================================================================


class TestTiAllowlistAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(
                    201, json={"_ref": _ref("threatinsight:allowlist", "evil.com")}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight allowlist add evil.com", ctx)

        posts = _posts_to(seen, "threatinsight:allowlist")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["fqdn"] == "evil.com"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(
                    201, json={"_ref": _ref("threatinsight:allowlist", "safe.com")}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure threat_insight allowlist add safe.com comment="known good"', ctx
            )

        posts = _posts_to(seen, "threatinsight:allowlist")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["fqdn"] == "safe.com"
        assert body["comment"] == "known good"

    async def test_add_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_insight allowlist add bad.com", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTiAllowlistDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []
        ref = _ref("threatinsight:allowlist", "evil.com")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "fqdn": "evil.com"}]))
            if req.method == "DELETE" and ref in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight allowlist evil.com delete", ctx)

        assert any(r.method == "DELETE" and ref in r.url.path for r in seen)

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight allowlist missing.com delete", ctx)

        assert "No allowlist entry found" in capsys.readouterr().out


class TestTiAllowlistShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatinsight:allowlist", "a"),
                                "fqdn": "a.com",
                                "type": "CUSTOM",
                            },
                            {
                                "_ref": _ref("threatinsight:allowlist", "b"),
                                "fqdn": "b.com",
                                "type": "SYSTEM",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight allowlist", ctx)

        out = capsys.readouterr().out
        assert "type=threatinsight:allowlist" in out
        assert "fqdn=a.com" in out
        assert "fqdn=b.com" in out

    async def test_show_filtered(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:allowlist" in req.url.path:
                fqdn_q = req.url.params.get("fqdn")
                if fqdn_q == "a.com":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatinsight:allowlist", "a"), "fqdn": "a.com"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight allowlist a.com", ctx)

        out = capsys.readouterr().out
        assert "fqdn=a.com" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:allowlist" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight allowlist ghost.com", ctx)

        assert "No allowlist entry found" in capsys.readouterr().out


# ===========================================================================
# Chunk A: Threat Insight - cloud client
# ===========================================================================


class TestTiCloudClientShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:cloudclient" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": _ref("threatinsight:cloudclient", "cc"), "enable": True}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight cloud_client", ctx)

        out = capsys.readouterr().out
        assert "type=threatinsight:cloudclient" in out
        assert "enable=True" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight cloud_client", ctx)

        assert capsys.readouterr().out == ""


class TestTiCloudClientSet:
    async def test_set_field(self):
        seen: list[httpx.Request] = []
        ref = _ref("threatinsight:cloudclient", "cc")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatinsight:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "enable": False}]))
            if req.method == "PUT" and ref in req.url.path:
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight cloud_client set enable=true", ctx)

        puts = _puts_to(seen, ref)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable"] is True

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:cloudclient" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("threatinsight:cloudclient", "cc")}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight cloud_client set", ctx)

        assert "Error" in capsys.readouterr().out

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:cloudclient" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_insight cloud_client set enable=true", ctx)

        assert "No cloud client configuration found" in capsys.readouterr().out


# ===========================================================================
# Chunk A: Threat Insight - insight_allowlist (read-only)
# ===========================================================================


class TestTiInsightAllowlistShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:insight_allowlist" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": _ref("threatinsight:insight_allowlist", "v1"), "version": "1.0"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight insight_allowlist", ctx)

        out = capsys.readouterr().out
        assert "type=threatinsight:insight_allowlist" in out
        assert "version=1.0" in out


# ===========================================================================
# Chunk A: Threat Insight - moduleset (read-only)
# ===========================================================================


class TestTiModulesetShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:moduleset" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": _ref("threatinsight:moduleset", "m1"), "version": "2.5"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight moduleset", ctx)

        out = capsys.readouterr().out
        assert "type=threatinsight:moduleset" in out
        assert "version=2.5" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatinsight:moduleset" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_insight moduleset", ctx)

        assert capsys.readouterr().out == ""


# ===========================================================================
# Chunk B: Threat Protection - profiles
# ===========================================================================


class TestTpProfileAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "threatprotection:profile" in req.url.path:
                return httpx.Response(
                    201, json={"_ref": _ref("threatprotection:profile", "MyProfile")}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection profile add MyProfile", ctx)

        posts = _posts_to(seen, "threatprotection:profile")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "MyProfile"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "threatprotection:profile" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("threatprotection:profile", "P2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure threat_protection profile add P2 comment="main profile"', ctx
            )

        posts = _posts_to(seen, "threatprotection:profile")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "P2"
        assert body["comment"] == "main profile"

    async def test_add_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure threat_protection profile add X", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestTpProfileDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []
        ref = _ref("threatprotection:profile", "MyProfile")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "MyProfile"}]))
            if req.method == "DELETE" and ref in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection profile MyProfile delete", ctx)

        assert any(r.method == "DELETE" and ref in r.url.path for r in seen)

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection profile Ghost delete", ctx)

        assert "No threat protection profile found" in capsys.readouterr().out


class TestTpProfileSet:
    async def test_set_comment(self):
        seen: list[httpx.Request] = []
        ref = _ref("threatprotection:profile", "MyProfile")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "MyProfile"}]))
            if req.method == "PUT" and ref in req.url.path:
                return httpx.Response(200, json={"_ref": ref})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure threat_protection profile MyProfile set comment=updated", ctx
            )

        puts = _puts_to(seen, ref)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("threatprotection:profile", "P")}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection profile P set", ctx)

        assert "Error" in capsys.readouterr().out


class TestTpProfileShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:profile", "P1"),
                                "name": "P1",
                                "comment": "first",
                            },
                            {"_ref": _ref("threatprotection:profile", "P2"), "name": "P2"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection profile", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:profile" in out
        assert "name=P1" in out
        assert "name=P2" in out

    async def test_show_specific(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                name_q = req.url.params.get("name")
                if name_q == "P1":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatprotection:profile", "P1"), "name": "P1"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection profile P1", ctx)

        out = capsys.readouterr().out
        assert "name=P1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection profile Ghost", ctx)

        assert "No threat protection profile found" in capsys.readouterr().out


# ===========================================================================
# Chunk B: Threat Protection - profile rules (show only)
# ===========================================================================


class TestTpProfileRuleShow:
    async def test_show_rules_for_profile(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile:rule" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:profile:rule", "r1"),
                                "profile": "MyProfile",
                                "rule": "rule1",
                                "disable": False,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection profile MyProfile rule", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:profile:rule" in out
        assert "profile=MyProfile" in out

    async def test_show_no_rules(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:profile:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection profile EmptyProfile rule", ctx)

        assert "No rules found for profile" in capsys.readouterr().out


# ===========================================================================
# Chunk B: Threat Protection - member-level rules (show only)
# ===========================================================================


class TestTpRuleShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rule" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:rule", "r1"),
                                "member": "member1",
                                "disable": False,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:rule" in out
        assert "member=member1" in out

    async def test_show_filtered(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rule" in req.url.path:
                rule_q = req.url.params.get("rule")
                if rule_q == "myrule":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatprotection:rule", "r1"), "rule": "myrule"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule myrule", ctx)

        out = capsys.readouterr().out
        assert "rule=myrule" in out


# ===========================================================================
# Chunk B: Threat Protection - grid-level rules (show/set)
# ===========================================================================


class TestTpGridRuleShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:grid:rule", "gr1"),
                                "name": "GridRule1",
                                "template": "tmpl1",
                                "comment": "grid wide",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection grid_rule", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:grid:rule" in out
        assert "name=GridRule1" in out

    async def test_show_specific(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                name_q = req.url.params.get("name")
                if name_q == "GR1":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatprotection:grid:rule", "gr1"), "name": "GR1"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection grid_rule GR1", ctx)

        out = capsys.readouterr().out
        assert "name=GR1" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection grid_rule Ghost", ctx)

        assert "No threat protection grid rule found" in capsys.readouterr().out


class TestTpGridRuleSet:
    async def test_set_comment(self):
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
            await process_line("configure threat_protection grid_rule GR1 set comment=updated", ctx)

        puts = _puts_to(seen, ref)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection grid_rule Ghost set comment=x", ctx)

        assert "No threat protection grid rule found" in capsys.readouterr().out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:grid:rule" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("threatprotection:grid:rule", "g")}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection grid_rule GR1 set", ctx)

        assert "Error" in capsys.readouterr().out


# ===========================================================================
# Chunk C: Threat Protection - rulesets (show/set)
# ===========================================================================


class TestTpRulesetShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:ruleset", "rs1"),
                                "version": "v1.0",
                                "comment": "first ruleset",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection ruleset", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:ruleset" in out
        assert "version=v1.0" in out

    async def test_show_specific(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                ver_q = req.url.params.get("version")
                if ver_q == "v1.0":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatprotection:ruleset", "rs1"), "version": "v1.0"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection ruleset v1.0", ctx)

        out = capsys.readouterr().out
        assert "version=v1.0" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection ruleset ghost", ctx)

        assert "No threat protection ruleset found" in capsys.readouterr().out


class TestTpRulesetSet:
    async def test_set_comment(self):
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
            await process_line("configure threat_protection ruleset v1.0 set comment=archived", ctx)

        puts = _puts_to(seen, ref)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "archived"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection ruleset ghost set comment=x", ctx)

        assert "No threat protection ruleset found" in capsys.readouterr().out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruleset" in req.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": _ref("threatprotection:ruleset", "r")}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure threat_protection ruleset v1.0 set", ctx)

        assert "Error" in capsys.readouterr().out


# ===========================================================================
# Chunk C: Threat Protection - rule templates (read-only)
# ===========================================================================


class TestTpRuletemplateShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruletemplate" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:ruletemplate", "t1"),
                                "name": "DNSMalware",
                                "category": "cat1",
                                "ruleset": "v1.0",
                                "description": "Malware detection",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_template", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:ruletemplate" in out
        assert "name=DNSMalware" in out

    async def test_show_filtered(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruletemplate" in req.url.path:
                name_q = req.url.params.get("name")
                if name_q == "DNSMalware":
                    return httpx.Response(
                        200,
                        json=_list(
                            [
                                {
                                    "_ref": _ref("threatprotection:ruletemplate", "t1"),
                                    "name": "DNSMalware",
                                }
                            ]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_template DNSMalware", ctx)

        out = capsys.readouterr().out
        assert "name=DNSMalware" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:ruletemplate" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_template Ghost", ctx)

        assert "No rule template found" in capsys.readouterr().out


# ===========================================================================
# Chunk C: Threat Protection - rule categories (read-only)
# ===========================================================================


class TestTpRulecategoryShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rulecategory" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:rulecategory", "c1"),
                                "name": "DNS",
                                "ruleset": "v1.0",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_category", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:rulecategory" in out
        assert "name=DNS" in out

    async def test_show_filtered(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rulecategory" in req.url.path:
                name_q = req.url.params.get("name")
                if name_q == "DNS":
                    return httpx.Response(
                        200,
                        json=_list(
                            [{"_ref": _ref("threatprotection:rulecategory", "c1"), "name": "DNS"}]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_category DNS", ctx)

        out = capsys.readouterr().out
        assert "name=DNS" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:rulecategory" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection rule_category Ghost", ctx)

        assert "No rule category found" in capsys.readouterr().out


# ===========================================================================
# Chunk C: Threat Protection - statistics (read-only)
# ===========================================================================


class TestTpStatisticsShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:statistics" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("threatprotection:statistics", "s1"),
                                "member": "member1.test",
                                "stat_infos": [],
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection statistics", ctx)

        out = capsys.readouterr().out
        assert "type=threatprotection:statistics" in out
        assert "member=member1.test" in out

    async def test_show_by_member(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:statistics" in req.url.path:
                member_q = req.url.params.get("member")
                if member_q == "grid1.test":
                    return httpx.Response(
                        200,
                        json=_list(
                            [
                                {
                                    "_ref": _ref("threatprotection:statistics", "s1"),
                                    "member": "grid1.test",
                                }
                            ]
                        ),
                    )
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection statistics grid1.test", ctx)

        out = capsys.readouterr().out
        assert "member=grid1.test" in out

    async def test_show_member_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "threatprotection:statistics" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show threat_protection statistics ghost.test", ctx)

        assert "No statistics found for member" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show threat_protection statistics", ctx)
        assert "Not connected" in capsys.readouterr().out
