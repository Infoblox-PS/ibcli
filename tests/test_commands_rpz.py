# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.rpz - Phase 6.

Covers:
  Chunk A: configure/show rpz zone
  Chunk B: simple records (cname, a, aaaa, txt)
  Chunk C: IP-variant records (a_ipaddress, aaaa_ipaddress, cname_clientipaddress,
           cname_clientipaddressdn, cname_ipaddress, cname_ipaddressdn)
  Chunk D: other record rewrites (mx, srv, ptr, naptr, https, svcb)
  Chunk E: allrpzrecords aggregator (show rpz records)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import rpz  # noqa: F401  ensures module registers handlers
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
# Helpers
# ---------------------------------------------------------------------------


def _list_resp(items: list[dict]) -> dict:
    return {"result": items}


def _zone_rp_ref(name: str = "rpz.example.com") -> str:
    return f"zone_rp/ZG5z:{name}/default"


def _rpz_rec_ref(rectype: str, name: str = "bad.example.com") -> str:
    return f"{rectype}/ZG5z:{name}/default"


def _posts_to(requests_seen: list, path_fragment: str) -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST" and path_fragment in r.url.path and "/logout" not in r.url.path
    ]


def _gets_to(requests_seen: list, path_fragment: str) -> list:
    return [r for r in requests_seen if r.method == "GET" and path_fragment in r.url.path]


def _deletes_to(requests_seen: list, path_fragment: str) -> list:
    return [r for r in requests_seen if r.method == "DELETE" and path_fragment in r.url.path]


# ===========================================================================
# Chunk A: RPZ zone
# ===========================================================================


class TestRpzZoneAdd:
    async def test_add_basic(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "zone_rp" in req.url.path:
                return httpx.Response(201, json={"_ref": _zone_rp_ref(), "fqdn": "rpz.example.com"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure rpz zone add rpz.example.com", ctx)

        posts = _posts_to(seen, "zone_rp")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["fqdn"] == "rpz.example.com"

    async def test_add_with_view_and_policy(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "zone_rp" in req.url.path:
                return httpx.Response(201, json={"_ref": _zone_rp_ref(), "fqdn": "rpz.example.com"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz zone add rpz.example.com view external policy NXDOMAIN",
                ctx,
            )

        posts = _posts_to(seen, "zone_rp")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["view"] == "external"
        assert body["rpz_policy"] == "NXDOMAIN"

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "zone_rp" in req.url.path:
                return httpx.Response(201, json={"_ref": _zone_rp_ref(), "fqdn": "rpz.example.com"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure rpz zone add rpz.example.com comment "threat feed"', ctx)

        posts = _posts_to(seen, "zone_rp")
        body = json.loads(posts[0].content)
        assert body["comment"] == "threat feed"


class TestRpzZoneDelete:
    async def test_delete_existing(self):
        seen: list[httpx.Request] = []
        ref = _zone_rp_ref()

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "zone_rp" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "fqdn": "rpz.example.com"}])
                )
            if req.method == "DELETE" and "zone_rp" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure rpz zone rpz.example.com delete", ctx)

        dels = _deletes_to(seen, "zone_rp")
        assert len(dels) == 1
        assert ref in dels[0].url.path

    async def test_delete_not_found_prints_message(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "zone_rp" in req.url.path:
                return httpx.Response(200, json=_list_resp([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure rpz zone nothere.example.com delete", ctx)

        out = capsys.readouterr().out
        assert "No RPZ zone found" in out


class TestRpzZoneShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "zone_rp" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": _zone_rp_ref(),
                                "fqdn": "rpz.example.com",
                                "rpz_policy": "NXDOMAIN",
                                "view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz zone", ctx)

        out = capsys.readouterr().out
        assert "rpz.example.com" in out
        assert "type=rpz" in out

    async def test_show_specific(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "zone_rp" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {"_ref": _zone_rp_ref(), "fqdn": "rpz.example.com"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "rpz.example.com" in out

    async def test_show_not_found_prints_message(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "zone_rp" in req.url.path:
                return httpx.Response(200, json=_list_resp([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz zone nothere.example.com", ctx)

        out = capsys.readouterr().out
        assert "No RPZ zone found" in out


# ===========================================================================
# Chunk B: Simple RPZ records - cname, a, aaaa, txt
# ===========================================================================


class TestRpzRecordCname:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:cname" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": _rpz_rec_ref("record:rpz:cname"), "name": "bad.example.com"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname add bad.example.com walled.internal zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:cname")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "bad.example.com"
        assert body["canonical"] == "walled.internal"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = _rpz_rec_ref("record:rpz:cname")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:cname" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp([{"_ref": ref, "name": "bad.example.com"}]),
                )
            if req.method == "DELETE" and "record:rpz:cname" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname bad.example.com delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:cname")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:cname" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": _rpz_rec_ref("record:rpz:cname"),
                                "name": "bad.example.com",
                                "canonical": "walled.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record cname zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "bad.example.com" in out
        assert "walled.internal" in out


class TestRpzRecordA:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:a" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": _rpz_rec_ref("record:rpz:a"), "name": "bad.example.com"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record a add bad.example.com 1.2.3.4 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:a")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ipv4addr"] == "1.2.3.4"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = _rpz_rec_ref("record:rpz:a")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:a" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "name": "bad.example.com"}])
                )
            if req.method == "DELETE" and "record:rpz:a" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record a bad.example.com delete zone rpz.example.com", ctx
            )

        dels = _deletes_to(seen, "record:rpz:a")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:a" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": _rpz_rec_ref("record:rpz:a"),
                                "name": "bad.example.com",
                                "ipv4addr": "1.2.3.4",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record a zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "1.2.3.4" in out


class TestRpzRecordAaaa:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:aaaa" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": _rpz_rec_ref("record:rpz:aaaa"), "name": "bad.example.com"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record aaaa add bad.example.com ::1 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:aaaa")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ipv6addr"] == "::1"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = _rpz_rec_ref("record:rpz:aaaa")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:aaaa" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "name": "bad.example.com"}])
                )
            if req.method == "DELETE" and "record:rpz:aaaa" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record aaaa bad.example.com delete zone rpz.example.com", ctx
            )

        dels = _deletes_to(seen, "record:rpz:aaaa")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:aaaa" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": _rpz_rec_ref("record:rpz:aaaa"),
                                "name": "bad.example.com",
                                "ipv6addr": "::1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record aaaa zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "::1" in out


class TestRpzRecordTxt:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:txt" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": _rpz_rec_ref("record:rpz:txt"), "name": "bad.example.com"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record txt add bad.example.com blocked zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:txt")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["text"] == "blocked"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = _rpz_rec_ref("record:rpz:txt")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:txt" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "name": "bad.example.com"}])
                )
            if req.method == "DELETE" and "record:rpz:txt" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record txt bad.example.com delete zone rpz.example.com", ctx
            )

        dels = _deletes_to(seen, "record:rpz:txt")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:txt" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": _rpz_rec_ref("record:rpz:txt"),
                                "name": "bad.example.com",
                                "text": "blocked",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record txt zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "blocked" in out


# ===========================================================================
# Chunk C: IP-address / client-IP variants
# ===========================================================================


class TestRpzRecordAIpaddress:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:a:ipaddress" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": "record:rpz:a:ipaddress/abc", "name": "192.0.2.0/24.rpz-ip"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record a_ipaddress add 192.0.2.0/24.rpz-ip 10.0.0.1 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:a:ipaddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ipv4addr"] == "10.0.0.1"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:a:ipaddress/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:a:ipaddress" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "name": "192.0.2.0/24.rpz-ip"}])
                )
            if req.method == "DELETE" and "record:rpz:a:ipaddress" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record a_ipaddress 192.0.2.0/24.rpz-ip delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:a:ipaddress")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:a:ipaddress" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:a:ipaddress/abc",
                                "name": "192.0.2.0/24.rpz-ip",
                                "ipv4addr": "10.0.0.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record a_ipaddress zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "10.0.0.1" in out


class TestRpzRecordCnameClientipaddress:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:cname:clientipaddress" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": "record:rpz:cname:clientipaddress/abc"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname_clientipaddress add "
                "192.0.2.0/24.rpz-client-ip walled.internal zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:cname:clientipaddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["canonical"] == "walled.internal"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:cname:clientipaddress/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:cname:clientipaddress" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:cname:clientipaddress" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname_clientipaddress "
                "192.0.2.0/24.rpz-client-ip delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:cname:clientipaddress")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:cname:clientipaddress" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:cname:clientipaddress/abc",
                                "canonical": "walled.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record cname_clientipaddress zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "walled.internal" in out


class TestRpzRecordCnameIpaddress:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:cname:ipaddress" in req.url.path:
                return httpx.Response(
                    201,
                    json={"_ref": "record:rpz:cname:ipaddress/abc"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname_ipaddress add "
                "198.51.100.0/24.rpz-ip walled.internal zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:cname:ipaddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["canonical"] == "walled.internal"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:cname:ipaddress/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:cname:ipaddress" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:cname:ipaddress" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record cname_ipaddress "
                "198.51.100.0/24.rpz-ip delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:cname:ipaddress")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:cname:ipaddress" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:cname:ipaddress/abc",
                                "canonical": "walled.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record cname_ipaddress zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "walled.internal" in out


# ===========================================================================
# Chunk D: Other record rewrites
# ===========================================================================


class TestRpzRecordMx:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:mx" in req.url.path:
                return httpx.Response(
                    201, json={"_ref": "record:rpz:mx/abc", "name": "bad.example.com"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record mx add bad.example.com mail.internal 10 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:mx")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["mail_exchanger"] == "mail.internal"
        assert body["preference"] == 10
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:mx/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:mx" in req.url.path:
                return httpx.Response(
                    200, json=_list_resp([{"_ref": ref, "name": "bad.example.com"}])
                )
            if req.method == "DELETE" and "record:rpz:mx" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record mx bad.example.com delete zone rpz.example.com", ctx
            )

        dels = _deletes_to(seen, "record:rpz:mx")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:mx" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:mx/abc",
                                "name": "bad.example.com",
                                "mail_exchanger": "mail.internal",
                                "preference": 10,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record mx zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "mail.internal" in out
        assert "type=rpz:mx" in out


class TestRpzRecordSrv:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:srv" in req.url.path:
                return httpx.Response(201, json={"_ref": "record:rpz:srv/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record srv add _sip._tcp.example.com sip.internal 10 20 5060 "
                "zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:srv")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["target"] == "sip.internal"
        assert body["priority"] == 10
        assert body["weight"] == 20
        assert body["port"] == 5060
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:srv/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:srv" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:srv" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record srv _sip._tcp.example.com delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:srv")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:srv" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:srv/abc",
                                "name": "_sip._tcp.example.com",
                                "target": "sip.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record srv zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "sip.internal" in out


class TestRpzRecordPtr:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:ptr" in req.url.path:
                return httpx.Response(201, json={"_ref": "record:rpz:ptr/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record ptr add 4.3.2.1.in-addr.arpa bad.example.com "
                "zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:ptr")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ptrdname"] == "bad.example.com"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:ptr/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:ptr" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:ptr" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record ptr 4.3.2.1.in-addr.arpa delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:ptr")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:ptr" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:ptr/abc",
                                "name": "4.3.2.1.in-addr.arpa",
                                "ptrdname": "bad.example.com",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record ptr zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "bad.example.com" in out


class TestRpzRecordNaptr:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:naptr" in req.url.path:
                return httpx.Response(201, json={"_ref": "record:rpz:naptr/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record naptr add bad.example.com 10 20 sip.internal "
                "zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:naptr")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["order"] == 10
        assert body["preference"] == 20
        assert body["replacement"] == "sip.internal"
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:naptr/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:naptr" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:naptr" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record naptr bad.example.com delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:naptr")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:naptr" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:naptr/abc",
                                "name": "bad.example.com",
                                "replacement": "sip.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record naptr zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "sip.internal" in out


class TestRpzRecordHttps:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:https" in req.url.path:
                return httpx.Response(201, json={"_ref": "record:rpz:https/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record https add bad.example.com safe.internal 1 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:https")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["target_name"] == "safe.internal"
        assert body["priority"] == 1
        assert body["rp_zone"] == "rpz.example.com"

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:https/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:https" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:https" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record https bad.example.com delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:https")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:https" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:https/abc",
                                "name": "bad.example.com",
                                "target_name": "safe.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record https zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "safe.internal" in out


class TestRpzRecordSvcb:
    async def test_add(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "record:rpz:svcb" in req.url.path:
                return httpx.Response(201, json={"_ref": "record:rpz:svcb/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record svcb add bad.example.com safe.internal 1 zone rpz.example.com",
                ctx,
            )

        posts = _posts_to(seen, "record:rpz:svcb")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["target_name"] == "safe.internal"
        assert body["priority"] == 1

    async def test_delete(self):
        seen: list[httpx.Request] = []
        ref = "record:rpz:svcb/abc"

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "record:rpz:svcb" in req.url.path:
                return httpx.Response(200, json=_list_resp([{"_ref": ref}]))
            if req.method == "DELETE" and "record:rpz:svcb" in req.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure rpz record svcb bad.example.com delete zone rpz.example.com",
                ctx,
            )

        dels = _deletes_to(seen, "record:rpz:svcb")
        assert len(dels) == 1

    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "record:rpz:svcb" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "record:rpz:svcb/abc",
                                "name": "bad.example.com",
                                "target_name": "safe.internal",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz record svcb zone rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "safe.internal" in out


# ===========================================================================
# Chunk E: allrpzrecords aggregator
# ===========================================================================


class TestRpzAllRecords:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "allrpzrecords" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list_resp(
                        [
                            {
                                "_ref": "allrpzrecords/abc",
                                "name": "bad.example.com",
                                "type": "record:rpz:cname",
                                "zone": "rpz.example.com",
                            },
                            {
                                "_ref": "allrpzrecords/def",
                                "name": "evil.example.com",
                                "type": "record:rpz:a",
                                "zone": "rpz.example.com",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz records zone=rpz.example.com", ctx)

        out = capsys.readouterr().out
        assert "bad.example.com" in out
        assert "evil.example.com" in out
        assert "record:rpz:cname" in out

    async def test_bare_form_prints_helpful_error(self, capsys):
        async with connected_ctx(None) as ctx:
            await process_line("show rpz records", ctx)
        out = capsys.readouterr().out
        assert "Error: zone required" in out

    async def test_show_empty_result(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "allrpzrecords" in req.url.path:
                return httpx.Response(200, json=_list_resp([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show rpz records zone=rpz.example.com", ctx)

        out = capsys.readouterr().out
        # No crash, empty output is fine
        assert out == ""
