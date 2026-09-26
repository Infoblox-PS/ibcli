# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.network - async SDK style."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import network  # noqa: F401  - registers handlers
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


# ---------------------------------------------------------------------------
# configure network add
# ---------------------------------------------------------------------------


async def test_add_network():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/ZG5z:1.2.3.0/24/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add 1.2.3.0/24", ctx)

    posts = _api_posts(requests_seen, "/network")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body == {"network": "1.2.3.0/24"}


async def test_add_network_with_comment_and_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../v1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network add 1.2.3.0/24 comment "lab net" view v1', ctx)

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["network"] == "1.2.3.0/24"
    assert body["comment"] == "lab net"
    assert body["network_view"] == "v1"


async def test_add_network_with_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure network add 1.2.3.0/24 set owner=alice set region=us-west", ctx
        )

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["extattrs"] == {
        "owner": {"value": "alice"},
        "region": {"value": "us-west"},
    }


async def test_add_network_normalizes_short_cidr():
    """Verify short-form CIDR normalization for scripts that bypass the parser."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../default"})
        return None

    from ibcli.commands.network import cli_add_network

    async with connected_ctx(handler) as ctx:
        await cli_add_network("configure network add 10.0.0/8", ctx)

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["network"] == "10.0.0.0/8"


async def test_add_network_not_connected(capsys):
    ctx = Context()
    await process_line("configure network add 1.2.3.0/24", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_add_network_with_one_member():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add 10.0.0.0/24 member 10.0.0.1", ctx)

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["network"] == "10.0.0.0/24"
    assert body["members"] == [{"_struct": "dhcpmember", "ipv4addr": "10.0.0.1"}]


async def test_add_network_with_two_members():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add 10.0.0.0/24 member 10.0.0.1 member 10.0.0.2", ctx)

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["network"] == "10.0.0.0/24"
    assert body["members"] == [
        {"_struct": "dhcpmember", "ipv4addr": "10.0.0.1"},
        {"_struct": "dhcpmember", "ipv4addr": "10.0.0.2"},
    ]


async def test_add_network_members_with_comment_and_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": "network/abc:.../v1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure network add 10.1.0.0/24 member 10.0.0.1 member 10.0.0.2"
            ' comment "subnet-01" view v1',
            ctx,
        )

    posts = _api_posts(requests_seen, "/network")
    body = json.loads(posts[0].content)
    assert body["network"] == "10.1.0.0/24"
    assert body["comment"] == "subnet-01"
    assert body["network_view"] == "v1"
    assert body["members"] == [
        {"_struct": "dhcpmember", "ipv4addr": "10.0.0.1"},
        {"_struct": "dhcpmember", "ipv4addr": "10.0.0.2"},
    ]


# ---------------------------------------------------------------------------
# configure network delete / modify
# ---------------------------------------------------------------------------


async def test_delete_network():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 delete", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_delete_network_with_view():
    ref = "network/abc:1.2.3.0/24/v1"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(
                200,
                json=_list([{"_ref": ref, "network": "1.2.3.0/24", "network_view": "v1"}]),
            )
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 delete view v1", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/network" in r.url.path]
    assert any("network_view=v1" in str(r.url) for r in gets)


async def test_delete_network_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 delete", ctx)

    assert "No network found" in capsys.readouterr().out


async def test_modify_network_comment():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network 1.2.3.0/24 modify comment "new note"', ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {"comment": "new note"}


async def test_modify_network_extattrs():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 modify set owner=bob", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert json.loads(puts[0].content)["extattrs"] == {"owner": {"value": "bob"}}


async def test_extattrs_set_merges_with_existing():
    ref = "network/abc:1.2.3.0/24/default"
    puts_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and ref in request.url.path:
            return httpx.Response(
                200,
                json={
                    "_ref": ref,
                    "network": "1.2.3.0/24",
                    "extattrs": {"Owner": {"value": "alice"}},
                },
            )
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            puts_seen.append(request)
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network 1.2.3.0/24 extattrs set "DC Location" DC1', ctx)

    assert len(puts_seen) == 1
    body = json.loads(puts_seen[0].content)
    assert body["extattrs"] == {
        "Owner": {"value": "alice"},
        "DC Location": {"value": "DC1"},
    }


async def test_extattrs_delete_removes_only_named_ea():
    ref = "network/abc:1.2.3.0/24/default"
    puts_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and ref in request.url.path:
            return httpx.Response(
                200,
                json={
                    "_ref": ref,
                    "network": "1.2.3.0/24",
                    "extattrs": {
                        "Owner": {"value": "alice"},
                        "DC Location": {"value": "DC1"},
                    },
                },
            )
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            puts_seen.append(request)
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network 1.2.3.0/24 extattrs delete "DC Location"', ctx)

    body = json.loads(puts_seen[0].content)
    assert body["extattrs"] == {"Owner": {"value": "alice"}}


async def test_modify_network_extattrs_quoted_name():
    """EA names with spaces must pass through `set "DC Location" DC1`."""
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network 1.2.3.0/24 modify set "DC Location" DC1', ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content)["extattrs"] == {
        "DC Location": {"value": "DC1"},
    }


# ---------------------------------------------------------------------------
# show network
# ---------------------------------------------------------------------------


async def test_show_network_all(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            if "ipv6network" in request.url.path:
                return httpx.Response(200, json=_list([]))
            if "/network" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "network/abc:1.2.3.0/24/default",
                                "network": "1.2.3.0/24",
                                "comment": "lab",
                            },
                            {"_ref": "network/abc:10.0.0.0/8/default", "network": "10.0.0.0/8"},
                        ]
                    ),
                )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network", ctx)

    out = capsys.readouterr().out
    assert "1.2.3.0/24" in out
    assert "10.0.0.0/8" in out
    assert "lab" in out


async def test_show_network_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {"_ref": "network/abc:1.2.3.0/24/default", "network": "1.2.3.0/24"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/network" in r.url.path]
    assert any(
        "network=1.2.3.0%2F24" in str(r.url) or "network=1.2.3.0/24" in str(r.url) for r in gets
    )
    assert "1.2.3.0/24" in capsys.readouterr().out


async def test_show_network_with_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "network/abc:1.2.3.0/24/v1",
                            "network": "1.2.3.0/24",
                            "network_view": "v1",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24 view v1", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/network" in r.url.path]
    assert any("network_view=v1" in str(r.url) for r in gets)


async def test_show_network_none_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 9.9.9.0/24", ctx)

    assert "No network found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Sub-slice 2b: network containers
# ---------------------------------------------------------------------------


async def test_add_network_container():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/networkcontainer" in request.url.path:
            return httpx.Response(201, json={"_ref": "networkcontainer/ZG5z:1.2.3.0/24/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network container add 1.2.3.0/24", ctx)

    posts = _api_posts(requests_seen, "/networkcontainer")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body == {"network": "1.2.3.0/24"}


async def test_add_network_container_with_comment_and_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/networkcontainer" in request.url.path:
            return httpx.Response(201, json={"_ref": "networkcontainer/abc:.../v1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure network container add 1.2.3.0/24 comment "my container" view v1', ctx
        )

    posts = _api_posts(requests_seen, "/networkcontainer")
    body = json.loads(posts[0].content)
    assert body["network"] == "1.2.3.0/24"
    assert body["comment"] == "my container"
    assert body["network_view"] == "v1"


async def test_add_network_container_with_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/networkcontainer" in request.url.path:
            return httpx.Response(201, json={"_ref": "networkcontainer/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network container add 1.2.3.0/24 set owner=alice", ctx)

    posts = _api_posts(requests_seen, "/networkcontainer")
    body = json.loads(posts[0].content)
    assert body["extattrs"] == {"owner": {"value": "alice"}}


async def test_delete_network_container():
    ref = "networkcontainer/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networkcontainer" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network container 1.2.3.0/24 delete", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_modify_network_container_comment():
    ref = "networkcontainer/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networkcontainer" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network container 1.2.3.0/24 modify comment "updated"', ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {"comment": "updated"}


async def test_show_network_container_all(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET":
            if "ipv6networkcontainer" in request.url.path:
                return httpx.Response(200, json=_list([]))
            if "networkcontainer" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "networkcontainer/abc:10.0.0.0/8/default",
                                "network": "10.0.0.0/8",
                                "comment": "root",
                            },
                            {
                                "_ref": "networkcontainer/abc:172.16.0.0/12/default",
                                "network": "172.16.0.0/12",
                            },
                        ]
                    ),
                )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network container", ctx)

    out = capsys.readouterr().out
    assert "10.0.0.0/8" in out
    assert "172.16.0.0/12" in out
    assert "root" in out


async def test_show_network_container_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networkcontainer" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "networkcontainer/abc:10.0.0.0/8/default",
                            "network": "10.0.0.0/8",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network container 10.0.0.0/8", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/networkcontainer" in r.url.path]
    assert any("network=10.0.0.0" in str(r.url) for r in gets)
    assert "10.0.0.0/8" in capsys.readouterr().out


async def test_show_network_container_with_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networkcontainer" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "networkcontainer/abc:10.0.0.0/8/v2",
                            "network": "10.0.0.0/8",
                            "network_view": "v2",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network container 10.0.0.0/8 view v2", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/networkcontainer" in r.url.path]
    assert any("network_view=v2" in str(r.url) for r in gets)


# ---------------------------------------------------------------------------
# Sub-slice 2c: shared networks
# ---------------------------------------------------------------------------


async def test_add_empty_shared_network():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/sharednetwork" in request.url.path:
            return httpx.Response(201, json={"_ref": "sharednetwork/ZG5z:corp-shared/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add shared corp-shared", ctx)

    posts = _api_posts(requests_seen, "/sharednetwork")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body == {"name": "corp-shared"}


async def test_add_shared_network_with_member_networks():
    ref1 = "network/abc:10.0.1.0/24/default"
    ref2 = "network/abc:10.0.2.0/24/default"
    get_calls = 0
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        nonlocal get_calls
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            get_calls += 1
            if get_calls == 1:
                return httpx.Response(200, json=_list([{"_ref": ref1, "network": "10.0.1.0/24"}]))
            return httpx.Response(200, json=_list([{"_ref": ref2, "network": "10.0.2.0/24"}]))
        if request.method == "POST" and "/sharednetwork" in request.url.path:
            return httpx.Response(201, json={"_ref": "sharednetwork/ZG5z:corp-shared/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure network add shared corp-shared network 10.0.1.0/24 network 10.0.2.0/24",
            ctx,
        )

    posts = _api_posts(requests_seen, "/sharednetwork")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "corp-shared"
    assert {"_ref": ref1} in body["networks"]
    assert {"_ref": ref2} in body["networks"]
    assert len(body["networks"]) == 2


async def test_add_shared_network_with_comment_and_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/sharednetwork" in request.url.path:
            return httpx.Response(201, json={"_ref": "sharednetwork/ZG5z:corp-shared/v1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure network add shared corp-shared comment "lab scope" view v1',
            ctx,
        )

    posts = _api_posts(requests_seen, "/sharednetwork")
    body = json.loads(posts[0].content)
    assert body["name"] == "corp-shared"
    assert body["comment"] == "lab scope"
    assert body["network_view"] == "v1"


async def test_add_shared_network_member_not_found(capsys):
    ref1 = "network/abc:10.0.1.0/24/default"
    get_calls = 0

    def handler(request: httpx.Request) -> httpx.Response | None:
        nonlocal get_calls
        if request.method == "GET" and "/network" in request.url.path:
            get_calls += 1
            if get_calls == 1:
                return httpx.Response(200, json=_list([{"_ref": ref1, "network": "10.0.1.0/24"}]))
            return httpx.Response(200, json=_list([]))
        return None

    requests_seen: list[httpx.Request] = []

    def tracking_handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        return handler(request)

    async with connected_ctx(tracking_handler) as ctx:
        await process_line(
            "configure network add shared corp-shared network 10.0.1.0/24 network 10.0.9.0/24",
            ctx,
        )

    out = capsys.readouterr().out
    assert "No network found" in out
    posts = _api_posts(requests_seen, "/sharednetwork")
    assert len(posts) == 0


async def test_delete_shared_network():
    ref = "sharednetwork/abc:corp-shared/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/sharednetwork" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "name": "corp-shared"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_network corp-shared delete", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_delete_shared_network_with_view():
    ref = "sharednetwork/abc:corp-shared/v1"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/sharednetwork" in request.url.path:
            return httpx.Response(
                200,
                json=_list([{"_ref": ref, "name": "corp-shared", "network_view": "v1"}]),
            )
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_network corp-shared delete view v1", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/sharednetwork" in r.url.path]
    assert any("network_view=v1" in str(r.url) for r in gets)


async def test_delete_shared_network_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/sharednetwork" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure shared_network no-such-sn delete", ctx)

    assert "No shared network found" in capsys.readouterr().out


async def test_show_shared_network_all(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/sharednetwork" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "sharednetwork/a:corp-shared/default",
                            "name": "corp-shared",
                            "comment": "corp DHCP",
                        },
                        {"_ref": "sharednetwork/b:lab-shared/default", "name": "lab-shared"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network shared", ctx)

    out = capsys.readouterr().out
    assert "corp-shared" in out
    assert "lab-shared" in out
    assert "corp DHCP" in out


async def test_show_shared_network_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/sharednetwork" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "sharednetwork/a:corp-shared/default",
                            "name": "corp-shared",
                            "comment": "corp DHCP",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network shared corp-shared", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/sharednetwork" in r.url.path]
    assert any("name=corp-shared" in str(r.url) for r in gets)
    assert "corp-shared" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Sub-slice 2e: split, join/move
# ---------------------------------------------------------------------------


async def test_split_network():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "POST" and ref in request.url.path:
            return httpx.Response(
                200,
                json=[
                    "network/abc:1.2.3.0/25/default",
                    "network/abc:1.2.3.128/25/default",
                ],
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 split 25", ctx)

    posts = _api_posts(requests_seen)
    assert any("split_network" in str(r.url) for r in posts)
    split_posts = [r for r in posts if "split_network" in str(r.url)]
    assert json.loads(split_posts[0].content) == {"cidr": 25}


async def test_split_network_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 split 25", ctx)

    assert "No network found" in capsys.readouterr().out


async def test_join_network_non_adjacent_rejected(capsys):
    """Non-adjacent CIDRs are rejected before any WAPI calls."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/25 join 1.2.4.128/25", ctx)

    out = capsys.readouterr().out
    assert "Error" in out
    assert "not adjacent siblings" in out
    # No WAPI calls beyond login probe
    api_calls = [r for r in requests_seen if "_schema" not in str(r.url)]
    assert len(api_calls) == 0


async def test_join_network_happy_path(capsys):
    """Two adjacent /25s join into a /24."""
    ref_a = "network/a:1.2.3.0/25/default"
    ref_b = "network/b:1.2.3.128/25/default"
    parent_ref = "network/p:1.2.3.0/24/default"
    get_calls = 0
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        nonlocal get_calls
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            get_calls += 1
            if get_calls == 1:
                return httpx.Response(200, json=_list([{"_ref": ref_a, "network": "1.2.3.0/25"}]))
            return httpx.Response(200, json=_list([{"_ref": ref_b, "network": "1.2.3.128/25"}]))
        if request.method == "DELETE" and ref_a in request.url.path:
            return httpx.Response(200, json=ref_a)
        if request.method == "DELETE" and ref_b in request.url.path:
            return httpx.Response(200, json=ref_b)
        if request.method == "POST" and "/network" in request.url.path:
            return httpx.Response(201, json={"_ref": parent_ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/25 join 1.2.3.128/25", ctx)

    out = capsys.readouterr().out
    assert "Error" not in out

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 2
    delete_paths = {r.url.path for r in deletes}
    assert any(ref_a in p for p in delete_paths)
    assert any(ref_b in p for p in delete_paths)

    posts = _api_posts(requests_seen, "/network")
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {"network": "1.2.3.0/24"}


async def test_join_network_missing_first_network(capsys):
    """First network missing → no WAPI delete calls."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/25 join 1.2.3.128/25", ctx)

    out = capsys.readouterr().out
    assert "Error" in out
    assert "not found" in out
    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 0


async def test_join_network_missing_second_network(capsys):
    """Second network missing → no WAPI delete calls."""
    ref_a = "network/a:1.2.3.0/25/default"
    get_calls = 0
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        nonlocal get_calls
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            get_calls += 1
            if get_calls == 1:
                return httpx.Response(200, json=_list([{"_ref": ref_a, "network": "1.2.3.0/25"}]))
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/25 join 1.2.3.128/25", ctx)

    out = capsys.readouterr().out
    assert "Error" in out
    assert "not found" in out
    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 0


def test_join_network_parent_computation():
    """Verify parent CIDR computation for various prefix lengths."""
    from ibcli.commands.network import _are_adjacent_siblings

    ok, parent = _are_adjacent_siblings("10.0.0.0/17", "10.0.128.0/17")
    assert ok
    assert parent == "10.0.0.0/16"

    ok, parent = _are_adjacent_siblings("192.168.0.0/24", "192.168.1.0/24")
    assert ok
    assert parent == "192.168.0.0/23"

    ok, parent = _are_adjacent_siblings("172.0.0.0/12", "172.16.0.0/12")
    assert ok
    assert parent == "172.0.0.0/11"


async def test_join_network_different_prefix_lengths_rejected(capsys):
    """CIDRs with different prefix lengths are rejected."""
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 join 1.2.3.128/25", ctx)

    out = capsys.readouterr().out
    assert "Error" in out
    api_calls = [r for r in requests_seen if "_schema" not in str(r.url)]
    assert len(api_calls) == 0


async def test_move_network_to_member():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 move member 10.0.0.5", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {
        "members": [{"_struct": "dhcpmember", "ipv4addr": "10.0.0.5"}]
    }


async def test_move_network_to_multiple_members():
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 move member 10.0.0.5 member 10.0.0.6", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {
        "members": [
            {"_struct": "dhcpmember", "ipv4addr": "10.0.0.5"},
            {"_struct": "dhcpmember", "ipv4addr": "10.0.0.6"},
        ]
    }


async def test_move_network_to_failover():
    # Full move: resolve failover peers, union into network.members, then PUT
    # failover_association on every range. Peer "b" is already a member.
    net_ref = "network/n:1.2.3.0/24/default"
    range_refs = [
        "range/a:1.2.3.10/1.2.3.20/default",
        "range/b:1.2.3.100/1.2.3.200/default",
    ]
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        if request.method == "GET" and "/dhcpfailover" in path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "dhcpfailover/x:fo1",
                            "name": "fo1",
                            "primary": "a.example.com",
                            "secondary": "b.example.com",
                        }
                    ]
                ),
            )
        if request.method == "GET" and "/network" in path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": net_ref,
                            "network": "1.2.3.0/24",
                            "members": [{"_struct": "dhcpmember", "name": "b.example.com"}],
                        }
                    ]
                ),
            )
        if request.method == "GET" and "/range" in path:
            return httpx.Response(
                200, json=_list([{"_ref": r, "network": "1.2.3.0/24"} for r in range_refs])
            )
        if request.method == "PUT":
            return httpx.Response(200, json={"_ref": "ok"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 move failover fo1", ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    # 1 PUT to the network (members merge) + 2 PUTs to ranges.
    assert len(puts) == 3
    net_put = next(p for p in puts if "/network" in p.url.path)
    members = json.loads(net_put.content)["members"]
    names = [m.get("name") for m in members]
    assert "b.example.com" in names  # pre-existing peer preserved
    assert "a.example.com" in names  # missing peer added
    range_puts = [p for p in puts if "/range" in p.url.path]
    assert len(range_puts) == 2
    assert all(json.loads(p.content) == {"failover_association": "fo1"} for p in range_puts)


async def test_move_network_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 1.2.3.0/24 move member 10.0.0.5", ctx)

    assert "No network found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Sub-slice 2e: IPAM next_available
# ---------------------------------------------------------------------------


async def test_next_available_ip(capsys):
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "POST" and ref in request.url.path:
            return httpx.Response(200, json={"ips": ["1.2.3.5"]})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24 ipam next_available", ctx)

    posts = _api_posts(requests_seen)
    func_posts = [r for r in posts if "next_available_ip" in str(r.url)]
    assert len(func_posts) == 1
    assert json.loads(func_posts[0].content) == {"num": 1}
    assert "1.2.3.5" in capsys.readouterr().out


async def test_next_available_ip_with_num(capsys):
    ref = "network/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "POST" and ref in request.url.path:
            return httpx.Response(
                200,
                json={
                    "ips": [
                        "1.2.3.5",
                        "1.2.3.6",
                        "1.2.3.7",
                        "1.2.3.8",
                        "1.2.3.9",
                    ]
                },
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24 ipam next_available 5", ctx)

    posts = _api_posts(requests_seen)
    func_posts = [r for r in posts if "next_available_ip" in str(r.url)]
    assert json.loads(func_posts[0].content) == {"num": 5}
    out = capsys.readouterr().out
    assert "1.2.3.5" in out
    assert "1.2.3.9" in out


async def test_next_available_network(capsys):
    ref = "networkcontainer/abc:1.2.3.0/24/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networkcontainer" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "1.2.3.0/24"}]))
        if request.method == "POST" and ref in request.url.path:
            return httpx.Response(200, json={"networks": ["1.2.3.0/26"]})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24 ipam next_network /26", ctx)

    posts = _api_posts(requests_seen)
    func_posts = [r for r in posts if "next_available_network" in str(r.url)]
    assert len(func_posts) == 1
    assert json.loads(func_posts[0].content) == {"cidr": 26, "num": 1}
    assert "1.2.3.0/26" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# IPv6 network tests
# ---------------------------------------------------------------------------


async def test_add_ipv6_network():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/ipv6network" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6network/ZG5z:2001:db8::/64/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add 2001:db8::/64", ctx)

    posts = _api_posts(requests_seen, "/ipv6network")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body == {"network": "2001:db8::/64"}


async def test_add_ipv6_network_with_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/ipv6network" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6network/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network add 2001:db8::/64 comment "v6 lab"', ctx)

    posts = _api_posts(requests_seen, "/ipv6network")
    body = json.loads(posts[0].content)
    assert body["network"] == "2001:db8::/64"
    assert body["comment"] == "v6 lab"


async def test_add_ipv6_network_with_view():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/ipv6network" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6network/abc:.../v1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network add 2001:db8::/64 view v1", ctx)

    posts = _api_posts(requests_seen, "/ipv6network")
    body = json.loads(posts[0].content)
    assert body["network_view"] == "v1"


async def test_delete_ipv6_network():
    ref = "ipv6network/abc:2001:db8::/64/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "2001:db8::/64"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 2001:db8::/64 delete", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/ipv6network" in r.url.path]
    assert len(gets) >= 1
    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_delete_ipv6_network_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/ipv6network" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network 2001:db8::/64 delete", ctx)

    assert "No network found" in capsys.readouterr().out


async def test_modify_ipv6_network():
    ref = "ipv6network/abc:2001:db8::/64/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6network" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "2001:db8::/64"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network 2001:db8::/64 modify comment "updated v6"', ctx)

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {"comment": "updated v6"}


async def test_show_ipv6_network_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6network" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "ipv6network/abc:2001:db8::/64/default",
                            "network": "2001:db8::/64",
                            "comment": "v6 lab",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 2001:db8::/64", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/ipv6network" in r.url.path]
    assert len(gets) >= 1
    out = capsys.readouterr().out
    assert "2001:db8::/64" in out
    assert "v6 lab" in out


async def test_show_network_all_lists_both_families(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            if "ipv6network" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6network/abc:2001:db8::/32/default",
                                "network": "2001:db8::/32",
                                "comment": "v6 net",
                            },
                        ]
                    ),
                )
            if "/network" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "network/abc:10.0.0.0/8/default",
                                "network": "10.0.0.0/8",
                                "comment": "v4 net",
                            },
                        ]
                    ),
                )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network", ctx)

    out = capsys.readouterr().out
    assert "10.0.0.0/8" in out
    assert "2001:db8::/32" in out
    assert "v4 net" in out
    assert "v6 net" in out

    get_paths = [r.url.path for r in requests_seen if r.method == "GET"]
    assert any("ipv6network" in p for p in get_paths)
    assert any("/network" in p and "ipv6" not in p for p in get_paths)


# ---------------------------------------------------------------------------
# IPv6 network container tests
# ---------------------------------------------------------------------------


async def test_add_ipv6_network_container():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/ipv6networkcontainer" in request.url.path:
            return httpx.Response(
                201, json={"_ref": "ipv6networkcontainer/ZG5z:2001:db8::/32/default"}
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network container add 2001:db8::/32", ctx)

    posts = _api_posts(requests_seen, "/ipv6networkcontainer")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body == {"network": "2001:db8::/32"}


async def test_add_ipv6_network_container_with_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/ipv6networkcontainer" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6networkcontainer/abc:.../default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network container add 2001:db8::/32 comment "v6 root"', ctx)

    posts = _api_posts(requests_seen, "/ipv6networkcontainer")
    body = json.loads(posts[0].content)
    assert body["network"] == "2001:db8::/32"
    assert body["comment"] == "v6 root"


async def test_delete_ipv6_network_container():
    ref = "ipv6networkcontainer/abc:2001:db8::/32/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6networkcontainer" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "2001:db8::/32"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network container 2001:db8::/32 delete", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/ipv6networkcontainer" in r.url.path]
    assert len(gets) >= 1
    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_modify_ipv6_network_container():
    ref = "ipv6networkcontainer/abc:2001:db8::/32/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6networkcontainer" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "network": "2001:db8::/32"}]))
        if request.method == "PUT" and ref in request.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure network container 2001:db8::/32 modify comment "v6 updated"', ctx
        )

    puts = [r for r in requests_seen if r.method == "PUT"]
    assert len(puts) == 1
    assert json.loads(puts[0].content) == {"comment": "v6 updated"}


async def test_show_ipv6_network_container_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/ipv6networkcontainer" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "ipv6networkcontainer/abc:2001:db8::/32/default",
                            "network": "2001:db8::/32",
                            "comment": "v6 root",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network container 2001:db8::/32", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/ipv6networkcontainer" in r.url.path]
    assert len(gets) >= 1
    assert "2001:db8::/32" in capsys.readouterr().out


async def test_show_network_container_all_lists_both_families(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET":
            if "ipv6networkcontainer" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "ipv6networkcontainer/abc:2001:db8::/32/default",
                                "network": "2001:db8::/32",
                                "comment": "v6 root",
                            },
                        ]
                    ),
                )
            if "networkcontainer" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "networkcontainer/abc:10.0.0.0/8/default",
                                "network": "10.0.0.0/8",
                            },
                        ]
                    ),
                )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network container", ctx)

    out = capsys.readouterr().out
    assert "10.0.0.0/8" in out
    assert "2001:db8::/32" in out
    assert "v6 root" in out


# ---------------------------------------------------------------------------
# Sub-slice 2e: show network statistics
# ---------------------------------------------------------------------------


async def test_show_network_statistics(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if (
            request.method == "GET"
            and "ipam" in request.url.path
            and "statistics" in request.url.path
        ):
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "ipam:statistics/...",
                            "network": "1.2.3.0/24",
                            "utilization": 42,
                            "total_ip_count": 254,
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network 1.2.3.0/24 statistics", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "ipam" in str(r.url).lower()]
    assert len(gets) >= 1
    out = capsys.readouterr().out
    assert "utilization" in out
    assert "42" in out
