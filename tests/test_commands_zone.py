# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.zone - async SDK style."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import zone  # noqa: F401
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Register the NULL root entry so the parser can find top-level words.

    Normally provided by system.py (which registers NULL with help/quit/configure/show
    etc.), but that module is not yet converted. Register the minimal subset needed
    for zone commands so the parser resolves configure and show correctly.
    """
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# Minimal valid list-response helpers
# ---------------------------------------------------------------------------


def _zone_list(zones: list[dict]) -> dict:
    """Return a paged list response body for zone resources."""
    return {"result": zones}


def _rec_list(records: list[dict]) -> dict:
    """Return a paged list response body for record resources."""
    return {"result": records}


def _api_posts(requests_seen: list, path_fragment: str = "") -> list:
    """Filter POST requests, excluding the SDK's logout call."""
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ---------------------------------------------------------------------------
# Zone add tests
# ---------------------------------------------------------------------------


async def test_add_auth_zone():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/ZG5z:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "foo.com"


async def test_add_forward_zone():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_forward" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_forward/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com forward_to ns1,1.2.3.4", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_forward" in r.url.path]
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "foo.com"
    assert body["forward_to"] == [{"name": "ns1", "address": "1.2.3.4"}]


async def test_add_delegated_zone():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_delegated" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_delegated/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com delegate_to ns1,1.2.3.4", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_delegated" in r.url.path]
    assert len(posts) == 1


async def test_add_stub_zone():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_stub" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_stub/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com stub_from ns1,1.2.3.4", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_stub" in r.url.path]
    assert len(posts) == 1


async def test_add_zone_with_comment_and_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(201, json={"_ref": "zone_auth/abc:foo.com/v1", "fqdn": "foo.com"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure zone add foo.com comment "hello world" view v1', ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "foo.com"
    assert body["comment"] == "hello world"
    assert body["view"] == "v1"


async def test_add_reverse_zone_rewrites_cidr_to_arpa():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/abc:.../default", "fqdn": "3.2.1.in-addr.arpa"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add 1.2.3.0/24", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "3.2.1.in-addr.arpa"


async def test_add_zone_wapi_error_prints_error(capsys):
    """A 400 WAPI error from the SDK is caught by the dispatcher and printed."""

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                400,
                json={
                    "Error": "AdmConDataError",
                    "code": "Client.Ibap.Data",
                    "text": "Zone already exists",
                },
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com", ctx)

    out = capsys.readouterr().out
    assert "Error" in out


# ---------------------------------------------------------------------------
# Zone show tests
# ---------------------------------------------------------------------------


async def test_show_zone_fqdn_queries_auth(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {
                            "_ref": "zone_auth/abc:foo.com/default",
                            "fqdn": "foo.com",
                            "comment": "hi",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show zone foo.com", ctx)

    out = capsys.readouterr().out
    assert "foo.com" in out
    assert "hi" in out


async def test_show_zone_falls_back_to_forward_then_delegated(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(200, json=_zone_list([]))
        if request.method == "GET" and "/zone_forward" in request.url.path:
            return httpx.Response(200, json=_zone_list([]))
        if request.method == "GET" and "/zone_delegated" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": "zone_delegated/abc:foo.com/default", "fqdn": "foo.com"},
                    ]
                ),
            )
        if request.method == "GET" and "/zone_stub" in request.url.path:
            return httpx.Response(200, json=_zone_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show zone foo.com", ctx)

    out = capsys.readouterr().out
    assert "foo.com" in out


async def test_show_zone_all_when_no_name(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": "zone_auth/abc:foo.com/default", "fqdn": "foo.com"},
                        {"_ref": "zone_auth/abc:bar.com/default", "fqdn": "bar.com"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show zone", ctx)

    out = capsys.readouterr().out
    assert "foo.com" in out
    assert "bar.com" in out


# ---------------------------------------------------------------------------
# Zone modify tests
# ---------------------------------------------------------------------------


async def test_modify_zone_gets_then_puts():
    ref = "zone_auth/abc:foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": ref, "fqdn": "foo.com"},
                    ]
                ),
            )
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref, "fqdn": "foo.com"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure zone foo.com modify comment "updated"', ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert body["comment"] == "updated"


async def test_delete_zone_gets_then_deletes():
    ref = "zone_auth/abc:foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": ref, "fqdn": "foo.com"},
                    ]
                ),
            )
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com delete", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1


async def test_delete_zone_with_view_filter():
    ref = "zone_auth/abc:foo.com/external"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": ref, "fqdn": "foo.com", "view": "external"},
                    ]
                ),
            )
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com delete view external", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/zone_auth" in r.url.path]
    assert len(gets) >= 1
    assert "view=external" in str(gets[0].url)


async def test_modify_zone_not_found_prints_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            for zt in ("zone_auth", "zone_forward", "zone_delegated", "zone_stub"):
                if f"/{zt}" in request.url.path:
                    return httpx.Response(200, json=_zone_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone nope.com modify comment hi", ctx)

    assert "No zone found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Host record tests
# ---------------------------------------------------------------------------


async def test_add_host_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "record:host" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "record:host/abc:web.foo.com/default", "name": "web.foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com add host web 1.2.3.4", ctx)

    posts = _api_posts(requests_seen, "record:host")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "web.foo.com"
    assert body["ipv4addrs"] == [{"ipv4addr": "1.2.3.4"}]


async def test_add_host_with_mac_and_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "record:host" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "record:host/abc:web.foo.com/default", "name": "web.foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure zone foo.com add host web 1.2.3.4 mac aa:bb:cc:dd:ee:ff comment "webserver"',
            ctx,
        )

    posts = _api_posts(requests_seen, "record:host")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["ipv4addrs"][0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert body["comment"] == "webserver"


async def test_delete_host_looks_up_then_deletes():
    ref = "record:host/abc:web.foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {"_ref": ref, "name": "web.foo.com"},
                    ]
                ),
            )
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com delete host web", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in str(deletes[0].url)


# ---------------------------------------------------------------------------
# Simple record add / delete tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd,field,value",
    [
        ("a web 1.2.3.4", "ipv4addr", "1.2.3.4"),
        ("aaaa web fe80::1", "ipv6addr", "fe80::1"),
        ("cname alias web.foo.com", "canonical", "web.foo.com"),
        ('txt web "some text"', "text", "some text"),
    ],
)
async def test_add_simple_record(cmd, field, value):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            # Determine the record type from the URL path
            rtype = request.url.path.split("/")[-1].split("?")[0]
            return httpx.Response(
                201, json={"_ref": f"{rtype}/abc:.../default", "name": "web.foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"configure zone foo.com add {cmd}", ctx)

    posts = _api_posts(requests_seen)
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    name_part = cmd.split()[1]
    assert body["name"].startswith(name_part)
    assert body[field] == value


@pytest.mark.parametrize(
    "recname,wapi_type",
    [
        ("a", "record:a"),
        ("aaaa", "record:aaaa"),
        ("cname", "record:cname"),
        ("txt", "record:txt"),
    ],
)
async def test_delete_simple_record(recname, wapi_type):
    ref = f"{wapi_type}/abc:web.foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {"_ref": ref, "name": "web.foo.com"},
                    ]
                ),
            )
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"configure zone foo.com delete {recname} web", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in str(deletes[0].url)


# ---------------------------------------------------------------------------
# MX and PTR tests
# ---------------------------------------------------------------------------


async def test_add_mx_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"_ref": "record:mx/abc:.../default", "name": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com add mx foo.com mail.foo.com 10", ctx)

    posts = _api_posts(requests_seen, "record:mx")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "foo.com"
    assert body["mail_exchanger"] == "mail.foo.com"
    assert body["preference"] == 10


async def test_add_ptr_record():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"_ref": "record:ptr/abc:.../default", "ptrdname": "host.foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone 1.2.3.0/24 add ptr 1.2.3.4 host.foo.com", ctx)

    posts = _api_posts(requests_seen, "record:ptr")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["ipv4addr"] == "1.2.3.4"
    assert body["ptrdname"] == "host.foo.com"


async def test_delete_mx_record():
    ref = "record:mx/abc:foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {"_ref": ref, "name": "foo.com"},
                    ]
                ),
            )
        if request.method == "DELETE":
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com delete mx foo.com", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in str(deletes[0].url)


# ---------------------------------------------------------------------------
# Show record tests
# ---------------------------------------------------------------------------


async def test_show_record_a(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if (
            request.method == "GET"
            and "record%3Aa" in request.url.path
            or (request.method == "GET" and "record:a" in request.url.path)
        ):
            return httpx.Response(
                200,
                json=_rec_list(
                    [
                        {
                            "_ref": "record:a/abc:web.foo.com/default",
                            "name": "web.foo.com",
                            "ipv4addr": "1.2.3.4",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record a_record=web.foo.com", ctx)

    out = capsys.readouterr().out
    assert "web.foo.com" in out
    assert "1.2.3.4" in out


async def test_show_record_host_uses_name_param():
    """show record info=<name> queries host, a, aaaa, cname in order."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            # Return empty for all - we just want to verify the GET hit record:host
            return httpx.Response(200, json=_rec_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record info=web.foo.com", ctx)

    get_paths = [str(r.url) for r in requests_seen if r.method == "GET"]
    assert any("record%3Ahost" in p or "record:host" in p for p in get_paths)


# ---------------------------------------------------------------------------
# EA (extattrs) pass-through tests
# ---------------------------------------------------------------------------


async def test_add_zone_with_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com set owner alice", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "foo.com"
    assert body["extattrs"] == {"owner": {"value": "alice"}}


async def test_add_zone_with_multiple_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com set owner alice set env prod", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    body = json.loads(posts[0].content)
    assert body["extattrs"] == {
        "owner": {"value": "alice"},
        "env": {"value": "prod"},
    }


async def test_modify_zone_with_extattrs():
    ref = "zone_auth/abc:foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": ref, "fqdn": "foo.com"},
                    ]
                ),
            )
        if request.method == "PUT":
            return httpx.Response(200, json={"_ref": ref, "fqdn": "foo.com"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com modify set owner bob", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert body["extattrs"] == {"owner": {"value": "bob"}}


async def test_add_host_with_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201, json={"_ref": "record:host/abc:web.foo.com/default", "name": "web.foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com add host web 1.2.3.4 set owner alice", ctx)

    posts = _api_posts(requests_seen, "record:host")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["extattrs"] == {"owner": {"value": "alice"}}


# ---------------------------------------------------------------------------
# Primary / secondary options
# ---------------------------------------------------------------------------


async def test_add_zone_with_primary():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone add foo.com primary ns1.corp.com", ctx)

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    body = json.loads(posts[0].content)
    assert body["fqdn"] == "foo.com"
    assert body["grid_primary"] == [{"name": "ns1.corp.com"}]


async def test_add_zone_with_secondary():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/zone_auth" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "zone_auth/abc:foo.com/default", "fqdn": "foo.com"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone add foo.com primary ns1.corp.com secondary ns2.corp.com", ctx
        )

    posts = [r for r in requests_seen if r.method == "POST" and "/zone_auth" in r.url.path]
    body = json.loads(posts[0].content)
    assert body["grid_primary"] == [{"name": "ns1.corp.com"}]
    assert body["grid_secondaries"] == [{"name": "ns2.corp.com"}]


async def test_modify_zone_with_primary():
    ref = "zone_auth/abc:foo.com/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200,
                json=_zone_list(
                    [
                        {"_ref": ref, "fqdn": "foo.com"},
                    ]
                ),
            )
        if request.method == "PUT":
            return httpx.Response(200, json={"_ref": ref, "fqdn": "foo.com"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone foo.com modify primary ns1.corp.com", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert body["grid_primary"] == [{"name": "ns1.corp.com"}]


# ===========================================================================
# configure zone <zone> rename host <old> <new>
# ===========================================================================


async def test_rename_host_puts_name_only():
    """Rename issues a GET for the old record then a PUT with {name: new_fqdn}."""
    ref = "record:host/abc:web01.zone01.example.com/default"
    puts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "_ref": ref,
                            "name": "web01.zone01.example.com",
                            "ipv4addrs": [{"ipv4addr": "10.0.0.1"}],
                        }
                    ]
                },
            )
        if request.method == "PUT":
            puts.append(request)
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone zone01.example.com rename host web01 web-prod01",
            ctx,
        )
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert body == {"name": "web-prod01.zone01.example.com"}


async def test_rename_host_not_found_prints_error(capsys):
    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone zone01.example.com rename host nope new",
            ctx,
        )
    assert "No host record found" in capsys.readouterr().out


async def test_rename_host_not_connected_prints_error(capsys):
    await process_line(
        "configure zone zone01.example.com rename host a b",
        Context(),
    )
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# configure zone <zone> dnssec sign|unsign|rollover_ksk|rollover_zsk
# ===========================================================================


@pytest.mark.parametrize(
    "verb,wapi_op",
    [
        ("sign", "SIGN"),
        ("unsign", "UNSIGN"),
        ("rollover_ksk", "ROLLOVER_KSK"),
        ("rollover_zsk", "ROLLOVER_ZSK"),
    ],
)
async def test_dnssec_verbs_call_correct_operation(verb, wapi_op):
    ref = "zone_auth/abc:zone01.example.com/default"
    posts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": ref, "fqdn": "zone01.example.com"}]}
            )
        if request.method == "POST" and "dnssec_operation" in str(request.url.params):
            posts.append(request)
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"configure zone zone01.example.com dnssec {verb}", ctx)
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {"operation": wapi_op}


async def test_dnssec_no_zone_found(capsys):
    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone missing.example.com dnssec sign", ctx)
    assert "No auth zone found" in capsys.readouterr().out


async def test_dnssec_not_connected(capsys):
    await process_line("configure zone a.com dnssec sign", Context())
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# configure zone <zone> copy from <zone>
# ===========================================================================


async def test_zone_copy_calls_copyzonerecords_on_source():
    """copyzonerecords is POSTed on the SOURCE zone ref with
    destination_zone=<dst-ref>."""
    src_ref = "zone_auth/abc:src.example.com/default"
    dst_ref = "zone_auth/xyz:dst.example.com/default"
    posts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            fqdn = request.url.params.get("fqdn", "")
            if fqdn == "dst.example.com":
                return httpx.Response(200, json={"result": [{"_ref": dst_ref, "fqdn": fqdn}]})
            if fqdn == "src.example.com":
                return httpx.Response(200, json={"result": [{"_ref": src_ref, "fqdn": fqdn}]})
            return httpx.Response(200, json={"result": []})
        if request.method == "POST" and "copyzonerecords" in str(request.url.params):
            posts.append(request)
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone dst.example.com copy from src.example.com", ctx)
    assert len(posts) == 1
    assert src_ref in str(posts[0].url)
    body = json.loads(posts[0].content)
    assert body == {"destination_zone": dst_ref}


async def test_zone_copy_missing_destination(capsys):
    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone dst.example.com copy from src.example.com", ctx)
    assert "No destination zone found" in capsys.readouterr().out


async def test_zone_copy_missing_source(capsys):
    dst_ref = "zone_auth/xyz:dst.example.com/default"

    def handler(request):
        if request.method == "GET" and "/zone_auth" in request.url.path:
            fqdn = request.url.params.get("fqdn", "")
            if fqdn == "dst.example.com":
                return httpx.Response(200, json={"result": [{"_ref": dst_ref, "fqdn": fqdn}]})
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone dst.example.com copy from src.example.com", ctx)
    assert "No source zone found" in capsys.readouterr().out


async def test_zone_copy_not_connected(capsys):
    await process_line("configure zone a.com copy from b.com", Context())
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# AXFR zone import: configure zone add with import_from=
# ===========================================================================


async def test_zone_add_with_import_from_sets_use_import_from():
    posts: list[httpx.Request] = []

    def handler(request):
        if request.method == "POST" and "/zone_auth" in request.url.path:
            posts.append(request)
            return httpx.Response(201, json="zone_auth/abc:corp.example.com")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone add corp.example.com primary=ibdns01.example.com "
            "import_from=10.99.0.53 do_host_abstraction=true "
            "create_ptr_for_hosts=true",
            ctx,
        )
    body = json.loads(posts[0].content)
    assert body["import_from"] == "10.99.0.53"
    assert body["use_import_from"] is True
    assert body["do_host_abstraction"] is True
    assert body["create_ptr_for_hosts"] is True


# ===========================================================================
# configure zone <zone> modify host <name>  (add/remove alias/ip/ipv6/comment)
# ===========================================================================


async def test_modify_host_adds_alias():
    ref = "record:host/abc:web01.zone01.example.com/default"
    puts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "_ref": ref,
                            "name": "web01.zone01.example.com",
                            "aliases": ["www.zone01.example.com"],
                            "ipv4addrs": [
                                {"ipv4addr": "10.0.0.1", "host": "web01.zone01.example.com"}
                            ],
                        }
                    ]
                },
            )
        if request.method == "PUT":
            puts.append(request)
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone zone01.example.com modify host web01 add-alias=portal",
            ctx,
        )
    body = json.loads(puts[0].content)
    assert set(body["aliases"]) == {"www.zone01.example.com", "portal.zone01.example.com"}


async def test_modify_host_removes_alias_and_strips_readonly_from_ipv4addrs():
    ref = "record:host/abc:web01.zone01.example.com/default"
    puts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "_ref": ref,
                            "name": "web01.zone01.example.com",
                            "aliases": ["www.zone01.example.com", "portal.zone01.example.com"],
                            # host field is read-only - the PUT must not echo it back.
                            "ipv4addrs": [
                                {
                                    "_ref": "record:host_ipv4addr/xyz",
                                    "ipv4addr": "10.0.0.1",
                                    "host": "web01.zone01.example.com",
                                    "configure_for_dhcp": False,
                                }
                            ],
                        }
                    ]
                },
            )
        if request.method == "PUT":
            puts.append(request)
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone zone01.example.com modify host web01 "
            "remove-alias=portal add-ip=10.99.0.1",
            ctx,
        )
    body = json.loads(puts[0].content)
    assert body["aliases"] == ["www.zone01.example.com"]
    # ipv4addrs should contain two entries, with no read-only `host`/`_ref`.
    for entry in body["ipv4addrs"]:
        assert "_ref" not in entry
        assert "host" not in entry
    addrs = [e["ipv4addr"] for e in body["ipv4addrs"]]
    assert set(addrs) == {"10.0.0.1", "10.99.0.1"}


async def test_modify_host_ipv6_add_remove():
    ref = "record:host/abc:web01.zone01.example.com/default"
    puts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "_ref": ref,
                            "name": "web01.zone01.example.com",
                            "ipv6addrs": [
                                {"ipv6addr": "2001:db8::1", "host": "web01.zone01.example.com"}
                            ],
                        }
                    ]
                },
            )
        if request.method == "PUT":
            puts.append(request)
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure zone zone01.example.com modify host web01 "
            "remove-ipv6=2001:db8::1 add-ipv6=2001:db8::2",
            ctx,
        )
    body = json.loads(puts[0].content)
    addrs = [e["ipv6addr"] for e in body["ipv6addrs"]]
    assert addrs == ["2001:db8::2"]


async def test_modify_host_comment_and_disable():
    ref = "record:host/abc:web01.zone01.example.com/default"
    puts: list[httpx.Request] = []

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": ref, "name": "web01.zone01.example.com"}]}
            )
        if request.method == "PUT":
            puts.append(request)
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure zone zone01.example.com modify host web01 comment "decomm" disable=true',
            ctx,
        )
    body = json.loads(puts[0].content)
    assert body["comment"] == "decomm"
    assert body["disable"] is True


async def test_modify_host_nothing_to_modify_prints_error(capsys):
    ref = "record:host/abc:web01.zone01.example.com/default"

    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": ref, "name": "web01.zone01.example.com"}]}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone zone01.example.com modify host web01", ctx)
    assert "Nothing to modify" in capsys.readouterr().out


async def test_modify_host_not_found(capsys):
    def handler(request):
        if request.method == "GET" and "/record:host" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure zone zone01.example.com modify host nope add-alias=x", ctx)
    assert "No host record found" in capsys.readouterr().out


async def test_modify_host_not_connected(capsys):
    await process_line(
        "configure zone zone01.example.com modify host web01 add-alias=x",
        Context(),
    )
    assert "Not connected" in capsys.readouterr().out
