# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for Phase 10 Chunk C - range template + ordered_range + dhcp_statistics."""

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
    COMMANDS.setdefault("NULL", CommandEntry(words="configure show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


def _list(items: list[dict]) -> dict:
    return {"result": items}


def _api_posts(requests_seen: list, fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (fragment == "" or fragment in r.url.path)
    ]


def _api_deletes(requests_seen: list, fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "DELETE" and (fragment == "" or fragment in r.url.path)
    ]


# ===========================================================================
# Range template (IPv4)
# ===========================================================================


class TestRangeTemplateAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "rangetemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template range add myrtpl", ctx)

        posts = _api_posts(requests_seen, "/rangetemplate")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myrtpl"

    async def test_add_with_number_of_addresses(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "rangetemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template range add myrtpl number_of_addresses 50", ctx)

        body = json.loads(_api_posts(requests_seen, "/rangetemplate")[0].content)
        assert body["number_of_addresses"] == 50

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/rangetemplate" in request.url.path:
                return httpx.Response(201, json={"_ref": "rangetemplate/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure template range add myrtpl comment "v4 range template"', ctx
            )

        body = json.loads(_api_posts(requests_seen, "/rangetemplate")[0].content)
        assert body["comment"] == "v4 range template"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template range add myrtpl", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestRangeTemplateDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/rangetemplate" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "rangetemplate/abc", "name": "myrtpl"}])
                )
            if request.method == "DELETE" and "/rangetemplate" in request.url.path:
                return httpx.Response(200, json="rangetemplate/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template range delete myrtpl", ctx)

        assert len(_api_deletes(requests_seen, "/rangetemplate")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/rangetemplate" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure template range delete nope", ctx)

        assert "No range template found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure template range delete myrtpl", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestRangeTemplateShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/rangetemplate" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "rangetemplate/abc",
                                "name": "myrtpl",
                                "number_of_addresses": 100,
                                "offset": 10,
                                "comment": "c1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template range", ctx)

        out = capsys.readouterr().out
        assert "myrtpl" in out
        assert "100" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/rangetemplate" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "rangetemplate/abc", "name": "myrtpl"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show template range myrtpl", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/rangetemplate" in r.url.path]
        assert gets
        assert "myrtpl" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show template range", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Ordered ranges (read-only)
# ===========================================================================


class TestOrderedRangeShow:
    async def test_bare_form_prints_helpful_error(self, capsys):
        """WAPI requires 'network' - bare form now gives a friendly error."""
        async with connected_ctx(None) as ctx:
            await process_line("show ordered_range", ctx)
        assert "Error: network required" in capsys.readouterr().out

    async def test_show_filtered_by_network(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/orderedranges" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "orderedranges/abc",
                                "network": "10.0.0.0/24",
                                "ranges": [],
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show ordered_range 10.0.0.0/24", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/orderedranges" in r.url.path]
        assert gets
        assert "10.0.0.0" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show ordered_range", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# DHCP statistics (read-only)
# ===========================================================================


class TestDhcpStatisticsShow:
    async def test_bare_form_prints_helpful_error(self, capsys):
        """WAPI requires 'statistics_object' - bare form now gives a friendly error."""
        async with connected_ctx(None) as ctx:
            await process_line("show dhcp_statistics", ctx)
        assert "Error: member required" in capsys.readouterr().out

    async def test_show_member_filter(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/dhcp:statistics" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "dhcp:statistics/abc",
                                "dhcp_utilization": 10000,
                                "dhcp_utilization_status": "LOW",
                                "dynamic_hosts": 20,
                                "static_hosts": 5,
                                "total_hosts": 100,
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show dhcp_statistics grid1.infoblox.com", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/dhcp:statistics" in r.url.path]
        assert gets
        assert "grid1.infoblox.com" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show dhcp_statistics", ctx)
        assert "Not connected" in capsys.readouterr().out
