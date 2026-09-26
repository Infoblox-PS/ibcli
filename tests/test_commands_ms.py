# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.ms - Phase 17.

Covers:
  Chunk A: MS server registration (add/delete/set/show)
  Chunk B: MS DHCP service config (show/set)
  Chunk C: MS DNS service config (show/set)
  Chunk D: AD sites domain (show-only, read-only)
  Chunk E: AD sites site (add/delete/show)
  Chunk F: MS superscope (add/delete/set/show)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- ctx.client.microsoftserver.* is the SDK entry point.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import ms  # noqa: F401  ensures module registers handlers
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
# Chunk A: MS Server registration
# ===========================================================================


class TestMsServerAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "POST"
                and "msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
            ):
                return httpx.Response(201, json={"_ref": _ref("msserver", "10.0.0.1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server add 10.0.0.1", ctx)

        posts = _posts_to(seen, "/msserver")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["address"] == "10.0.0.1"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "POST"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
            ):
                return httpx.Response(201, json={"_ref": _ref("msserver", "10.0.0.2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server add 10.0.0.2 comment=prod-ms", ctx)

        posts = _posts_to(seen, "/msserver")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["address"] == "10.0.0.2"
        assert body["comment"] == "prod-ms"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server add 10.0.0.1", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
                and "superscope" not in req.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("msserver", "10.0.0.1"), "address": "10.0.0.1"},
                        ]
                    ),
                )
            if req.method == "DELETE" and "/msserver" in req.url.path:
                return httpx.Response(200, json=_ref("msserver", "10.0.0.1"))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 delete", ctx)

        dels = _deletes_to(seen, "/msserver")
        assert len(dels) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.9.9.9 delete", ctx)

        out = capsys.readouterr().out
        assert "No MS server found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 delete", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerSet:
    async def test_set_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
                and "superscope" not in req.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("msserver", "10.0.0.1"), "address": "10.0.0.1"},
                        ]
                    ),
                )
            if req.method == "PUT" and "/msserver" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("msserver", "10.0.0.1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 set comment=updated", ctx)

        puts = _puts_to(seen, "/msserver")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("comment") == "updated"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.9.9.9 set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No MS server found" in out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "/msserver" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("msserver", "10.0.0.1"), "address": "10.0.0.1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 set comment=x", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
                and "superscope" not in req.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver", "10.0.0.1"),
                                "address": "10.0.0.1",
                                "server_name": "ad-server.corp.local",
                                "comment": "primary MS",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server", ctx)

        out = capsys.readouterr().out
        assert "type=msserver" in out
        assert "address=10.0.0.1" in out
        assert "server_name=ad-server.corp.local" in out

    async def test_show_by_address(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
                and "superscope" not in req.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver", "10.0.0.1"),
                                "address": "10.0.0.1",
                                "server_name": "ad-server.corp.local",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1", ctx)

        out = capsys.readouterr().out
        assert "address=10.0.0.1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if (
                req.method == "GET"
                and "/msserver" in req.url.path
                and "dhcp" not in req.url.path
                and "dns" not in req.url.path
                and "adsites" not in req.url.path
                and "superscope" not in req.url.path
            ):
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.9.9.9", ctx)

        out = capsys.readouterr().out
        assert "No MS server found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_server", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# Chunk B: MS DHCP service config
# ===========================================================================


class TestMsServerDhcpShow:
    async def test_show_dhcp(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dhcp" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:dhcp", "10.0.0.1"),
                                "address": "10.0.0.1",
                                "status": "WORKING",
                                "synchronization_interval": 60,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 dhcp", ctx)

        out = capsys.readouterr().out
        assert "type=msserver:dhcp" in out
        assert "address=10.0.0.1" in out
        assert "status=WORKING" in out

    async def test_show_dhcp_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dhcp" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.9.9.9 dhcp", ctx)

        out = capsys.readouterr().out
        assert "No MS DHCP config found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_server 10.0.0.1 dhcp", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerDhcpSet:
    async def test_set_ok(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "msserver:dhcp" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("msserver:dhcp", "10.0.0.1"), "address": "10.0.0.1"},
                        ]
                    ),
                )
            if req.method == "PUT" and "msserver:dhcp" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("msserver:dhcp", "10.0.0.1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure ms_server 10.0.0.1 dhcp set synchronization_interval=30", ctx
            )

        puts = _puts_to(seen, "msserver:dhcp")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("synchronization_interval") == 30

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dhcp" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.9.9.9 dhcp set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No MS DHCP config found" in out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 dhcp set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 dhcp set comment=x", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# Chunk C: MS DNS service config
# ===========================================================================


class TestMsServerDnsShow:
    async def test_show_dns(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dns" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:dns", "10.0.0.1"),
                                "address": "10.0.0.1",
                                "uuid": "abc123",
                                "synchronization_interval": 120,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 dns", ctx)

        out = capsys.readouterr().out
        assert "type=msserver:dns" in out
        assert "address=10.0.0.1" in out
        assert "uuid=abc123" in out

    async def test_show_dns_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dns" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.9.9.9 dns", ctx)

        out = capsys.readouterr().out
        assert "No MS DNS config found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_server 10.0.0.1 dns", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerDnsSet:
    async def test_set_ok(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "msserver:dns" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("msserver:dns", "10.0.0.1"), "address": "10.0.0.1"},
                        ]
                    ),
                )
            if req.method == "PUT" and "msserver:dns" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("msserver:dns", "10.0.0.1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure ms_server 10.0.0.1 dns set enable_dns_reports_sync=true", ctx
            )

        puts = _puts_to(seen, "msserver:dns")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("enable_dns_reports_sync") is True

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:dns" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.9.9.9 dns set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No MS DNS config found" in out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 dns set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 dns set comment=x", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# Chunk D: AD sites domain (read-only, show only)
# ===========================================================================


class TestMsServerAdDomainShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:domain" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:adsites:domain", "corp.local"),
                                "name": "corp.local",
                                "netbios": "CORP",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_domain", ctx)

        out = capsys.readouterr().out
        assert "type=msserver:adsites:domain" in out
        assert "name=corp.local" in out
        assert "netbios=CORP" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:domain" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:adsites:domain", "corp.local"),
                                "name": "corp.local",
                                "netbios": "CORP",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_domain corp.local", ctx)

        out = capsys.readouterr().out
        assert "name=corp.local" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:domain" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_domain nosuchdomain", ctx)

        out = capsys.readouterr().out
        assert "No AD domain found" in out

    async def test_show_empty_no_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:domain" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_domain", ctx)

        out = capsys.readouterr().out
        assert "No AD domains found for server" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_server 10.0.0.1 ad_domain", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# Chunk E: AD sites site (full CRUD)
# ===========================================================================


class TestMsServerAdSiteAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("msserver:adsites:site", "HQ")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 ad_site add HQ", ctx)

        posts = _posts_to(seen, "msserver:adsites:site")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "HQ"
        assert body["domain"] == "10.0.0.1"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("msserver:adsites:site", "Branch")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure ms_server 10.0.0.1 ad_site add Branch comment=branch-office", ctx
            )

        posts = _posts_to(seen, "msserver:adsites:site")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "Branch"
        assert body["comment"] == "branch-office"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 ad_site add HQ", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerAdSiteDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:adsites:site", "HQ"),
                                "name": "HQ",
                                "domain": "10.0.0.1",
                            },
                        ]
                    ),
                )
            if req.method == "DELETE" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(200, json=_ref("msserver:adsites:site", "HQ"))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 ad_site HQ delete", ctx)

        dels = _deletes_to(seen, "msserver:adsites:site")
        assert len(dels) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_server 10.0.0.1 ad_site nosuchsite delete", ctx)

        out = capsys.readouterr().out
        assert "No AD site found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_server 10.0.0.1 ad_site HQ delete", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsServerAdSiteShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:adsites:site", "HQ"),
                                "name": "HQ",
                                "domain": "10.0.0.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_site", ctx)

        out = capsys.readouterr().out
        assert "type=msserver:adsites:site" in out
        assert "name=HQ" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("msserver:adsites:site", "HQ"),
                                "name": "HQ",
                                "domain": "10.0.0.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_site HQ", ctx)

        out = capsys.readouterr().out
        assert "name=HQ" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_site nosuchsite", ctx)

        out = capsys.readouterr().out
        assert "No AD site found" in out

    async def test_show_empty_no_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "msserver:adsites:site" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_server 10.0.0.1 ad_site", ctx)

        out = capsys.readouterr().out
        assert "No AD sites found for server" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_server 10.0.0.1 ad_site", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


# ===========================================================================
# Chunk F: MS superscope
# ===========================================================================


class TestMsSuperscopeAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "mssuperscope" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("mssuperscope", "scope1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope add scope1", ctx)

        posts = _posts_to(seen, "mssuperscope")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "scope1"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "mssuperscope" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("mssuperscope", "scope2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope add scope2 comment=prod-scope", ctx)

        posts = _posts_to(seen, "mssuperscope")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "scope2"
        assert body["comment"] == "prod-scope"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_superscope add scope1", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsSuperscopeDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("mssuperscope", "scope1"), "name": "scope1"},
                        ]
                    ),
                )
            if req.method == "DELETE" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json=_ref("mssuperscope", "scope1"))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope scope1 delete", ctx)

        dels = _deletes_to(seen, "mssuperscope")
        assert len(dels) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope nosuchscope delete", ctx)

        out = capsys.readouterr().out
        assert "No MS superscope found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_superscope scope1 delete", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsSuperscopeSet:
    async def test_set_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("mssuperscope", "scope1"), "name": "scope1"},
                        ]
                    ),
                )
            if req.method == "PUT" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("mssuperscope", "scope1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope scope1 set comment=updated", ctx)

        puts = _puts_to(seen, "mssuperscope")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("comment") == "updated"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope nosuch set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No MS superscope found" in out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("mssuperscope", "scope1"), "name": "scope1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ms_superscope scope1 set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure ms_superscope scope1 set comment=x", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestMsSuperscopeShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("mssuperscope", "scope1"),
                                "name": "scope1",
                                "network_view": "default",
                                "comment": "prod superscope",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_superscope", ctx)

        out = capsys.readouterr().out
        assert "type=mssuperscope" in out
        assert "name=scope1" in out
        assert "network_view=default" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("mssuperscope", "scope1"),
                                "name": "scope1",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_superscope scope1", ctx)

        out = capsys.readouterr().out
        assert "name=scope1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_superscope nosuchscope", ctx)

        out = capsys.readouterr().out
        assert "No MS superscope found" in out

    async def test_show_all_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "mssuperscope" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ms_superscope", ctx)

        out = capsys.readouterr().out
        assert out == ""

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show ms_superscope", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out
