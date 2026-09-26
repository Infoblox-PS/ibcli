# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for IPv6 DHCP parity: ipv6range, ipv6fixed, ipv6 templates,
ipv6 option space/def, ipv6 shared network (Chunks A-E)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import dhcp  # noqa: F401  - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _list(items: list[dict]) -> dict:
    return {"result": items}


def _api_posts(requests_seen: list, path_fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ===========================================================================
# Chunk A: IPv6 range add / delete / show
# ===========================================================================


class TestIpv6RangeAdd:
    async def test_add_ipv6range_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6range" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6range/ZG5z:abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range add 2001:db8::10 2001:db8::50",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6range")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["network"] == "2001:db8::/32"
        assert body["start_addr"] == "2001:db8::10"
        assert body["end_addr"] == "2001:db8::50"

    async def test_add_ipv6range_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6range" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range add 2001:db8::10 2001:db8::50"
                ' comment "v6 range"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6range")
        body = json.loads(posts[0].content)
        assert body["comment"] == "v6 range"

    async def test_add_ipv6range_with_member(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6range" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range add 2001:db8::10 2001:db8::50"
                " member 2001:db8::1",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6range")
        body = json.loads(posts[0].content)
        assert body["member"] == {"_struct": "dhcpmember", "ipv6addr": "2001:db8::1"}

    async def test_add_ipv6range_with_view(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6range" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range add 2001:db8::10 2001:db8::50"
                " view internal",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6range")
        body = json.loads(posts[0].content)
        assert body["network_view"] == "internal"

    async def test_add_ipv6range_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network 2001:db8::/32 ipv6range add 2001:db8::10 2001:db8::50",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestIpv6RangeDelete:
    async def test_delete_ipv6range(self):
        ref = "ipv6range/ZG5z:abc"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": ref, "start_addr": "2001:db8::10", "end_addr": "2001:db8::50"}]
                    ),
                )
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range delete 2001:db8::10 2001:db8::50",
                ctx,
            )

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_ipv6range_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6range" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6range delete 2001:db8::10 2001:db8::50",
                ctx,
            )
        assert "No IPv6 range found" in capsys.readouterr().out

    async def test_delete_ipv6range_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network 2001:db8::/32 ipv6range delete 2001:db8::10 2001:db8::50",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6Range:
    async def test_show_ipv6range_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6range/a",
                                "network": "2001:db8::/32",
                                "start_addr": "2001:db8::10",
                                "end_addr": "2001:db8::50",
                                "comment": "",
                                "member": None,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6range", ctx)
        out = capsys.readouterr().out
        assert "2001:db8::10" in out
        assert "2001:db8::50" in out

    async def test_show_ipv6range_filtered_by_cidr(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6range" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6range 2001:db8::/32", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/ipv6range" in r.url.path]
        assert gets
        assert "2001" in str(gets[-1].url)

    async def test_show_ipv6range_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ipv6range", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B: IPv6 fixed add / delete / show
# ===========================================================================


class TestIpv6FixedAdd:
    async def test_add_ipv6fixed_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddress/ZG5z:abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed add 2001:db8::1 00:01:00:01:aa:bb:cc:dd",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6fixedaddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ipv6addr"] == "2001:db8::1"
        assert body["duid"] == "00:01:00:01:aa:bb:cc:dd"
        assert body["match_client"] == "DUID"

    async def test_add_ipv6fixed_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed add 2001:db8::1"
                ' 00:01:00:01:aa:bb:cc:dd comment "my v6 host"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6fixedaddress")
        body = json.loads(posts[0].content)
        assert body["comment"] == "my v6 host"

    async def test_add_ipv6fixed_with_name(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed add 2001:db8::1"
                " 00:01:00:01:aa:bb:cc:dd name myv6host",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6fixedaddress")
        body = json.loads(posts[0].content)
        assert body["name"] == "myv6host"

    async def test_add_ipv6fixed_with_view(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed add 2001:db8::1"
                " 00:01:00:01:aa:bb:cc:dd view internal",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6fixedaddress")
        body = json.loads(posts[0].content)
        assert body["network_view"] == "internal"

    async def test_add_ipv6fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network 2001:db8::/32 ipv6fixed add 2001:db8::1 00:01:00:01:aa:bb:cc:dd",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestIpv6FixedDelete:
    async def test_delete_ipv6fixed(self):
        ref = "ipv6fixedaddress/ZG5z:abc"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "ipv6addr": "2001:db8::1"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed delete 2001:db8::1",
                ctx,
            )

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_ipv6fixed_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 2001:db8::/32 ipv6fixed delete 2001:db8::1",
                ctx,
            )
        assert "No IPv6 fixed address found" in capsys.readouterr().out

    async def test_delete_ipv6fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network 2001:db8::/32 ipv6fixed delete 2001:db8::1",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6Fixed:
    async def test_show_ipv6fixed_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6fixedaddress/a",
                                "ipv6addr": "2001:db8::1",
                                "duid": "00:01:00:01:aa:bb:cc:dd",
                                "network": "2001:db8::/32",
                                "name": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6fixed", ctx)
        out = capsys.readouterr().out
        assert "2001:db8::1" in out
        assert "00:01:00:01:aa:bb:cc:dd" in out

    async def test_show_ipv6fixed_by_ip(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6fixedaddress" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6fixedaddress/a",
                                "ipv6addr": "2001:db8::1",
                                "duid": "00:01:00:01:aa:bb:cc:dd",
                                "network": "2001:db8::/32",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6fixed 2001:db8::1", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/ipv6fixedaddress" in r.url.path]
        assert gets
        assert "2001" in str(gets[-1].url)

    async def test_show_ipv6fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ipv6fixed", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk C: IPv6 fixed-address template + IPv6 range template
# ===========================================================================


class TestIpv6FixedTemplateAdd:
    async def test_add_ipv6fixed_template_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddresstemplate/ZG5z:tpl1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6fixed add v6tpl1", ctx)

        posts = _api_posts(requests_seen, "/ipv6fixedaddresstemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "v6tpl1"
        assert body["number_of_addresses"] == 1

    async def test_add_ipv6fixed_template_with_offset(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddresstemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6fixed add v6tpl1 offset 10", ctx)

        posts = _api_posts(requests_seen, "/ipv6fixedaddresstemplate")
        body = json.loads(posts[0].content)
        assert body["offset"] == 10

    async def test_add_ipv6fixed_template_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6fixedaddresstemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure template ipv6fixed add v6tpl1 comment "ipv6 tpl"', ctx)

        posts = _api_posts(requests_seen, "/ipv6fixedaddresstemplate")
        body = json.loads(posts[0].content)
        assert body["comment"] == "ipv6 tpl"

    async def test_add_ipv6fixed_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template ipv6fixed add v6tpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestIpv6FixedTemplateDelete:
    async def test_delete_ipv6fixed_template(self):
        ref = "ipv6fixedaddresstemplate/ZG5z:v6tpl1"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "v6tpl1"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6fixed delete v6tpl1", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_ipv6fixed_template_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6fixed delete v6tpl1", ctx)
        assert "No IPv6 fixed template found" in capsys.readouterr().out

    async def test_delete_ipv6fixed_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template ipv6fixed delete v6tpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6FixedTemplate:
    async def test_show_ipv6fixed_template_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "ipv6fixedaddresstemplate/a", "name": "v6tpl1", "comment": "c1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template ipv6fixed", ctx)
        out = capsys.readouterr().out
        assert "v6tpl1" in out

    async def test_show_ipv6fixed_template_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6fixedaddresstemplate" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "ipv6fixedaddresstemplate/a", "name": "v6tpl1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template ipv6fixed v6tpl1", ctx)

        gets = [
            r
            for r in requests_seen
            if r.method == "GET" and "/ipv6fixedaddresstemplate" in r.url.path
        ]
        assert gets
        assert "v6tpl1" in str(gets[-1].url)

    async def test_show_ipv6fixed_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("show template ipv6fixed", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestIpv6RangeTemplateAdd:
    async def test_add_ipv6range_template_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6rangetemplate/ZG5z:rtpl1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6range add rtpl1", ctx)

        posts = _api_posts(requests_seen, "/ipv6rangetemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "rtpl1"
        assert body["number_of_addresses"] == 1

    async def test_add_ipv6range_template_with_offset(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6rangetemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6range add rtpl1 offset 5", ctx)

        posts = _api_posts(requests_seen, "/ipv6rangetemplate")
        body = json.loads(posts[0].content)
        assert body["offset"] == 5

    async def test_add_ipv6range_template_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6rangetemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure template ipv6range add rtpl1 comment "v6 range tpl"', ctx)

        posts = _api_posts(requests_seen, "/ipv6rangetemplate")
        body = json.loads(posts[0].content)
        assert body["comment"] == "v6 range tpl"

    async def test_add_ipv6range_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template ipv6range add rtpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestIpv6RangeTemplateDelete:
    async def test_delete_ipv6range_template(self):
        ref = "ipv6rangetemplate/ZG5z:rtpl1"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "rtpl1"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6range delete rtpl1", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_ipv6range_template_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template ipv6range delete rtpl1", ctx)
        assert "No IPv6 range template found" in capsys.readouterr().out

    async def test_delete_ipv6range_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template ipv6range delete rtpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6RangeTemplate:
    async def test_show_ipv6range_template_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "ipv6rangetemplate/a", "name": "rtpl1", "comment": "c1"}]),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template ipv6range", ctx)
        out = capsys.readouterr().out
        assert "rtpl1" in out

    async def test_show_ipv6range_template_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6rangetemplate" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "ipv6rangetemplate/a", "name": "rtpl1"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template ipv6range rtpl1", ctx)

        gets = [
            r for r in requests_seen if r.method == "GET" and "/ipv6rangetemplate" in r.url.path
        ]
        assert gets
        assert "rtpl1" in str(gets[-1].url)

    async def test_show_ipv6range_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("show template ipv6range", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D: IPv6 option space + option def
# ===========================================================================


class TestIpv6OptionSpaceAdd:
    async def test_add_ipv6_option_space(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6dhcpoptionspace" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6dhcpoptionspace/ZG5z:SUNW6"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ipv6optionspace add SUNW6", ctx)

        posts = _api_posts(requests_seen, "/ipv6dhcpoptionspace")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "SUNW6"

    async def test_add_ipv6_option_space_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure ipv6optionspace add SUNW6", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestIpv6OptiondefAdd:
    async def test_add_ipv6_optiondef_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6dhcpoptiondefinition" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6dhcpoptiondefinition/ZG5z:abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure ipv6optiondef add ntp-server code 56 type ip-address", ctx
            )

        posts = _api_posts(requests_seen, "/ipv6dhcpoptiondefinition")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "ntp-server"
        assert body["code"] == 56
        assert body["type"] == "ip-address"
        assert "space" not in body

    async def test_add_ipv6_optiondef_with_space(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6dhcpoptiondefinition" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6dhcpoptiondefinition/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure ipv6optiondef add ntp-server code 56 type ip-address space SUNW6",
                ctx,
            )

        posts = _api_posts(requests_seen, "/ipv6dhcpoptiondefinition")
        body = json.loads(posts[0].content)
        assert body["space"] == "SUNW6"

    async def test_add_ipv6_optiondef_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure ipv6optiondef add ntp-server code 56 type ip-address", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6Options:
    async def test_show_ipv6_options(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6dhcpoptiondefinition" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6dhcpoptiondefinition/a",
                                "name": "ntp-server",
                                "code": 56,
                                "type": "ip-address",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6options", ctx)
        out = capsys.readouterr().out
        assert "ntp-server" in out

    async def test_show_ipv6_options_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ipv6options", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk E: IPv6 shared network
# ===========================================================================


class TestIpv6SharedAdd:
    async def test_add_ipv6shared_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6sharednetwork/ZG5z:myshared"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ipv6shared add myshared", ctx)

        posts = _api_posts(requests_seen, "/ipv6sharednetwork")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myshared"

    async def test_add_ipv6shared_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6sharednetwork/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure ipv6shared add myshared comment "shared v6 net"', ctx)

        posts = _api_posts(requests_seen, "/ipv6sharednetwork")
        body = json.loads(posts[0].content)
        assert body["comment"] == "shared v6 net"

    async def test_add_ipv6shared_with_view(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(201, json={"_ref": "ipv6sharednetwork/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ipv6shared add myshared view internal", ctx)

        posts = _api_posts(requests_seen, "/ipv6sharednetwork")
        body = json.loads(posts[0].content)
        assert body["network_view"] == "internal"

    async def test_add_ipv6shared_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure ipv6shared add myshared", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestIpv6SharedDelete:
    async def test_delete_ipv6shared(self):
        ref = "ipv6sharednetwork/ZG5z:myshared"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "myshared"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ipv6shared delete myshared", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_ipv6shared_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure ipv6shared delete myshared", ctx)
        assert "No IPv6 shared network found" in capsys.readouterr().out

    async def test_delete_ipv6shared_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure ipv6shared delete myshared", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowIpv6Shared:
    async def test_show_ipv6shared_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6sharednetwork/a",
                                "name": "myshared",
                                "comment": "",
                                "network_view": "default",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6shared", ctx)
        out = capsys.readouterr().out
        assert "myshared" in out

    async def test_show_ipv6shared_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/ipv6sharednetwork" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "ipv6sharednetwork/a", "name": "myshared", "comment": ""}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ipv6shared myshared", ctx)

        gets = [
            r for r in requests_seen if r.method == "GET" and "/ipv6sharednetwork" in r.url.path
        ]
        assert gets
        assert "myshared" in str(gets[-1].url)

    async def test_show_ipv6shared_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ipv6shared", ctx)
        assert "Not connected" in capsys.readouterr().out
