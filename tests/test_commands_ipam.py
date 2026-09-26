# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.ipam - Phase 8 IPAM command handlers."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import ipam  # noqa: F401  - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None, **client_kwargs):
    """A Context around a mocked NiosClient.

    Pass ``enforce_restrictions=False`` for a command whose WAPI object type
    forbids the operation on NIOS 9.1 - the SDK refuses those before they
    reach the transport, and the test still needs to assert the request the
    CLI would build.
    """
    async with make_client(handler, **client_kwargs) as client:
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


def _api_deletes(requests_seen: list, path_fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_gets(requests_seen: list, path_fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "GET"
        and "/_schema" not in r.url.path
        and "/grid/session" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ===========================================================================
# Chunk A - Individual address (read-only)
# ===========================================================================


async def test_show_ipv4address(capsys):
    results = [
        {
            "ip_address": "10.0.0.1",
            "network": "10.0.0.0/24",
            "network_view": "default",
            "status": "USED",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "names": ["host1.example.com"],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "ipv4address" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show address 10.0.0.1", ctx)

    out = capsys.readouterr().out
    assert "10.0.0.1" in out
    assert "USED" in out


async def test_show_ipv4address_not_connected(capsys):
    ctx = Context()
    await process_line("show address 10.0.0.1", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_show_ipv4address_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "ipv4address" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show address 10.0.0.1", ctx)

    assert "No IPv4 address found" in capsys.readouterr().out


async def test_show_ipv6address(capsys):
    results = [
        {
            "ip_address": "2001:db8::1",
            "network": "2001:db8::/32",
            "network_view": "default",
            "status": "USED",
            "duid": "00:01:00:01:ab:cd:ef:00",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "ipv6address" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show address ipv6 2001:db8::1", ctx)

    out = capsys.readouterr().out
    assert "2001:db8::1" in out


async def test_show_ipv6address_not_connected(capsys):
    ctx = Context()
    await process_line("show address ipv6 2001:db8::1", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B - Network views
# ===========================================================================


async def test_add_networkview():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "networkview" in request.url.path:
            return httpx.Response(201, json={"_ref": "networkview/ZG5z:default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network_view add myview", ctx)

    posts = _api_posts(requests_seen, "networkview")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "myview"


async def test_add_networkview_with_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "networkview" in request.url.path:
            return httpx.Response(201, json={"_ref": "networkview/ZG5z:myview"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure network_view add myview comment "test view"', ctx)

    posts = _api_posts(requests_seen, "networkview")
    body = json.loads(posts[0].content)
    assert body["name"] == "myview"
    assert body["comment"] == "test view"


async def test_delete_networkview():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "networkview" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": "networkview/ZG5z:myview", "name": "myview"}]}
            )
        if request.method == "DELETE" and "networkview" in request.url.path:
            return httpx.Response(200, json="networkview/ZG5z:myview")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network_view myview delete", ctx)

    deletes = _api_deletes(requests_seen, "networkview")
    assert len(deletes) == 1


async def test_delete_networkview_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "networkview" in request.url.path:
            return httpx.Response(200, json={"result": []})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure network_view missing delete", ctx)

    assert "No network view found" in capsys.readouterr().out


async def test_show_networkview(capsys):
    results = [{"_ref": "networkview/1", "name": "default", "comment": "", "is_default": True}]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "networkview" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network_view", ctx)

    assert "default" in capsys.readouterr().out


async def test_show_networkview_specific(capsys):
    results = [
        {"_ref": "networkview/1", "name": "myview", "comment": "my view", "is_default": False}
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "networkview" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network_view myview", ctx)

    out = capsys.readouterr().out
    assert "myview" in out


async def test_add_networkview_not_connected(capsys):
    ctx = Context()
    await process_line("configure network_view add myview", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B - VLAN view
# ===========================================================================


async def test_add_vlanview():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "vlanview" in request.url.path:
            return httpx.Response(201, json={"_ref": "vlanview/ZG5z:default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure vlan_view add myvlanview start_vlan_id=1 end_vlan_id=4094", ctx
        )

    posts = _api_posts(requests_seen, "vlanview")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "myvlanview"
    assert body["start_vlan_id"] == 1
    assert body["end_vlan_id"] == 4094


async def test_delete_vlanview():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "vlanview" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": "vlanview/ZG5z:myvlanview", "name": "myvlanview"}]}
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="vlanview/ZG5z:myvlanview")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure vlan_view myvlanview delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_vlanview(capsys):
    results = [
        {
            "_ref": "vlanview/1",
            "name": "default",
            "start_vlan_id": 1,
            "end_vlan_id": 4094,
            "comment": "",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "vlanview" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show vlan_view", ctx)

    out = capsys.readouterr().out
    assert "default" in out
    assert "4094" in out


async def test_add_vlanview_not_connected(capsys):
    ctx = Context()
    await process_line("configure vlan_view add myvv", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B - VLAN range
# ===========================================================================


async def test_add_vlanrange():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "vlanrange" in request.url.path:
            return httpx.Response(201, json={"_ref": "vlanrange/ZG5z:myrange"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure vlan_range add myrange start_vlan_id=100 end_vlan_id=200 vlan_view=default",
            ctx,
        )

    posts = _api_posts(requests_seen, "vlanrange")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "myrange"
    assert body["start_vlan_id"] == 100
    assert body["end_vlan_id"] == 200
    assert body["vlan_view"] == "default"


async def test_delete_vlanrange():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "vlanrange" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": "vlanrange/ZG5z:myrange", "name": "myrange"}]}
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="vlanrange/ZG5z:myrange")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure vlan_range myrange delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_vlanrange(capsys):
    results = [
        {
            "_ref": "vlanrange/1",
            "name": "myrange",
            "vlan_view": "default",
            "start_vlan_id": 100,
            "end_vlan_id": 200,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "vlanrange" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show vlan_range", ctx)

    out = capsys.readouterr().out
    assert "myrange" in out
    assert "100" in out


async def test_add_vlanrange_not_connected(capsys):
    ctx = Context()
    await process_line("configure vlan_range add myrange", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B - VLAN
# ===========================================================================


async def test_add_vlan():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/vlan" in request.url.path:
            return httpx.Response(201, json={"_ref": "vlan/ZG5z:100"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure vlan add 100 name=myvlan parent=vlanrange/abc", ctx)

    posts = _api_posts(requests_seen, "/vlan")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["id"] == 100
    assert body["name"] == "myvlan"
    assert body["parent"] == "vlanrange/abc"


async def test_delete_vlan():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/vlan" in request.url.path:
            return httpx.Response(200, json={"result": [{"_ref": "vlan/ZG5z:100", "id": 100}]})
        if request.method == "DELETE":
            return httpx.Response(200, json="vlan/ZG5z:100")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure vlan 100 delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_vlan(capsys):
    results = [{"_ref": "vlan/1", "id": 100, "name": "myvlan", "parent": "vlanrange/abc"}]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/vlan" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show vlan", ctx)

    out = capsys.readouterr().out
    assert "100" in out
    assert "myvlan" in out


async def test_show_vlan_specific(capsys):
    results = [{"_ref": "vlan/1", "id": 100, "name": "myvlan", "parent": "vlanrange/abc"}]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/vlan" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show vlan 100", ctx)

    assert "100" in capsys.readouterr().out


async def test_add_vlan_not_connected(capsys):
    ctx = Context()
    await process_line("configure vlan add 100 name=x", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk C - Superhost
# ===========================================================================


async def test_add_superhost():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "superhost" in request.url.path:
            return httpx.Response(201, json={"_ref": "superhost/ZG5z:mysh"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure superhost add mysh", ctx)

    posts = _api_posts(requests_seen, "superhost")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "mysh"


async def test_add_superhost_with_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "superhost" in request.url.path:
            return httpx.Response(201, json={"_ref": "superhost/ZG5z:mysh"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line('configure superhost add mysh comment "my superhost"', ctx)

    posts = _api_posts(requests_seen, "superhost")
    body = json.loads(posts[0].content)
    assert body["comment"] == "my superhost"


async def test_delete_superhost():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "superhost" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": "superhost/ZG5z:mysh", "name": "mysh"}]}
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="superhost/ZG5z:mysh")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure superhost mysh delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_superhost(capsys):
    results = [
        {
            "_ref": "superhost/1",
            "name": "mysh",
            "comment": "test",
            "dhcp_associated_objects": ["fixedaddress/1"],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "superhost" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show superhost", ctx)

    out = capsys.readouterr().out
    assert "mysh" in out
    assert "dhcp_objects=1" in out


async def test_show_superhostchild(capsys):
    results = [
        {
            "_ref": "superhostchild/1",
            "name": "host1",
            "type": "HostRecord",
            "parent": "mysh",
            "record_parent": "example.com",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "superhostchild" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show superhostchild mysh", ctx)

    out = capsys.readouterr().out
    assert "host1" in out
    assert "HostRecord" in out


async def test_add_superhost_not_connected(capsys):
    ctx = Context()
    await process_line("configure superhost add mysh", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk C - Bulkhost
# ===========================================================================


async def test_add_bulkhost():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "bulkhost" in request.url.path:
            return httpx.Response(201, json={"_ref": "bulkhost/ZG5z:host"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure bulkhost add host zone=example.com start_addr=10.0.0.1 end_addr=10.0.0.10",
            ctx,
        )

    posts = _api_posts(requests_seen, "bulkhost")
    # Filter out bulkhostnametemplate matches
    bh_posts = [p for p in posts if "nametemplate" not in p.url.path]
    assert len(bh_posts) == 1
    body = json.loads(bh_posts[0].content)
    assert body["prefix"] == "host"
    assert body["zone"] == "example.com"
    assert body["start_addr"] == "10.0.0.1"
    assert body["end_addr"] == "10.0.0.10"


async def test_delete_bulkhost():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if (
            request.method == "GET"
            and "/bulkhost" in request.url.path
            and "nametemplate" not in request.url.path
        ):
            return httpx.Response(
                200, json={"result": [{"_ref": "bulkhost/ZG5z:host", "prefix": "host"}]}
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="bulkhost/ZG5z:host")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure bulkhost host delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_bulkhost(capsys):
    results = [
        {
            "_ref": "bulkhost/1",
            "prefix": "host",
            "zone": "example.com",
            "start_addr": "10.0.0.1",
            "end_addr": "10.0.0.10",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if (
            request.method == "GET"
            and "/bulkhost" in request.url.path
            and "nametemplate" not in request.url.path
        ):
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show bulkhost", ctx)

    out = capsys.readouterr().out
    assert "host" in out
    assert "example.com" in out


async def test_add_bulkhost_not_connected(capsys):
    ctx = Context()
    await process_line("configure bulkhost add host zone=example.com", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk C - Bulkhost name template
# ===========================================================================


async def test_add_bulkhost_template():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "bulkhostnametemplate" in request.url.path:
            return httpx.Response(201, json={"_ref": "bulkhostnametemplate/ZG5z:mytmpl"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure bulkhost_template add mytmpl template_format=host{n}.example.com", ctx
        )

    posts = _api_posts(requests_seen, "bulkhostnametemplate")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["template_name"] == "mytmpl"
    assert body["template_format"] == "host{n}.example.com"


async def test_delete_bulkhost_template():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "bulkhostnametemplate" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {"_ref": "bulkhostnametemplate/ZG5z:mytmpl", "template_name": "mytmpl"}
                    ]
                },
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="bulkhostnametemplate/ZG5z:mytmpl")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure bulkhost_template mytmpl delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_bulkhost_template(capsys):
    results = [
        {
            "_ref": "bulkhostnametemplate/1",
            "template_name": "mytmpl",
            "template_format": "host{n}.example.com",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "bulkhostnametemplate" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show bulkhost_template", ctx)

    out = capsys.readouterr().out
    assert "mytmpl" in out
    assert "host{n}.example.com" in out


async def test_add_bulkhost_template_not_connected(capsys):
    ctx = Context()
    await process_line("configure bulkhost_template add mytmpl template_format=x", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - Network discovery (read-only)
# ===========================================================================


async def test_show_network_discovery(capsys):
    results = [{"_ref": "network_discovery/1", "network": "10.0.0.0/24"}]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "network_discovery" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show network_discovery", ctx)

    out = capsys.readouterr().out
    assert "network_discovery" in out


async def test_show_network_discovery_not_connected(capsys):
    ctx = Context()
    await process_line("show network_discovery", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - RIR (read-only)
# ===========================================================================


async def test_show_rir(capsys):
    results = [
        {
            "_ref": "rir/1",
            "name": "RIPE",
            "communication_mode": "EMAIL",
            "email": "ripe@example.com",
            "url": "https://ripe.net",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if (
            request.method == "GET"
            and "/rir" in request.url.path
            and "organization" not in request.url.path
        ):
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show rir", ctx)

    out = capsys.readouterr().out
    assert "RIPE" in out
    assert "EMAIL" in out


async def test_show_rir_not_connected(capsys):
    ctx = Context()
    await process_line("show rir", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - RIR organization
# ===========================================================================


async def test_add_rir_organization():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "rir:organization" in request.url.path:
            return httpx.Response(201, json={"_ref": "rir:organization/ZG5z:myorg"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure rir_organization add myorg id=ORG-123 rir=rir/1", ctx)

    posts = _api_posts(requests_seen, "rir:organization")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "myorg"
    assert body["id"] == "ORG-123"
    assert body["rir"] == "rir/1"


async def test_delete_rir_organization():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "rir:organization" in request.url.path:
            return httpx.Response(
                200, json={"result": [{"_ref": "rir:organization/ZG5z:myorg", "name": "myorg"}]}
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="rir:organization/ZG5z:myorg")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure rir_organization myorg delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_rir_organization(capsys):
    results = [
        {
            "_ref": "rir:organization/1",
            "name": "myorg",
            "id": "ORG-123",
            "rir": "rir/1",
            "maintainer": "admin",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "rir:organization" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show rir_organization", ctx)

    out = capsys.readouterr().out
    assert "myorg" in out
    assert "ORG-123" in out


async def test_add_rir_organization_not_connected(capsys):
    ctx = Context()
    await process_line("configure rir_organization add myorg id=X rir=RIPE", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - Hostname rewrite policy
# ===========================================================================


async def test_add_hostname_policy():
    # NIOS 9.1 forbids create/delete on `hostnamerewritepolicy` and the
    # SDK refuses before building the request. This asserts the request
    # the CLI *would* send, so enforcement is off.
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "hostnamerewritepolicy" in request.url.path:
            return httpx.Response(201, json={"_ref": "hostnamerewritepolicy/ZG5z:mypolicy"})
        return None

    async with connected_ctx(handler, enforce_restrictions=False) as ctx:
        await process_line(
            "configure hostname_policy add mypolicy valid_characters=abcdefghijklmnopqrstuvwxyz",
            ctx,
        )

    posts = _api_posts(requests_seen, "hostnamerewritepolicy")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "mypolicy"
    assert body["valid_characters"] == "abcdefghijklmnopqrstuvwxyz"


async def test_delete_hostname_policy():
    # NIOS 9.1 forbids create/delete on `hostnamerewritepolicy` and the
    # SDK refuses before building the request. This asserts the request
    # the CLI *would* send, so enforcement is off.
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "hostnamerewritepolicy" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [{"_ref": "hostnamerewritepolicy/ZG5z:mypolicy", "name": "mypolicy"}]
                },
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="hostnamerewritepolicy/ZG5z:mypolicy")
        return None

    async with connected_ctx(handler, enforce_restrictions=False) as ctx:
        await process_line("configure hostname_policy mypolicy delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_hostname_policy(capsys):
    results = [
        {
            "_ref": "hostnamerewritepolicy/1",
            "name": "mypolicy",
            "valid_characters": "abc",
            "replacement_character": "-",
            "is_default": False,
            "pre_defined": False,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "hostnamerewritepolicy" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show hostname_policy", ctx)

    out = capsys.readouterr().out
    assert "mypolicy" in out
    assert "valid_characters=abc" in out


async def test_show_hostname_policy_specific(capsys):
    results = [
        {
            "_ref": "hostnamerewritepolicy/1",
            "name": "mypolicy",
            "valid_characters": "abc",
            "replacement_character": "-",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "hostnamerewritepolicy" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show hostname_policy mypolicy", ctx)

    assert "mypolicy" in capsys.readouterr().out


async def test_add_hostname_policy_not_connected(capsys):
    ctx = Context()
    await process_line("configure hostname_policy add mypolicy", ctx)
    assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - IPv6 network template
# ===========================================================================


async def test_add_ipv6networktemplate():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "ipv6networktemplate" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6networktemplate/ZG5z:mytmpl"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure template ipv6network add mytmpl cidr=64", ctx)

    posts = _api_posts(requests_seen, "ipv6networktemplate")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "mytmpl"
    assert body["cidr"] == 64


async def test_add_ipv6networktemplate_with_comment():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "ipv6networktemplate" in request.url.path:
            return httpx.Response(201, json={"_ref": "ipv6networktemplate/ZG5z:mytmpl"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            'configure template ipv6network add mytmpl cidr=64 comment "v6 template"', ctx
        )

    posts = _api_posts(requests_seen, "ipv6networktemplate")
    body = json.loads(posts[0].content)
    assert body["comment"] == "v6 template"


async def test_delete_ipv6networktemplate():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "ipv6networktemplate" in request.url.path:
            return httpx.Response(
                200,
                json={"result": [{"_ref": "ipv6networktemplate/ZG5z:mytmpl", "name": "mytmpl"}]},
            )
        if request.method == "DELETE":
            return httpx.Response(200, json="ipv6networktemplate/ZG5z:mytmpl")
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure template ipv6network mytmpl delete", ctx)

    assert len(_api_deletes(requests_seen)) == 1


async def test_show_ipv6networktemplate(capsys):
    results = [
        {"_ref": "ipv6networktemplate/1", "name": "mytmpl", "cidr": 64, "comment": "v6 template"}
    ]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "ipv6networktemplate" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show template ipv6network", ctx)

    out = capsys.readouterr().out
    assert "mytmpl" in out
    assert "64" in out


async def test_show_ipv6networktemplate_specific(capsys):
    results = [{"_ref": "ipv6networktemplate/1", "name": "mytmpl", "cidr": 64}]

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "ipv6networktemplate" in request.url.path:
            return httpx.Response(200, json={"result": results})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show template ipv6network mytmpl", ctx)

    assert "mytmpl" in capsys.readouterr().out


async def test_add_ipv6networktemplate_not_connected(capsys):
    ctx = Context()
    await process_line("configure template ipv6network add mytmpl cidr=64", ctx)
    assert "Not connected" in capsys.readouterr().out
