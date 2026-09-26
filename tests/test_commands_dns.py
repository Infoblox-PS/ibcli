# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.dns - Phase 11.

Covers:
  Chunk A: NS group sub-types (delegation, forwarding, forward_stub, stub) + allnsgroup
  Chunk B: DDNS principal clusters + cluster groups
  Chunk C: Record name policy + DNS64
  Chunk D: Ordered RPZ + allrecords aggregator
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import dns  # noqa: F401  ensures module registers handlers
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


def _posts_to(requests_seen: list, path_fragment: str) -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST" and path_fragment in r.url.path and "/logout" not in r.url.path
    ]


def _gets_to(requests_seen: list, path_fragment: str) -> list:
    return [r for r in requests_seen if r.method == "GET" and path_fragment in r.url.path]


def _puts_to(requests_seen: list, path_fragment: str) -> list:
    return [r for r in requests_seen if r.method == "PUT" and path_fragment in r.url.path]


def _deletes_to(requests_seen: list, path_fragment: str) -> list:
    return [r for r in requests_seen if r.method == "DELETE" and path_fragment in r.url.path]


# ===========================================================================
# Chunk A: NS group sub-types + allnsgroup
# ===========================================================================

# ---- delegation ----


async def test_add_nsgroup_delegation_basic():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:delegation/ZG5z:deleg1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup delegation add deleg1", ctx)

    posts = _posts_to(requests_seen, "nsgroup:delegation")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "deleg1"


async def test_add_nsgroup_delegation_with_delegate_to():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:delegation/ZG5z:deleg2"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure nsgroup delegation add deleg2 delegate_to ns1.test,1.2.3.4",
            ctx,
        )

    posts = _posts_to(requests_seen, "nsgroup:delegation")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "deleg2"
    assert body["delegate_to"] == [{"name": "ns1.test", "address": "1.2.3.4"}]


async def test_delete_nsgroup_delegation():
    requests_seen: list[httpx.Request] = []
    ref = "nsgroup:delegation/ZG5z:deleg1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "deleg1"}]))
        if req.method == "DELETE" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup delegation deleg1 delete", ctx)

    deletes = _deletes_to(requests_seen, "nsgroup:delegation")
    assert len(deletes) == 1


async def test_show_nsgroup_delegation_all(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "nsgroup:delegation/ZG5z:d1", "name": "d1", "comment": "test"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup delegation", ctx)

    out = capsys.readouterr().out
    assert "name=d1" in out
    assert "comment=test" in out


async def test_show_nsgroup_delegation_named(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "nsgroup:delegation" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "nsgroup:delegation/ZG5z:d1", "name": "d1"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup delegation d1", ctx)

    out = capsys.readouterr().out
    assert "d1" in out


# ---- forwarding member ----


async def test_add_nsgroup_forwarding_basic():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:forwardingmember" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:forwardingmember/ZG5z:fwd1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup forwarding add fwd1", ctx)

    posts = _posts_to(requests_seen, "nsgroup:forwardingmember")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "fwd1"


async def test_add_nsgroup_forwarding_with_servers():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:forwardingmember" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:forwardingmember/ZG5z:fwd2"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure nsgroup forwarding add fwd2 forwarding_servers ns.fwd.test",
            ctx,
        )

    posts = _posts_to(requests_seen, "nsgroup:forwardingmember")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "fwd2"
    assert body["forwarding_servers"] == [{"name": "ns.fwd.test"}]


async def test_delete_nsgroup_forwarding():
    requests_seen: list[httpx.Request] = []
    ref = "nsgroup:forwardingmember/ZG5z:fwd1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "nsgroup:forwardingmember" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "fwd1"}]))
        if req.method == "DELETE" and "nsgroup:forwardingmember" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup forwarding fwd1 delete", ctx)

    deletes = _deletes_to(requests_seen, "nsgroup:forwardingmember")
    assert len(deletes) == 1


async def test_show_nsgroup_forwarding(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "nsgroup:forwardingmember" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "nsgroup:forwardingmember/ZG5z:fwd1", "name": "fwd1"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup forwarding", ctx)

    out = capsys.readouterr().out
    assert "fwd1" in out


# ---- forward_stub server ----


async def test_add_nsgroup_forward_stub():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:forwardstubserver" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:forwardstubserver/ZG5z:fs1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup forward_stub add fs1", ctx)

    posts = _posts_to(requests_seen, "nsgroup:forwardstubserver")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "fs1"


async def test_delete_nsgroup_forward_stub():
    requests_seen: list[httpx.Request] = []
    ref = "nsgroup:forwardstubserver/ZG5z:fs1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "nsgroup:forwardstubserver" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "fs1"}]))
        if req.method == "DELETE" and "nsgroup:forwardstubserver" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup forward_stub fs1 delete", ctx)

    deletes = _deletes_to(requests_seen, "nsgroup:forwardstubserver")
    assert len(deletes) == 1


async def test_show_nsgroup_forward_stub(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "nsgroup:forwardstubserver" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "nsgroup:forwardstubserver/ZG5z:fs1",
                            "name": "fs1",
                            "comment": "stub",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup forward_stub", ctx)

    out = capsys.readouterr().out
    assert "fs1" in out
    assert "stub" in out


# ---- stub member ----


async def test_add_nsgroup_stub():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "nsgroup:stubmember" in req.url.path:
            return httpx.Response(201, json={"_ref": "nsgroup:stubmember/ZG5z:stub1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup stub add stub1", ctx)

    posts = _posts_to(requests_seen, "nsgroup:stubmember")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "stub1"


async def test_delete_nsgroup_stub():
    requests_seen: list[httpx.Request] = []
    ref = "nsgroup:stubmember/ZG5z:stub1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "nsgroup:stubmember" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "stub1"}]))
        if req.method == "DELETE" and "nsgroup:stubmember" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure nsgroup stub stub1 delete", ctx)

    deletes = _deletes_to(requests_seen, "nsgroup:stubmember")
    assert len(deletes) == 1


async def test_show_nsgroup_stub(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "nsgroup:stubmember" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "nsgroup:stubmember/ZG5z:stub1", "name": "stub1"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup stub", ctx)

    out = capsys.readouterr().out
    assert "stub1" in out


# ---- allnsgroup aggregate ----


async def test_show_nsgroup_all(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "allnsgroup" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "allnsgroup/ZG5z:deleg1", "name": "deleg1", "type": "DELEGATION"},
                        {"_ref": "allnsgroup/ZG5z:stub1", "name": "stub1", "type": "STUB_MEMBER"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show nsgroup all", ctx)

    out = capsys.readouterr().out
    assert "deleg1" in out
    assert "DELEGATION" in out
    assert "stub1" in out
    assert "STUB_MEMBER" in out


# ===========================================================================
# Chunk B: DDNS principal clusters + cluster groups
# ===========================================================================

# ---- ddns cluster ----


async def test_add_ddns_cluster_basic():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(201, json={"_ref": "ddns:principalcluster/ZG5z:c1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure ddns cluster add cluster1", ctx)

    posts = _posts_to(requests_seen, "ddns:principalcluster")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "cluster1"


async def test_add_ddns_cluster_with_principals():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(201, json={"_ref": "ddns:principalcluster/ZG5z:c2"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure ddns cluster add cluster2 principals host1.test,host2.test",
            ctx,
        )

    posts = _posts_to(requests_seen, "ddns:principalcluster")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "cluster2"
    assert "host1.test" in body["principals"]
    assert "host2.test" in body["principals"]


async def test_delete_ddns_cluster():
    requests_seen: list[httpx.Request] = []
    ref = "ddns:principalcluster/ZG5z:c1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "cluster1"}]))
        if req.method == "DELETE" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure ddns cluster cluster1 delete", ctx)

    deletes = _deletes_to(requests_seen, "ddns:principalcluster")
    assert len(deletes) == 1


async def test_set_ddns_cluster():
    requests_seen: list[httpx.Request] = []
    ref = "ddns:principalcluster/ZG5z:c1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "cluster1"}]))
        if req.method == "PUT" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure ddns cluster cluster1 set comment updated", ctx)

    puts = _puts_to(requests_seen, "ddns:principalcluster")
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert body["comment"] == "updated"


async def test_show_ddns_cluster(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "ddns:principalcluster" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "ddns:principalcluster/ZG5z:c1",
                            "name": "cluster1",
                            "principals": ["host1.test"],
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show ddns cluster", ctx)

    out = capsys.readouterr().out
    assert "cluster1" in out
    assert "host1.test" in out


# ---- ddns cluster_group ----


async def test_add_ddns_cluster_group_basic():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "ddns:principalcluster:group" in req.url.path:
            return httpx.Response(201, json={"_ref": "ddns:principalcluster:group/ZG5z:g1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure ddns cluster_group add grp1", ctx)

    posts = _posts_to(requests_seen, "ddns:principalcluster:group")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "grp1"


async def test_delete_ddns_cluster_group():
    requests_seen: list[httpx.Request] = []
    ref = "ddns:principalcluster:group/ZG5z:g1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "ddns:principalcluster:group" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "grp1"}]))
        if req.method == "DELETE" and "ddns:principalcluster:group" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure ddns cluster_group grp1 delete", ctx)

    deletes = _deletes_to(requests_seen, "ddns:principalcluster:group")
    assert len(deletes) == 1


async def test_show_ddns_cluster_group(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "ddns:principalcluster:group" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "ddns:principalcluster:group/ZG5z:g1",
                            "name": "grp1",
                            "comment": "my group",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show ddns cluster_group", ctx)

    out = capsys.readouterr().out
    assert "grp1" in out
    assert "my group" in out


# ===========================================================================
# Chunk C: Record name policy + DNS64
# ===========================================================================

# ---- record_name_policy ----


async def test_add_record_name_policy():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "recordnamepolicy" in req.url.path:
            return httpx.Response(201, json={"_ref": "recordnamepolicy/ZG5z:p1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure record_name_policy add pol1 regex ^[a-z]+$",
            ctx,
        )

    posts = _posts_to(requests_seen, "recordnamepolicy")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "pol1"
    assert body["regex"] == "^[a-z]+$"


async def test_delete_record_name_policy():
    requests_seen: list[httpx.Request] = []
    ref = "recordnamepolicy/ZG5z:p1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "recordnamepolicy" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "pol1"}]))
        if req.method == "DELETE" and "recordnamepolicy" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure record_name_policy pol1 delete", ctx)

    deletes = _deletes_to(requests_seen, "recordnamepolicy")
    assert len(deletes) == 1


async def test_show_record_name_policy(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "recordnamepolicy" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "recordnamepolicy/ZG5z:p1",
                            "name": "pol1",
                            "regex": "^[a-z]+$",
                            "is_default": False,
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record_name_policy", ctx)

    out = capsys.readouterr().out
    assert "pol1" in out
    assert "^[a-z]+$" in out


async def test_show_record_name_policy_named(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "recordnamepolicy" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "recordnamepolicy/ZG5z:p1",
                            "name": "pol1",
                            "regex": ".*",
                            "is_default": True,
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record_name_policy pol1", ctx)

    out = capsys.readouterr().out
    assert "pol1" in out
    assert "is_default=true" in out


# ---- dns64 ----


async def test_add_dns64():
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "POST" and "dns64group" in req.url.path:
            return httpx.Response(201, json={"_ref": "dns64group/ZG5z:g1"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure dns64 add mygroup prefix 64:ff9b::/96",
            ctx,
        )

    posts = _posts_to(requests_seen, "dns64group")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "mygroup"
    assert body["prefix"] == "64:ff9b::/96"


async def test_delete_dns64():
    requests_seen: list[httpx.Request] = []
    ref = "dns64group/ZG5z:g1"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "dns64group" in req.url.path:
            return httpx.Response(200, json=_list_resp([{"_ref": ref, "name": "mygroup"}]))
        if req.method == "DELETE" and "dns64group" in req.url.path:
            return httpx.Response(200, json=ref)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure dns64 mygroup delete", ctx)

    deletes = _deletes_to(requests_seen, "dns64group")
    assert len(deletes) == 1


async def test_show_dns64(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "dns64group" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "dns64group/ZG5z:g1",
                            "name": "mygroup",
                            "prefix": "64:ff9b::/96",
                            "comment": "nat64",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show dns64", ctx)

    out = capsys.readouterr().out
    assert "mygroup" in out
    assert "64:ff9b::/96" in out
    assert "nat64" in out


async def test_show_dns64_named(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "dns64group" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": "dns64group/ZG5z:g1", "name": "mygroup", "prefix": "64:ff9b::/96"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show dns64 mygroup", ctx)

    out = capsys.readouterr().out
    assert "mygroup" in out


# ===========================================================================
# Chunk D: Ordered RPZ + allrecords aggregator
# ===========================================================================

# ---- show rpz_order ----


async def test_show_rpz_order(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "orderedresponsepolicyzones" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "orderedresponsepolicyzones/ZG5z:default",
                            "view": "default",
                            "rp_zones": [
                                "zone_rp/ZG5z:rpz1.example.com/default",
                                "zone_rp/ZG5z:rpz2.example.com/default",
                            ],
                        }
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show rpz_order view=default", ctx)

    out = capsys.readouterr().out
    assert "view=default" in out
    assert "rpz1.example.com" in out
    assert "rpz2.example.com" in out


async def test_show_rpz_order_bare_form_requires_view(capsys):
    async with connected_ctx(None) as ctx:
        await process_line("show rpz_order", ctx)
    assert "Error: view required" in capsys.readouterr().out


async def test_show_rpz_order_with_view(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "orderedresponsepolicyzones" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "orderedresponsepolicyzones/ZG5z:ext",
                            "view": "ext",
                            "rp_zones": ["zone_rp/ZG5z:rpz1.test/ext"],
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show rpz_order view ext", ctx)

    gets = _gets_to(requests_seen, "orderedresponsepolicyzones")
    assert len(gets) >= 1


# ---- configure rpz_order set ----


async def test_configure_rpz_order_set():
    requests_seen: list[httpx.Request] = []
    ref = "orderedresponsepolicyzones/ZG5z:default"

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "orderedresponsepolicyzones" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {"_ref": ref, "view": "default", "rp_zones": []},
                    ]
                ),
            )
        if req.method == "PUT" and "orderedresponsepolicyzones" in req.url.path:
            return httpx.Response(200, json={"_ref": ref})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "configure rpz_order set rpz_list "
            "zone_rp/ZG5z:rpz1.example.com/default,zone_rp/ZG5z:rpz2.example.com/default",
            ctx,
        )

    puts = _puts_to(requests_seen, "orderedresponsepolicyzones")
    assert len(puts) == 1
    body = json.loads(puts[0].content)
    assert len(body["rp_zones"]) == 2
    assert "rpz1.example.com" in body["rp_zones"][0]


# ---- show record all ----


async def test_show_record_all(capsys):
    def handler(req: httpx.Request) -> httpx.Response | None:
        if req.method == "GET" and "allrecords" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "allrecords/ZG5z:a/default",
                            "name": "host1.example.com",
                            "type": "record:a",
                            "zone": "example.com",
                            "view": "default",
                        },
                        {
                            "_ref": "allrecords/ZG5z:txt/default",
                            "name": "host2.example.com",
                            "type": "record:txt",
                            "zone": "example.com",
                            "view": "default",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record all zone=example.com", ctx)

    out = capsys.readouterr().out
    assert "host1.example.com" in out
    assert "record:a" in out
    assert "host2.example.com" in out
    assert "record:txt" in out


async def test_show_record_all_bare_form_requires_zone(capsys):
    async with connected_ctx(None) as ctx:
        await process_line("show record all", ctx)
    assert "Error: zone required" in capsys.readouterr().out


async def test_show_record_all_with_name(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "allrecords" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "allrecords/ZG5z:a/default",
                            "name": "host1.example.com",
                            "type": "record:a",
                            "zone": "example.com",
                            "view": "default",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record all host1.example.com zone=example.com", ctx)

    gets = _gets_to(requests_seen, "allrecords")
    assert len(gets) >= 1
    out = capsys.readouterr().out
    assert "host1.example.com" in out


async def test_show_record_all_with_zone(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response | None:
        requests_seen.append(req)
        if req.method == "GET" and "allrecords" in req.url.path:
            return httpx.Response(
                200,
                json=_list_resp(
                    [
                        {
                            "_ref": "allrecords/ZG5z:a/default",
                            "name": "host1.example.com",
                            "type": "record:a",
                            "zone": "example.com",
                            "view": "default",
                        },
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show record all zone example.com", ctx)

    gets = _gets_to(requests_seen, "allrecords")
    assert len(gets) >= 1


# ===========================================================================
# Not-connected guard tests (spot-check a few handlers)
# ===========================================================================


async def test_not_connected_add_nsgroup_delegation(capsys):
    async with connected_ctx() as ctx:
        ctx.client = None
        await process_line("configure nsgroup delegation add deleg1", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_not_connected_add_ddns_cluster(capsys):
    async with connected_ctx() as ctx:
        ctx.client = None
        await process_line("configure ddns cluster add cluster1", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_not_connected_show_dns64(capsys):
    async with connected_ctx() as ctx:
        ctx.client = None
        await process_line("show dns64", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_not_connected_show_record_all(capsys):
    async with connected_ctx() as ctx:
        ctx.client = None
        await process_line("show record all", ctx)
    assert "Not connected" in capsys.readouterr().out
