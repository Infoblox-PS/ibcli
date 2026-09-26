# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.discovery - Phase 16.

Covers:
  Chunk A: Device inventory - device (show all / show by name),
           interface, component, neighbor, support_bundle (all read-only)
  Chunk B: SDN network (show), VRF (show), credential_group (add/delete/set/show)
  Chunk C: Grid properties (show/set), member properties (show/set), status (show)
  Chunk D: Diagnostic task (start/show), vdiscovery task (add/delete/start/show)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- ctx.client.discovery.* is the SDK entry point.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import discovery  # noqa: F401  ensures module registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so configure/show are recognised."""
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
# Chunk A: Device inventory
# ===========================================================================


class TestDiscoveryDeviceShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:device" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:device", "sw1"),
                                "name": "sw1",
                                "address": "10.0.0.1",
                                "type": "SWITCH",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:device" in out
        assert "name=sw1" in out
        assert "address=10.0.0.1" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:device" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:device", "sw1"),
                                "name": "sw1",
                                "address": "10.0.0.1",
                                "type": "SWITCH",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1", ctx)

        out = capsys.readouterr().out
        assert "name=sw1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:device" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw99", ctx)

        out = capsys.readouterr().out
        assert "No device found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show discovery device", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestDiscoveryDeviceInterface:
    async def test_show_interfaces(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:deviceinterface" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:deviceinterface", "if0"),
                                "name": "GigE0/0",
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "type": "ETHERNET",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 interface", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:deviceinterface" in out
        assert "name=GigE0/0" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:deviceinterface" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 interface", ctx)

        out = capsys.readouterr().out
        assert "No interfaces found" in out


class TestDiscoveryDeviceComponent:
    async def test_show_components(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:devicecomponent" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:devicecomponent", "fan0"),
                                "component_name": "Fan0",
                                "type": "FAN",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 component", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:devicecomponent" in out
        assert "component_name=Fan0" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:devicecomponent" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 component", ctx)

        out = capsys.readouterr().out
        assert "No components found" in out


class TestDiscoveryDeviceNeighbor:
    async def test_show_neighbors(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:deviceneighbor" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:deviceneighbor", "n1"),
                                "name": "router1",
                                "address": "10.0.0.254",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 neighbor", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:deviceneighbor" in out
        assert "name=router1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:deviceneighbor" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device sw1 neighbor", ctx)

        out = capsys.readouterr().out
        assert "No neighbors found" in out


class TestDiscoveryDeviceSupportBundle:
    async def test_show_bundles(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:devicesupportbundle" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:devicesupportbundle", "b1"),
                                "name": "CiscoIOS",
                                "version": "1.2",
                                "author": "Infoblox",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device CiscoIOS support_bundle", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:devicesupportbundle" in out
        assert "name=CiscoIOS" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:devicesupportbundle" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery device UnknownBundle support_bundle", ctx)

        out = capsys.readouterr().out
        assert "No support bundles found" in out


# ===========================================================================
# Chunk B: SDN network + VRF + credential_group
# ===========================================================================


class TestDiscoverySdnNetworkShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:sdnnetwork" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:sdnnetwork", "sdn1"),
                                "name": "sdn1",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery sdn_network", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:sdnnetwork" in out
        assert "name=sdn1" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:sdnnetwork" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:sdnnetwork", "sdn1"),
                                "name": "sdn1",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery sdn_network sdn1", ctx)

        out = capsys.readouterr().out
        assert "name=sdn1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:sdnnetwork" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery sdn_network nosuchnet", ctx)

        out = capsys.readouterr().out
        assert "No SDN network found" in out


class TestDiscoveryVrfShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:vrf" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:vrf", "vrf1"),
                                "name": "vrf1",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery vrf", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:vrf" in out
        assert "name=vrf1" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:vrf" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:vrf", "vrf1"),
                                "name": "vrf1",
                                "network_view": "default",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery vrf vrf1", ctx)

        out = capsys.readouterr().out
        assert "name=vrf1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:vrf" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery vrf novrf", ctx)

        out = capsys.readouterr().out
        assert "No VRF found" in out


class TestDiscoveryCredentialGroupAdd:
    async def test_add_no_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("discovery:credentialgroup", "cg1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group add cg1", ctx)

        posts = _posts_to(seen, "discovery:credentialgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "cg1"
        assert "comment" not in body

    async def test_add_with_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("discovery:credentialgroup", "cg2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group add cg2 comment=prod", ctx)

        posts = _posts_to(seen, "discovery:credentialgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "prod"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure discovery credential_group add cg1", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestDiscoveryCredentialGroupDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("discovery:credentialgroup", "cg1"), "name": "cg1"},
                        ]
                    ),
                )
            if req.method == "DELETE" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(200, json=_ref("discovery:credentialgroup", "cg1"))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group cg1 delete", ctx)

        dels = _deletes_to(seen, "discovery:credentialgroup")
        assert len(dels) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group nosuchcg delete", ctx)

        out = capsys.readouterr().out
        assert "No credential group found" in out


class TestDiscoveryCredentialGroupSet:
    async def test_set_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("discovery:credentialgroup", "cg1"), "name": "cg1"},
                        ]
                    ),
                )
            if req.method == "PUT" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("discovery:credentialgroup", "cg1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group cg1 set comment=updated", ctx)

        puts = _puts_to(seen, "discovery:credentialgroup")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("comment") == "updated"

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group nosuch set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No credential group found" in out

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("discovery:credentialgroup", "cg1"), "name": "cg1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery credential_group cg1 set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out


class TestDiscoveryCredentialGroupShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:credentialgroup", "cg1"),
                                "name": "cg1",
                                "uuid": "abc",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery credential_group", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:credentialgroup" in out
        assert "name=cg1" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("discovery:credentialgroup", "cg1"), "name": "cg1"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery credential_group cg1", ctx)

        out = capsys.readouterr().out
        assert "name=cg1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:credentialgroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery credential_group nosuch", ctx)

        out = capsys.readouterr().out
        assert "No credential group found" in out


# ===========================================================================
# Chunk C: Grid properties + member properties + status
# ===========================================================================


class TestDiscoveryGridPropertiesShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:gridproperties" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:gridproperties", "gp1"),
                                "grid_name": "TestGrid",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery grid_properties", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:gridproperties" in out
        assert "grid_name=TestGrid" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:gridproperties" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery grid_properties", ctx)

        out = capsys.readouterr().out
        assert out == ""


class TestDiscoveryGridPropertiesSet:
    async def test_set_ok(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "discovery:gridproperties" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:gridproperties", "gp1"),
                                "grid_name": "TestGrid",
                            },
                        ]
                    ),
                )
            if req.method == "PUT" and "discovery:gridproperties" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("discovery:gridproperties", "gp1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure discovery grid_properties set disable_ip_scanning=true", ctx
            )

        puts = _puts_to(seen, "discovery:gridproperties")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("disable_ip_scanning") is True

    async def test_set_no_kvs(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery grid_properties set", ctx)

        out = capsys.readouterr().out
        assert "specify at least one" in out

    async def test_set_no_properties(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:gridproperties" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery grid_properties set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No grid properties found" in out


class TestDiscoveryMemberPropertiesShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:memberproperties", "mp1"),
                                "discovery_member": "gm01.test",
                                "address": "192.168.1.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery member_properties", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:memberproperties" in out
        assert "discovery_member=gm01.test" in out

    async def test_show_by_member(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:memberproperties", "mp1"),
                                "discovery_member": "gm01.test",
                                "address": "192.168.1.1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery member_properties gm01.test", ctx)

        out = capsys.readouterr().out
        assert "discovery_member=gm01.test" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery member_properties nosuchmember", ctx)

        out = capsys.readouterr().out
        assert "No member properties found" in out


class TestDiscoveryMemberPropertiesSet:
    async def test_set_ok(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:memberproperties", "mp1"),
                                "discovery_member": "gm01.test",
                            },
                        ]
                    ),
                )
            if req.method == "PUT" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(200, json={"_ref": _ref("discovery:memberproperties", "mp1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure discovery member_properties gm01.test set enable_snmp_v3=true", ctx
            )

        puts = _puts_to(seen, "discovery:memberproperties")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body.get("enable_snmp_v3") is True

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:memberproperties" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure discovery member_properties nosuch set comment=x", ctx)

        out = capsys.readouterr().out
        assert "No member properties found" in out


class TestDiscoveryStatusShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:status" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:status", "st1"),
                                "address": "10.0.0.1",
                                "status": "COMPLETE",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery status", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:status" in out
        assert "address=10.0.0.1" in out
        assert "status=COMPLETE" in out

    async def test_show_by_member(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:status" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:status", "st1"),
                                "address": "10.0.0.1",
                                "status": "COMPLETE",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery status 10.0.0.1", ctx)

        out = capsys.readouterr().out
        assert "status=COMPLETE" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:status" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery status 1.2.3.4", ctx)

        out = capsys.readouterr().out
        assert "No discovery status found" in out


# ===========================================================================
# Chunk D: Diagnostic task + vdiscovery task
# ===========================================================================


class TestDiscoveryDiagnosticStart:
    # NIOS 9.1 forbids create on `discovery:diagnostictask` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_start_no_member(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "discovery:diagnostictask" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("discovery:diagnostictask", "dt1")})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure discovery diagnostic start", ctx)

        posts = _posts_to(seen, "discovery:diagnostictask")
        assert len(posts) == 1

    async def test_start_with_member(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "discovery:diagnostictask" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("discovery:diagnostictask", "dt1")})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure discovery diagnostic start member=gm01.test", ctx)

        posts = _posts_to(seen, "discovery:diagnostictask")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body.get("network_view") == "gm01.test"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure discovery diagnostic start", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestDiscoveryDiagnosticShow:
    async def test_show(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:diagnostictask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("discovery:diagnostictask", "dt1"),
                                "ip_address": "10.0.0.5",
                                "task_id": "t001",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery diagnostic", ctx)

        out = capsys.readouterr().out
        assert "type=discovery:diagnostictask" in out
        assert "ip_address=10.0.0.5" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "discovery:diagnostictask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show discovery diagnostic", ctx)

        out = capsys.readouterr().out
        assert out == ""


class TestVdiscoveryTaskAdd:
    async def test_add_name_only(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "vdiscoverytask" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("vdiscoverytask", "t1")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure vdiscovery task add vmtask1", ctx)

        posts = _posts_to(seen, "vdiscoverytask")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "vmtask1"

    async def test_add_with_service_and_comment(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "vdiscoverytask" in req.url.path:
                return httpx.Response(201, json={"_ref": _ref("vdiscoverytask", "t2")})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure vdiscovery task add vmtask2 service=VMWARE comment=prod", ctx
            )

        posts = _posts_to(seen, "vdiscoverytask")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["driver_type"] == "VMWARE"
        assert body["comment"] == "prod"

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("configure vdiscovery task add t1", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out


class TestVdiscoveryTaskDelete:
    async def test_delete_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("vdiscoverytask", "t1"), "name": "vmtask1"},
                        ]
                    ),
                )
            if req.method == "DELETE" and "vdiscoverytask" in req.url.path:
                return httpx.Response(200, json=_ref("vdiscoverytask", "t1"))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure vdiscovery task vmtask1 delete", ctx)

        dels = _deletes_to(seen, "vdiscoverytask")
        assert len(dels) == 1

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure vdiscovery task nosuch delete", ctx)

        out = capsys.readouterr().out
        assert "No vDiscovery task found" in out


class TestVdiscoveryTaskStart:
    async def test_start_found(self):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": _ref("vdiscoverytask", "t1"), "name": "vmtask1"},
                        ]
                    ),
                )
            if req.method == "POST" and "vdiscoverytask" in req.url.path:
                return httpx.Response(200, json={})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure vdiscovery task vmtask1 start", ctx)

        posts = _posts_to(seen, "vdiscoverytask")
        assert len(posts) == 1
        query = posts[0].url.query
        query_str = query.decode() if isinstance(query, bytes) else query
        assert "vdiscovery_control" in query_str

    async def test_start_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure vdiscovery task nosuch start", ctx)

        out = capsys.readouterr().out
        assert "No vDiscovery task found" in out


class TestVdiscoveryTaskShow:
    async def test_show_all(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("vdiscoverytask", "t1"),
                                "name": "vmtask1",
                                "driver_type": "VMWARE",
                                "state": "IDLE",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show vdiscovery task", ctx)

        out = capsys.readouterr().out
        assert "type=vdiscoverytask" in out
        assert "name=vmtask1" in out
        assert "driver_type=VMWARE" in out

    async def test_show_by_name(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": _ref("vdiscoverytask", "t1"),
                                "name": "vmtask1",
                                "driver_type": "VMWARE",
                                "state": "IDLE",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show vdiscovery task vmtask1", ctx)

        out = capsys.readouterr().out
        assert "name=vmtask1" in out

    async def test_show_empty(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "vdiscoverytask" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show vdiscovery task nosuch", ctx)

        out = capsys.readouterr().out
        assert "No vDiscovery task found" in out

    async def test_not_connected(self, capsys):
        ctx = Context(client=None, online=False, host="")
        await process_line("show vdiscovery task", ctx)
        out = capsys.readouterr().out
        assert "Not connected" in out
