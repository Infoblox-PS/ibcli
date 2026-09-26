# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.upgrade - Phase 9.

Covers:
  Chunk A: upgrade_group - show, add, delete, set
  Chunk B: upgrade_schedule (singleton) - show, set
  Chunk C: distribution_schedule (singleton) - show, set
  Chunk D: upgrade_status (read-only) - show (all + by member)

Notes:
- WAPI list responses must be wrapped as {"result": [...]} (paging envelope).
- upgradeschedule and distributionschedule are singletons - no add/delete.
- upgradestatus is fully read-only - show only.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import upgrade  # noqa: F401  - registers handlers
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


# ---------------------------------------------------------------------------
# Request-inspection helpers
# ---------------------------------------------------------------------------


def _gets(seen: list, fragment: str = "") -> list:
    return [
        r
        for r in seen
        if r.method == "GET"
        and "/_schema" not in r.url.path
        and "/grid/session" not in r.url.path
        and (fragment == "" or fragment in r.url.path)
    ]


def _posts(seen: list, fragment: str = "") -> list:
    return [
        r
        for r in seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (fragment == "" or fragment in r.url.path)
    ]


def _deletes(seen: list, fragment: str = "") -> list:
    return [r for r in seen if r.method == "DELETE" and (fragment == "" or fragment in r.url.path)]


def _puts(seen: list, fragment: str = "") -> list:
    return [r for r in seen if r.method == "PUT" and (fragment == "" or fragment in r.url.path)]


def _list(items: list) -> dict:
    return {"result": items}


def _ref(obj_type: str, name: str) -> str:
    return f"{obj_type}/ZG5z:{name}"


# ===========================================================================
# Chunk A - upgrade_group
# ===========================================================================


class TestShowUpgradeGroup:
    async def test_show_all(self, capsys):
        groups = [
            {
                "_ref": _ref("upgradegroup", "grp1"),
                "name": "grp1",
                "upgrade_policy": "SIMULTANEOUSLY",
            },
            {
                "_ref": _ref("upgradegroup", "grp2"),
                "name": "grp2",
                "upgrade_policy": "SEQUENTIALLY",
                "comment": "second group",
            },
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list(groups))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_group", ctx)

        out = capsys.readouterr().out
        assert "grp1" in out
        assert "grp2" in out
        assert "SIMULTANEOUSLY" in out

    async def test_show_by_name(self, capsys):
        groups = [
            {
                "_ref": _ref("upgradegroup", "grp1"),
                "name": "grp1",
                "upgrade_policy": "SIMULTANEOUSLY",
            }
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list(groups))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_group grp1", ctx)

        out = capsys.readouterr().out
        assert "grp1" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show upgrade_group", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_group nope", ctx)

        assert "No upgrade group found" in capsys.readouterr().out


class TestAddUpgradeGroup:
    async def test_add_minimal(self, capsys):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "upgradegroup" in req.url.path:
                return httpx.Response(
                    200,
                    json={"_ref": _ref("upgradegroup", "mygroup"), "name": "mygroup"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_group add mygroup", ctx)

        posts = _posts(seen, "upgradegroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mygroup"
        assert "Created" in capsys.readouterr().out

    async def test_add_with_options(self, capsys):
        seen: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "POST" and "upgradegroup" in req.url.path:
                return httpx.Response(
                    200,
                    json={"_ref": _ref("upgradegroup", "mygroup"), "name": "mygroup"},
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure upgrade_group add mygroup comment=testcomment "
                "upgrade_policy=SEQUENTIALLY distribution_policy=SIMULTANEOUSLY",
                ctx,
            )

        posts = _posts(seen, "upgradegroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mygroup"
        assert body["comment"] == "testcomment"
        assert body["upgrade_policy"] == "SEQUENTIALLY"
        assert body["distribution_policy"] == "SIMULTANEOUSLY"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure upgrade_group add mygroup", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestDeleteUpgradeGroup:
    async def test_delete(self, capsys):
        seen: list[httpx.Request] = []
        grp_ref = _ref("upgradegroup", "grp1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": grp_ref, "name": "grp1"}]))
            if req.method == "DELETE" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=grp_ref)
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_group grp1 delete", ctx)

        dels = _deletes(seen, "upgradegroup")
        assert len(dels) == 1
        assert "Deleted" in capsys.readouterr().out

    async def test_delete_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_group nope delete", ctx)

        assert "No upgrade group found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure upgrade_group grp1 delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestSetUpgradeGroup:
    async def test_set_field(self, capsys):
        seen: list[httpx.Request] = []
        grp_ref = _ref("upgradegroup", "grp1")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": grp_ref, "name": "grp1"}]))
            if req.method == "PUT" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json={"_ref": grp_ref, "name": "grp1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_group grp1 set comment=updated", ctx)

        puts = _puts(seen, "upgradegroup")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"
        assert "Updated" in capsys.readouterr().out

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradegroup" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_group nope set comment=x", ctx)

        assert "No upgrade group found" in capsys.readouterr().out

    async def test_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure upgrade_group grp1 set comment=x", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk B - upgrade_schedule (singleton)
# ===========================================================================


class TestShowUpgradeSchedule:
    async def test_show(self, capsys):
        sched = [
            {"_ref": _ref("upgradeschedule", "default"), "active": True, "start_time": 1700000000}
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradeschedule" in req.url.path:
                return httpx.Response(200, json=_list(sched))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_schedule", ctx)

        out = capsys.readouterr().out
        assert "active=True" in out
        assert "1700000000" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradeschedule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_schedule", ctx)

        assert "No upgrade schedule found" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show upgrade_schedule", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestSetUpgradeSchedule:
    async def test_set(self, capsys):
        seen: list[httpx.Request] = []
        sched_ref = _ref("upgradeschedule", "default")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "upgradeschedule" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": sched_ref, "active": False}]))
            if req.method == "PUT" and "upgradeschedule" in req.url.path:
                return httpx.Response(200, json={"_ref": sched_ref, "active": True})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_schedule set active=true", ctx)

        puts = _puts(seen, "upgradeschedule")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["active"] is True
        assert "Updated" in capsys.readouterr().out

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradeschedule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure upgrade_schedule set active=true", ctx)

        assert "No upgrade schedule found" in capsys.readouterr().out

    async def test_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure upgrade_schedule set active=true", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk C - distribution_schedule (singleton)
# ===========================================================================


class TestShowDistributionSchedule:
    async def test_show(self, capsys):
        sched = [
            {
                "_ref": _ref("distributionschedule", "default"),
                "active": False,
                "start_time": 1700001000,
            }
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "distributionschedule" in req.url.path:
                return httpx.Response(200, json=_list(sched))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show distribution_schedule", ctx)

        out = capsys.readouterr().out
        assert "active=False" in out
        assert "1700001000" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "distributionschedule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show distribution_schedule", ctx)

        assert "No distribution schedule found" in capsys.readouterr().out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show distribution_schedule", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestSetDistributionSchedule:
    async def test_set(self, capsys):
        seen: list[httpx.Request] = []
        sched_ref = _ref("distributionschedule", "default")

        def handler(req: httpx.Request) -> httpx.Response | None:
            seen.append(req)
            if req.method == "GET" and "distributionschedule" in req.url.path:
                return httpx.Response(200, json=_list([{"_ref": sched_ref, "active": False}]))
            if req.method == "PUT" and "distributionschedule" in req.url.path:
                return httpx.Response(200, json={"_ref": sched_ref, "active": True})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure distribution_schedule set active=true", ctx)

        puts = _puts(seen, "distributionschedule")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["active"] is True
        assert "Updated" in capsys.readouterr().out

    async def test_set_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "distributionschedule" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure distribution_schedule set active=true", ctx)

        assert "No distribution schedule found" in capsys.readouterr().out

    async def test_set_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure distribution_schedule set active=true", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Chunk D - upgrade_status (read-only)
# ===========================================================================


class TestShowUpgradeStatus:
    async def test_show_grid(self, capsys):
        statuses = [
            {
                "_ref": _ref("upgradestatus", "grid"),
                "type": "GRID",
                "grid_state": "DEFAULT",
                "current_version": "9.0.0",
            },
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradestatus" in req.url.path:
                return httpx.Response(200, json=_list(statuses))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_status grid", ctx)

        out = capsys.readouterr().out
        assert "DEFAULT" in out
        assert "9.0.0" in out

    async def test_show_by_member(self, capsys):
        statuses = [
            {
                "_ref": _ref("upgradestatus", "ns1"),
                "type": "VNODE",
                "member": "ns1.example.com",
                "current_version": "9.0.0",
                "upgrade_state": "NONE",
                "element_status": "WORKING",
            },
        ]

        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradestatus" in req.url.path:
                return httpx.Response(200, json=_list(statuses))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_status vnode ns1.example.com", ctx)

        out = capsys.readouterr().out
        assert "ns1.example.com" in out
        assert "WORKING" in out

    async def test_show_not_found(self, capsys):
        def handler(req: httpx.Request) -> httpx.Response | None:
            if req.method == "GET" and "upgradestatus" in req.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show upgrade_status vnode nosuchmember", ctx)

        assert "No upgrade status found" in capsys.readouterr().out

    async def test_show_bare_form_prints_incomplete(self, capsys):
        """The grammar now requires a type selector; bare form gets 'Incomplete'."""
        async with connected_ctx(None) as ctx:
            await process_line("show upgrade_status", ctx)
        out = capsys.readouterr().out
        assert "Incomplete" in out
        assert "grid" in out and "vnode" in out

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show upgrade_status grid", ctx)
        assert "Not connected" in capsys.readouterr().out
