# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for grid_ext - Phase 13.

Chunks A-D: captive_portal, nat_group, master_grid, gmc_group,
            gmc_schedule, license_gridwide, member dfp/cloudsync/parental_control.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import (
    grid,  # noqa: F401 - extends existing waypoints
    grid_ext,  # noqa: F401 - registers handlers
)
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root and show grid chain so the parser resolves top-level words."""
    from ibcli.registry import _merge_words  # type: ignore[attr-defined]

    COMMANDS.setdefault("NULL", CommandEntry(words="configure show restart"))
    show_grid = COMMANDS.setdefault("show grid", CommandEntry(words="<cr> <name>"))
    show_grid.words = _merge_words(show_grid.words or "", "<name>")


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


def _api_posts(requests_seen, path_fragment=""):
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_puts(requests_seen, path_fragment=""):
    return [
        r
        for r in requests_seen
        if r.method == "PUT" and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_deletes(requests_seen, path_fragment=""):
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (path_fragment == "" or path_fragment in r.url.path)
    ]


def _api_gets(requests_seen, path_fragment=""):
    return [
        r
        for r in requests_seen
        if r.method == "GET"
        and "_schema" not in str(r.url.query)
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ===========================================================================
# Chunk A - Captive Portal
# ===========================================================================


@pytest.mark.skip(reason="captive_portal commands hidden from CLI surface")
class TestCaptivePortal:
    async def test_add_captive_portal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "captiveportal" in request.url.path:
                return httpx.Response(201, json={"_ref": "captiveportal/ZG5z:portal1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure captive_portal add portal1.lab.com authn_server_group=mygrp", ctx
            )

        posts = _api_posts(requests_seen, "captiveportal")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "portal1.lab.com"
        assert body["authn_server_group"] == "mygrp"

    async def test_add_captive_portal_no_name(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure captive_portal add", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower() or "required" in out.lower() or "name" in out.lower()

    async def test_del_captive_portal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "captiveportal" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "captiveportal/ZG5z:p1", "name": "p1.lab.com"}])
                )
            if request.method == "DELETE":
                return httpx.Response(200, json="captiveportal/ZG5z:p1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure captive_portal p1.lab.com delete", ctx)

        deletes = _api_deletes(requests_seen, "captiveportal")
        assert len(deletes) == 1

    async def test_del_captive_portal_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "captiveportal" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure captive_portal nosuchportal delete", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no captive" in out.lower()

    async def test_set_captive_portal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "captiveportal" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "captiveportal/ZG5z:p1", "name": "p1.lab.com"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "captiveportal/ZG5z:p1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure captive_portal p1.lab.com set service_enabled=true", ctx)

        puts = _api_puts(requests_seen, "captiveportal")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["service_enabled"] is True

    async def test_show_captive_portal_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "captiveportal" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "captiveportal/ZG5z:p1",
                                "name": "p1.lab.com",
                                "service_enabled": True,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show captive_portal", ctx)
        out = capsys.readouterr().out
        assert "p1.lab.com" in out

    async def test_show_captive_portal_named(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "captiveportal" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "captiveportal/ZG5z:p1", "name": "p1.lab.com"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show captive_portal p1.lab.com", ctx)

        gets = _api_gets(requests_seen, "captiveportal")
        assert any("name=p1.lab.com" in str(r.url.query) or "name" in str(r.url) for r in gets)


# ===========================================================================
# Chunk A - NAT Group
# ===========================================================================


class TestNatGroup:
    async def test_add_nat_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "natgroup" in request.url.path:
                return httpx.Response(201, json={"_ref": "natgroup/ZG5z:ng1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure nat_group add my-natgrp comment="A NAT group"', ctx)

        posts = _api_posts(requests_seen, "natgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "my-natgrp"
        assert body["comment"] == "A NAT group"

    async def test_add_nat_group_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "natgroup" in request.url.path:
                return httpx.Response(201, json={"_ref": "natgroup/ZG5z:ng2"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nat_group add simplenatgrp", ctx)

        posts = _api_posts(requests_seen, "natgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "simplenatgrp"

    async def test_del_nat_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "natgroup" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "natgroup/ZG5z:ng1", "name": "my-natgrp"}])
                )
            if request.method == "DELETE":
                return httpx.Response(200, json="natgroup/ZG5z:ng1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nat_group my-natgrp delete", ctx)

        deletes = _api_deletes(requests_seen, "natgroup")
        assert len(deletes) == 1

    async def test_del_nat_group_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "natgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nat_group ghost delete", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no nat" in out.lower()

    async def test_set_nat_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "natgroup" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "natgroup/ZG5z:ng1", "name": "my-natgrp"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "natgroup/ZG5z:ng1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure nat_group my-natgrp set comment=updated", ctx)

        puts = _api_puts(requests_seen, "natgroup")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["comment"] == "updated"

    async def test_show_nat_group_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "natgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "natgroup/ZG5z:ng1", "name": "my-natgrp", "comment": "test"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show nat_group", ctx)
        out = capsys.readouterr().out
        assert "my-natgrp" in out

    async def test_show_nat_group_none(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "natgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show nat_group", ctx)
        out = capsys.readouterr().out
        assert "no nat" in out.lower()


# ===========================================================================
# Chunk B - Master Grid
# ===========================================================================


class TestMasterGrid:
    # NIOS 9.1 forbids create/delete on `mastergrid` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_add_master_grid(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "mastergrid" in request.url.path:
                return httpx.Response(201, json={"_ref": "mastergrid/ZG5z:mg1"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure master_grid add mymgm address=10.0.0.1", ctx)

        posts = _api_posts(requests_seen, "mastergrid")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["address"] == "10.0.0.1"

    async def test_add_master_grid_missing_address(self, capsys):
        async with connected_ctx(enforce_restrictions=False) as ctx:
            await process_line("configure master_grid add mymgm", ctx)
        out = capsys.readouterr().out
        assert "address" in out.lower() or "required" in out.lower()

    async def test_del_master_grid(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "mastergrid" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "mastergrid/ZG5z:mg1", "address": "10.0.0.1"}])
                )
            if request.method == "DELETE":
                return httpx.Response(200, json="mastergrid/ZG5z:mg1")
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure master_grid 10.0.0.1 delete", ctx)

        deletes = _api_deletes(requests_seen, "mastergrid")
        assert len(deletes) == 1

    async def test_del_master_grid_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "mastergrid" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure master_grid ghost delete", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no master" in out.lower()

    async def test_set_master_grid(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "mastergrid" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "mastergrid/ZG5z:mg1", "address": "10.0.0.1"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "mastergrid/ZG5z:mg1"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure master_grid 10.0.0.1 set enable=true", ctx)

        puts = _api_puts(requests_seen, "mastergrid")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["enable"] is True

    async def test_show_master_grid(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "mastergrid" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "mastergrid/ZG5z:mg1",
                                "address": "10.0.0.1",
                                "join_status": "WORKING",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show master_grid", ctx)
        out = capsys.readouterr().out
        assert "10.0.0.1" in out
        assert "WORKING" in out

    async def test_show_master_grid_empty(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "mastergrid" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show master_grid", ctx)
        out = capsys.readouterr().out
        assert "no master" in out.lower()


# ===========================================================================
# Chunk B - GMC Group
# ===========================================================================


@pytest.mark.skip(reason="gmc_group commands hidden from CLI surface")
class TestGmcGroup:
    async def test_add_gmc_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "gmcgroup" in request.url.path:
                return httpx.Response(201, json={"_ref": "gmcgroup/ZG5z:g1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure gmc_group add mygroup comment="GMC Group"', ctx)

        posts = _api_posts(requests_seen, "gmcgroup")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "mygroup"
        assert body["comment"] == "GMC Group"

    async def test_del_gmc_group(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "gmcgroup" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "gmcgroup/ZG5z:g1", "name": "mygroup"}])
                )
            if request.method == "DELETE":
                return httpx.Response(200, json="gmcgroup/ZG5z:g1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure gmc_group mygroup delete", ctx)

        deletes = _api_deletes(requests_seen, "gmcgroup")
        assert len(deletes) == 1

    async def test_del_gmc_group_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "gmcgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure gmc_group ghost delete", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no gmc" in out.lower()

    async def test_show_gmc_group(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "gmcgroup" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "gmcgroup/ZG5z:g1", "name": "mygroup", "comment": "test"},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show gmc_group", ctx)
        out = capsys.readouterr().out
        assert "mygroup" in out

    async def test_show_gmc_group_none(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "gmcgroup" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show gmc_group", ctx)
        out = capsys.readouterr().out
        assert "no gmc" in out.lower()


# ===========================================================================
# Chunk B - GMC Schedule
# ===========================================================================


@pytest.mark.skip(reason="gmc_schedule commands hidden from CLI surface")
class TestGmcSchedule:
    async def test_add_gmc_schedule(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "gmcschedule" in request.url.path:
                return httpx.Response(201, json={"_ref": "gmcschedule/ZG5z:s1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure gmc_schedule add start_time=1700000000", ctx)

        posts = _api_posts(requests_seen, "gmcschedule")
        assert len(posts) == 1

    async def test_del_gmc_schedule(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "DELETE":
                return httpx.Response(200, json="gmcschedule/ZG5z:s1")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure gmc_schedule gmcschedule/ZG5z:s1 delete", ctx)

        deletes = _api_deletes(requests_seen)
        assert len(deletes) == 1

    async def test_set_gmc_schedule(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "gmcschedule/ZG5z:s1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure gmc_schedule gmcschedule/ZG5z:s1 set activate_gmc_group_schedule=true",
                ctx,
            )

        puts = _api_puts(requests_seen)
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["activate_gmc_group_schedule"] is True

    async def test_show_gmc_schedule(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "gmcschedule" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "gmcschedule/ZG5z:s1", "activate_gmc_group_schedule": True},
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show gmc_schedule", ctx)
        out = capsys.readouterr().out
        assert "activate_gmc_group_schedule" in out or "gmcschedule" in out

    async def test_show_gmc_schedule_empty(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "gmcschedule" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show gmc_schedule", ctx)
        out = capsys.readouterr().out
        assert "no gmc" in out.lower()


# ===========================================================================
# Chunk C - Grid-wide License
# ===========================================================================


class TestLicenseGridwide:
    # NIOS 9.1 forbids create on `license:gridwide` and the SDK refuses it
    # before the request is built. These assert the request the CLI
    # *would* send, so enforcement is off here.
    async def test_show_license_gridwide(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if (
                request.method == "GET"
                and "license" in request.url.path
                and "gridwide" in request.url.path
            ):
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "license:gridwide/ZG5z:l1",
                                "type": "DNS",
                                "expiration_status": "PERMANENT",
                                "key": "ABC123",
                                "limit": "unlimited",
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show license_gridwide", ctx)
        out = capsys.readouterr().out
        assert "DNS" in out
        assert "PERMANENT" in out

    async def test_show_license_gridwide_empty(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "license" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("show license_gridwide", ctx)
        out = capsys.readouterr().out
        assert "no grid-wide" in out.lower()

    async def test_add_license_gridwide(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "license" in request.url.path:
                return httpx.Response(201, json={"_ref": "license:gridwide/ZG5z:l1"})
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure license_gridwide add dns", ctx)

        posts = _api_posts(requests_seen)
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["type"] == "DNS"

    async def test_del_license_gridwide(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "license" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "license:gridwide/ZG5z:l1", "type": "DNS"}])
                )
            if request.method == "DELETE":
                return httpx.Response(200, json="license:gridwide/ZG5z:l1")
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure license_gridwide dns delete", ctx)

        deletes = _api_deletes(requests_seen)
        assert len(deletes) == 1

    async def test_del_license_gridwide_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "license" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler, enforce_restrictions=False) as ctx:
            await process_line("configure license_gridwide NOSUCHLICENSE delete", ctx)
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "no license" in out.lower()


# ===========================================================================
# Chunk D - Member DFP
# ===========================================================================


class TestMemberDfp:
    async def test_show_member_dfp(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "memberdfp" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "memberdfp/ZG5z:d1",
                                "host_name": "ns1.lab.com",
                                "dfp_forward_first": True,
                                "is_dfp_override": False,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com dfp", ctx)
        out = capsys.readouterr().out
        assert "ns1.lab.com" in out
        assert "dfp_forward_first" in out

    async def test_show_member_dfp_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "memberdfp" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns1.lab.com dfp", ctx)
        out = capsys.readouterr().out
        assert "no memberdfp" in out.lower() or "not found" in out.lower()

    async def test_set_member_dfp(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "memberdfp" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "memberdfp/ZG5z:d1", "host_name": "ns1.lab.com"}])
                )
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "memberdfp/ZG5z:d1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns1.lab.com dfp set dfp_forward_first=true", ctx
            )

        puts = _api_puts(requests_seen, "memberdfp")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["dfp_forward_first"] is True

    async def test_set_member_dfp_no_kvs(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure grid Infoblox member ns1.lab.com dfp set", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower() or "specify" in out.lower()


# ===========================================================================
# Chunk D - Member Cloud Sync
# ===========================================================================


class TestMemberCloudsync:
    async def test_show_member_cloudsync(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "membercloudsync" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "membercloudsync/ZG5z:c1",
                                "host_name": "ns2.lab.com",
                                "cloud_sync_enabled": True,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns2.lab.com cloudsync", ctx)
        out = capsys.readouterr().out
        assert "ns2.lab.com" in out
        assert "cloud_sync_enabled" in out

    async def test_show_member_cloudsync_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "membercloudsync" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns2.lab.com cloudsync", ctx)
        out = capsys.readouterr().out
        assert "no membercloudsync" in out.lower() or "not found" in out.lower()

    async def test_set_member_cloudsync(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "membercloudsync" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list([{"_ref": "membercloudsync/ZG5z:c1", "host_name": "ns2.lab.com"}]),
                )
            if request.method == "PUT":
                return httpx.Response(200, json={"_ref": "membercloudsync/ZG5z:c1"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid Infoblox member ns2.lab.com cloudsync set cloud_sync_enabled=false",
                ctx,
            )

        puts = _api_puts(requests_seen, "membercloudsync")
        assert len(puts) == 1
        body = json.loads(puts[0].content)
        assert body["cloud_sync_enabled"] is False

    async def test_set_member_cloudsync_no_kvs(self, capsys):
        async with connected_ctx() as ctx:
            await process_line("configure grid Infoblox member ns2.lab.com cloudsync set", ctx)
        out = capsys.readouterr().out
        assert "error" in out.lower() or "specify" in out.lower()


# ===========================================================================
# Chunk D - Member Parental Control (show-only)
# ===========================================================================


class TestMemberParentalControl:
    async def test_show_member_parental_control(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "parentalcontrol" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "member:parentalcontrol/ZG5z:pc1",
                                "name": "ns3.lab.com",
                                "enable_service": False,
                            }
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns3.lab.com parental_control", ctx)
        out = capsys.readouterr().out
        assert "ns3.lab.com" in out
        assert "enable_service" in out

    async def test_show_member_parental_control_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "parentalcontrol" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid Infoblox member ns3.lab.com parental_control", ctx)
        out = capsys.readouterr().out
        assert "no member" in out.lower() or "not found" in out.lower()
