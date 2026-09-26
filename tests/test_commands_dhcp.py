# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for DHCP slices 3a, 3b, and 3c (ranges, fixed, templates, filters, failover, options, leases)."""

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
    """Seed the NULL root entry so the parser resolves top-level words.

    system.py (not yet converted) normally provides this. dhcp.py registers
    all intermediate waypoints it needs, so only the root NULL entry is needed.
    """
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8"))


def _list(items: list[dict]) -> dict:
    """Return a paged list-response body."""
    return {"result": items}


def _api_posts(requests_seen: list, path_fragment: str = "") -> list:
    """Filter POST requests, excluding the SDK's logout call."""
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ===========================================================================
# Range add
# ===========================================================================


class TestRangeAdd:
    async def test_add_range_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(201, json={"_ref": "range/ZG5z:1.2.3.10/1.2.3.50/default"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50", ctx)

        posts = _api_posts(requests_seen, "/range")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["network"] == "1.2.3.0/24"
        assert body["start_addr"] == "1.2.3.10"
        assert body["end_addr"] == "1.2.3.50"

    async def test_add_range_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(201, json={"_ref": "range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50 comment "test range"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/range")
        body = json.loads(posts[0].content)
        assert body["comment"] == "test range"

    async def test_add_range_with_member(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(201, json={"_ref": "range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50 member 10.0.0.1",
                ctx,
            )

        posts = _api_posts(requests_seen, "/range")
        body = json.loads(posts[0].content)
        assert body["member"] == {"_struct": "dhcpmember", "ipv4addr": "10.0.0.1"}

    async def test_add_range_with_failover(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(201, json={"_ref": "range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50 failover myfailover",
                ctx,
            )

        posts = _api_posts(requests_seen, "/range")
        body = json.loads(posts[0].content)
        assert body["failover_association"] == "myfailover"
        assert "member" not in body

    async def test_add_range_with_view(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(201, json={"_ref": "range/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50 view internal",
                ctx,
            )

        posts = _api_posts(requests_seen, "/range")
        body = json.loads(posts[0].content)
        assert body["network_view"] == "internal"

    async def test_add_range_wapi_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and "/range" in request.url.path:
                return httpx.Response(
                    400,
                    json={
                        "Error": "AdmConDataError",
                        "code": "Client.Ibap.Data",
                        "text": "Range overlap",
                    },
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50", ctx)

        # NiosError is caught by the dispatcher; no assertion needed here -
        # the test verifies the command doesn't crash.

    async def test_add_range_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network 1.2.3.0/24 range add 1.2.3.10 1.2.3.50", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Range delete
# ===========================================================================


class TestRangeDelete:
    async def test_delete_range(self):
        ref = "range/ZG5z:1.2.3.10/1.2.3.50/default"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": ref, "start_addr": "1.2.3.10", "end_addr": "1.2.3.50"}]),
                )
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 range delete 1.2.3.10 1.2.3.50", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_modify_range_swaps_failover(self):
        ref = "range/ZG5z:1.2.3.10/1.2.3.50/default"
        puts_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": ref, "start_addr": "1.2.3.10", "end_addr": "1.2.3.50"}]),
                )
            if request.method == "PUT" and ref in request.url.path:
                puts_seen.append(request)
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 range modify 1.2.3.10 1.2.3.50 failover fo-group2",
                ctx,
            )

        assert len(puts_seen) == 1
        body = _body(puts_seen[0])
        assert body.get("failover_association") == "fo-group2"

    async def test_modify_range_errors_without_fields(self, capsys):
        ref = "range/ZG5z:1.2.3.10/1.2.3.50/default"

        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 range modify 1.2.3.10 1.2.3.50", ctx)
        assert "nothing to modify" in capsys.readouterr().out

    async def test_delete_range_with_view(self):
        ref = "range/ZG5z:1.2.3.10/1.2.3.50/internal"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE":
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 range delete 1.2.3.10 1.2.3.50 view internal",
                ctx,
            )

        gets = [r for r in requests_seen if r.method == "GET" and "/range" in r.url.path]
        assert gets, "Expected a GET /range request"
        assert "internal" in str(gets[-1].url)

    async def test_delete_range_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 range delete 1.2.3.10 1.2.3.50", ctx)
        assert "No range found" in capsys.readouterr().out

    async def test_delete_range_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network 1.2.3.0/24 range delete 1.2.3.10 1.2.3.50", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Show range
# ===========================================================================


class TestShowRange:
    async def test_show_range_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "range/a",
                                "network": "1.2.3.0/24",
                                "start_addr": "1.2.3.10",
                                "end_addr": "1.2.3.50",
                                "comment": "",
                                "failover_association": "",
                                "member": None,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show range", ctx)
        out = capsys.readouterr().out
        assert "1.2.3.10" in out
        assert "1.2.3.50" in out

    async def test_show_range_filtered_by_cidr(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/range" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "range/a",
                                "network": "1.2.3.0/24",
                                "start_addr": "1.2.3.10",
                                "end_addr": "1.2.3.50",
                                "comment": "",
                                "failover_association": "",
                                "member": None,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show range 1.2.3.0/24", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/range" in r.url.path]
        assert gets
        assert "1.2.3.0" in str(gets[-1].url)

    async def test_show_range_not_connected(self, capsys):
        ctx = Context()
        await process_line("show range", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Fixed add
# ===========================================================================


class TestFixedAdd:
    async def test_add_fixed_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddress/ZG5z:1.2.3.4/default"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 fixed add 1.2.3.4 aa:bb:cc:dd:ee:ff", ctx
            )

        posts = _api_posts(requests_seen, "/fixedaddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["ipv4addr"] == "1.2.3.4"
        assert body["mac"] == "aa:bb:cc:dd:ee:ff"

    async def test_add_fixed_mac_normalisation(self):
        """MAC without colons should have colons inserted."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 fixed add 1.2.3.4 aabbccddeeff", ctx)

        posts = _api_posts(requests_seen, "/fixedaddress")
        body = json.loads(posts[0].content)
        assert body["mac"] == "aa:bb:cc:dd:ee:ff"

    async def test_add_fixed_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure network 1.2.3.0/24 fixed add 1.2.3.4 aa:bb:cc:dd:ee:ff comment "my host"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/fixedaddress")
        body = json.loads(posts[0].content)
        assert body["comment"] == "my host"

    async def test_add_fixed_with_name(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 fixed add 1.2.3.4 aa:bb:cc:dd:ee:ff name myhost",
                ctx,
            )

        posts = _api_posts(requests_seen, "/fixedaddress")
        body = json.loads(posts[0].content)
        assert body["name"] == "myhost"

    async def test_add_fixed_with_view(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 fixed add 1.2.3.4 aa:bb:cc:dd:ee:ff view internal",
                ctx,
            )

        posts = _api_posts(requests_seen, "/fixedaddress")
        body = json.loads(posts[0].content)
        assert body["network_view"] == "internal"

    async def test_add_fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network 1.2.3.0/24 fixed add 1.2.3.4 aa:bb:cc:dd:ee:ff", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Fixed delete
# ===========================================================================


class TestFixedDelete:
    async def test_delete_fixed(self):
        ref = "fixedaddress/ZG5z:1.2.3.4/default"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fixedaddress" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "ipv4addr": "1.2.3.4"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 fixed delete 1.2.3.4", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_fixed_with_view(self):
        ref = "fixedaddress/ZG5z:1.2.3.4/internal"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fixedaddress" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref}]))
            if request.method == "DELETE":
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network 1.2.3.0/24 fixed delete 1.2.3.4 view internal", ctx
            )

        gets = [r for r in requests_seen if r.method == "GET" and "/fixedaddress" in r.url.path]
        assert gets
        assert "internal" in str(gets[-1].url)

    async def test_delete_fixed_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fixedaddress" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network 1.2.3.0/24 fixed delete 1.2.3.4", ctx)
        assert "No fixed address found" in capsys.readouterr().out

    async def test_delete_fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network 1.2.3.0/24 fixed delete 1.2.3.4", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Show fixed
# ===========================================================================


class TestShowFixed:
    async def test_show_fixed_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fixedaddress" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "fixedaddress/a",
                                "ipv4addr": "1.2.3.4",
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "network": "1.2.3.0/24",
                                "name": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show fixed", ctx)
        out = capsys.readouterr().out
        assert "1.2.3.4" in out
        assert "aa:bb:cc:dd:ee:ff" in out

    async def test_show_fixed_by_ip(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fixedaddress" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "fixedaddress/a",
                                "ipv4addr": "1.2.3.4",
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "network": "1.2.3.0/24",
                                "name": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show fixed 1.2.3.4", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/fixedaddress" in r.url.path]
        assert gets
        assert "1.2.3.4" in str(gets[-1].url)

    async def test_show_fixed_not_connected(self, capsys):
        ctx = Context()
        await process_line("show fixed", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Fixed-address template add / delete / show  (3b)
# ===========================================================================


class TestFixedTemplateAdd:
    async def test_add_template_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddresstemplate/ZG5z:tpl1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template fixed add tpl1", ctx)

        posts = _api_posts(requests_seen, "/fixedaddresstemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "tpl1"
        assert body["number_of_addresses"] == 1

    async def test_add_template_with_offset(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddresstemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template fixed add tpl1 offset 5", ctx)

        posts = _api_posts(requests_seen, "/fixedaddresstemplate")
        body = json.loads(posts[0].content)
        assert body["offset"] == 5

    async def test_add_template_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "fixedaddresstemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure template fixed add tpl1 comment "my template"', ctx)

        posts = _api_posts(requests_seen, "/fixedaddresstemplate")
        body = json.loads(posts[0].content)
        assert body["comment"] == "my template"

    async def test_add_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template fixed add tpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFixedTemplateDelete:
    async def test_delete_template(self):
        ref = "fixedaddresstemplate/ZG5z:tpl1"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "tpl1"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template fixed delete tpl1", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_template_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template fixed delete tpl1", ctx)
        assert "No template found" in capsys.readouterr().out

    async def test_delete_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template fixed delete tpl1", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowFixedTemplate:
    async def test_show_template_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "fixedaddresstemplate/a", "name": "tpl1", "comment": "c1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template fixed", ctx)
        out = capsys.readouterr().out
        assert "tpl1" in out

    async def test_show_template_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fixedaddresstemplate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [{"_ref": "fixedaddresstemplate/a", "name": "tpl1", "comment": "c1"}]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template fixed tpl1", ctx)

        gets = [
            r for r in requests_seen if r.method == "GET" and "/fixedaddresstemplate" in r.url.path
        ]
        assert gets
        assert "tpl1" in str(gets[-1].url)

    async def test_show_template_not_connected(self, capsys):
        ctx = Context()
        await process_line("show template fixed", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# MAC filter add / delete  (3b)
# ===========================================================================


class TestMacFilterAdd:
    async def test_add_macfilter(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/filtermac" in request.url.path:
                return httpx.Response(201, json={"_ref": "filtermac/ZG5z:my_filter"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network macfilter add my_filter", ctx)

        posts = _api_posts(requests_seen, "/filtermac")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "my_filter"

    async def test_add_macfilter_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network macfilter add my_filter", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestMacFilterDelete:
    async def test_delete_macfilter(self):
        ref = "filtermac/ZG5z:my_filter"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "my_filter"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network macfilter delete my_filter", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_macfilter_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network macfilter delete my_filter", ctx)
        assert "No MAC filter found" in capsys.readouterr().out

    async def test_delete_macfilter_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network macfilter delete my_filter", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# MAC filter address add / delete  (3b)
# ===========================================================================

FILTER_REF = "filtermac/ZG5z:my_filter"


class TestMacFilterAddrAdd:
    async def test_add_macfilteraddr(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": FILTER_REF, "name": "my_filter"}]))
            if request.method == "POST" and "/macfilteraddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "macfilteraddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network filter my_filter add macaddress aa:bb:cc:dd:ee:ff", ctx
            )

        posts = _api_posts(requests_seen, "/macfilteraddress")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["mac"] == "aa:bb:cc:dd:ee:ff"
        # WAPI's macfilteraddress.filter is a name, not a _ref, despite the
        # _ref looking like one - sending a _ref returns "does not match any
        # MAC filter" against a real grid (NIOS 9.x).
        assert body["filter"] == "my_filter"

    async def test_add_macfilteraddr_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": FILTER_REF, "name": "my_filter"}]))
            if request.method == "POST" and "/macfilteraddress" in request.url.path:
                return httpx.Response(201, json={"_ref": "macfilteraddress/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure network filter my_filter add macaddress aa:bb:cc:dd:ee:ff comment "test mac"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/macfilteraddress")
        body = json.loads(posts[0].content)
        assert body["comment"] == "test mac"

    async def test_add_macfilteraddr_filter_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network filter my_filter add macaddress aa:bb:cc:dd:ee:ff", ctx
            )
        assert "No MAC filter found" in capsys.readouterr().out

    async def test_add_macfilteraddr_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network filter my_filter add macaddress aa:bb:cc:dd:ee:ff", ctx
        )
        assert "Not connected" in capsys.readouterr().out


class TestMacFilterAddrDelete:
    async def test_delete_macfilteraddr(self):
        addr_ref = "macfilteraddress/ZG5z:aa:bb"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": FILTER_REF, "name": "my_filter"}]))
            if request.method == "GET" and "/macfilteraddress" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": addr_ref, "mac": "aa:bb:cc:dd:ee:ff"}])
                )
            if request.method == "DELETE" and addr_ref in request.url.path:
                return httpx.Response(200, json=addr_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network filter my_filter delete macaddress aa:bb:cc:dd:ee:ff",
                ctx,
            )

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert addr_ref in deletes[0].url.path

    async def test_delete_macfilteraddr_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": FILTER_REF, "name": "my_filter"}]))
            if request.method == "GET" and "/macfilteraddress" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network filter my_filter delete macaddress aa:bb:cc:dd:ee:ff",
                ctx,
            )
        assert "No MAC filter address found" in capsys.readouterr().out


# ===========================================================================
# Show network filter  (3b)
# ===========================================================================


class TestShowNetworkFilter:
    async def test_show_filter_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": FILTER_REF, "name": "my_filter", "comment": ""},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show network filter", ctx)
        out = capsys.readouterr().out
        assert "my_filter" in out

    async def test_show_filter_named(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/filtermac" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": FILTER_REF, "name": "my_filter"}]))
            if request.method == "GET" and "/macfilteraddress" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "macfilteraddress/a",
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "comment": "",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show network filter my_filter", ctx)
        out = capsys.readouterr().out
        assert "aa:bb:cc:dd:ee:ff" in out

    async def test_show_filter_not_connected(self, capsys):
        ctx = Context()
        await process_line("show network filter", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Failover add / delete / show  (3c)
# ===========================================================================


class TestFailoverAdd:
    async def test_add_failover(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/dhcpfailover" in request.url.path:
                return httpx.Response(201, json={"_ref": "dhcpfailover/ZG5z:my_fail"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure network failover add my_fail primary dns01.example.com secondary dns02.example.com",
                ctx,
            )

        posts = _api_posts(requests_seen, "/dhcpfailover")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "my_fail"
        assert body["primary_server_type"] == "GRID"
        assert body["secondary_server_type"] == "GRID"
        assert body["primary"] == "dns01.example.com"
        assert body["secondary"] == "dns02.example.com"

    async def test_add_failover_not_connected(self, capsys):
        ctx = Context()
        await process_line(
            "configure network failover add my_fail primary 1.2.3.1 secondary 1.2.3.2",
            ctx,
        )
        assert "Not connected" in capsys.readouterr().out


class TestFailoverDelete:
    async def test_delete_failover(self):
        ref = "dhcpfailover/ZG5z:my_fail"
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/dhcpfailover" in request.url.path:
                return httpx.Response(200, json=_list([{"_ref": ref, "name": "my_fail"}]))
            if request.method == "DELETE" and ref in request.url.path:
                return httpx.Response(200, json=ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network failover delete my_fail", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1
        assert ref in deletes[0].url.path

    async def test_delete_failover_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/dhcpfailover" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure network failover delete my_fail", ctx)
        assert "No failover found" in capsys.readouterr().out

    async def test_delete_failover_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure network failover delete my_fail", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestShowFailover:
    async def test_show_failover_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/dhcpfailover" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dhcpfailover/a",
                                "name": "my_fail",
                                "primary": "dns01.example.com",
                                "secondary": "dns02.example.com",
                                "comment": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show network failover", ctx)
        out = capsys.readouterr().out
        assert "my_fail" in out

    async def test_show_failover_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/dhcpfailover" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dhcpfailover/a",
                                "name": "my_fail",
                                "primary": "dns01.example.com",
                                "secondary": "dns02.example.com",
                                "comment": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show network failover my_fail", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/dhcpfailover" in r.url.path]
        assert gets
        assert "my_fail" in str(gets[-1].url)

    async def test_show_failover_not_connected(self, capsys):
        ctx = Context()
        await process_line("show network failover", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Option space add  (3c)
# ===========================================================================


class TestOptionSpaceAdd:
    async def test_add_option_space(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/dhcpoptionspace" in request.url.path:
                return httpx.Response(201, json={"_ref": "dhcpoptionspace/ZG5z:SUNW"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure option_space add SUNW", ctx)

        posts = _api_posts(requests_seen, "/dhcpoptionspace")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "SUNW"

    async def test_add_option_space_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure option_space add SUNW", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Optiondef add  (3c)
# ===========================================================================


class TestOptiondefAdd:
    async def test_add_optiondef_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/dhcpoptiondefinition" in request.url.path:
                return httpx.Response(201, json={"_ref": "dhcpoptiondefinition/ZG5z:abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure optiondef add jumpstart code 6 type text", ctx)

        posts = _api_posts(requests_seen, "/dhcpoptiondefinition")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "jumpstart"
        assert body["code"] == 6
        assert body["type"] == "text"
        assert "space" not in body

    async def test_add_optiondef_with_space(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/dhcpoptiondefinition" in request.url.path:
                return httpx.Response(201, json={"_ref": "dhcpoptiondefinition/ZG5z:abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure optiondef add jumpstart code 6 type text space SUNW", ctx)

        posts = _api_posts(requests_seen, "/dhcpoptiondefinition")
        body = json.loads(posts[0].content)
        assert body["space"] == "SUNW"

    async def test_add_optiondef_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure optiondef add jumpstart code 6 type text", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Show network options  (3c)
# ===========================================================================


class TestShowNetworkOptions:
    async def test_show_network_options(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/dhcpoptiondefinition" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dhcpoptiondefinition/a",
                                "name": "jumpstart",
                                "code": 6,
                                "type": "text",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show network options", ctx)
        out = capsys.readouterr().out
        assert "jumpstart" in out

    async def test_show_network_options_not_connected(self, capsys):
        ctx = Context()
        await process_line("show network options", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Show lease  (3c)
# ===========================================================================


class TestShowLease:
    async def test_show_lease_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/lease" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "lease/a",
                                "address": "1.2.3.4",
                                "binding_state": "ACTIVE",
                                "hardware": "aa:bb:cc:dd:ee:ff",
                                "client_hostname": "myhost",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show lease", ctx)
        out = capsys.readouterr().out
        assert "1.2.3.4" in out
        assert "ACTIVE" in out

    async def test_show_lease_by_ip(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/lease" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "lease/a",
                                "address": "1.2.3.4",
                                "binding_state": "ACTIVE",
                                "hardware": "aa:bb:cc:dd:ee:ff",
                                "client_hostname": "",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show lease 1.2.3.4", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/lease" in r.url.path]
        assert gets
        assert "1.2.3.4" in str(gets[-1].url)

    async def test_show_lease_not_connected(self, capsys):
        ctx = Context()
        await process_line("show lease", ctx)
        assert "Not connected" in capsys.readouterr().out
