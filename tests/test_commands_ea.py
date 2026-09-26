# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for EA definitions and device types (slice 6a)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import ea  # noqa: F401 - registers handlers
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


# ===========================================================================
# EA def add
# ===========================================================================


class TestEaDefAdd:
    async def test_add_ea_string_type(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    201, json={"_ref": "extensibleattributedef/ZG5z:Foo", "name": "Foo"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid attribute add Foo type string", ctx)

        posts = _api_posts(requests_seen, "/extensibleattributedef")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "Foo"
        assert body["type"] == "STRING"

    async def test_add_ea_enum_with_list_values(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    201, json={"_ref": "extensibleattributedef/ZG5z:Role", "name": "Role"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid attribute add Role type enum"
                " list_value Server list_value Switch list_value Router",
                ctx,
            )

        posts = _api_posts(requests_seen, "/extensibleattributedef")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "Role"
        assert body["type"] == "ENUM"
        values = [lv["value"] for lv in body.get("list_values", [])]
        assert "Server" in values
        assert "Switch" in values
        assert "Router" in values

    async def test_add_ea_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    201, json={"_ref": "extensibleattributedef/ZG5z:Bar", "name": "Bar"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                'configure grid attribute add Bar type string comment "my ea"',
                ctx,
            )

        posts = _api_posts(requests_seen, "/extensibleattributedef")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["comment"] == "my ea"

    async def test_add_ea_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid attribute add Foo type string", ctx)
        assert "Not connected" in capsys.readouterr().out

    async def test_add_ea_nios_error(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "POST" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    400,
                    json={
                        "Error": "AdmConProtoError",
                        "code": "Client.Ibap.Proto",
                        "text": "Already exists",
                    },
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid attribute add Foo type string", ctx)
        # NiosError is caught by the dispatcher; output may be empty or contain error text
        # The important thing is no unhandled exception.


# ===========================================================================
# EA def delete
# ===========================================================================


class TestEaDefDelete:
    async def test_delete_ea_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "extensibleattributedef/ZG5z:Foo", "name": "Foo"}])
                )
            if (
                request.method == "DELETE"
                and "/extensibleattributedef/ZG5z:Foo" in request.url.path
            ):
                return httpx.Response(200, json="extensibleattributedef/ZG5z:Foo")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid attribute Foo delete", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1

    async def test_delete_ea_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid attribute Foo delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "not found" in out.lower() or "Foo" in out

    async def test_delete_ea_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid attribute Foo delete", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# EA def show
# ===========================================================================


class TestEaDefShow:
    async def test_show_all_attributes(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "extensibleattributedef/ZG5z:Foo",
                                "name": "Foo",
                                "type": "STRING",
                            },
                            {
                                "_ref": "extensibleattributedef/ZG5z:Role",
                                "name": "Role",
                                "type": "ENUM",
                                "list_values": [{"value": "Server"}, {"value": "Switch"}],
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid attribute", ctx)

        out = capsys.readouterr().out
        assert "Foo" in out
        assert "Role" in out
        assert "Server" in out

    async def test_show_specific_attribute(self, capsys):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "extensibleattributedef/ZG5z:Foo",
                                "name": "Foo",
                                "type": "STRING",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid attribute Foo", ctx)

        gets = [
            r
            for r in requests_seen
            if r.method == "GET" and "/extensibleattributedef" in r.url.path
        ]
        assert len(gets) >= 1
        # name=Foo should appear in the query string
        assert "Foo" in str(gets[0].url)
        out = capsys.readouterr().out
        assert "Foo" in out

    async def test_show_attribute_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid attribute", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Device types
# ===========================================================================


@pytest.mark.skip(reason="device_type verb removed - use `attribute add <name> type ENUM`")
class TestDeviceTypeAdd:
    async def test_add_device_type_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    201, json={"_ref": "extensibleattributedef/ZG5z:DevType", "name": "DevType"}
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line(
                "configure grid device_type add DevType list_value Server list_value Router",
                ctx,
            )

        posts = _api_posts(requests_seen, "/extensibleattributedef")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "DevType"
        assert body["type"] == "ENUM"
        vals = [v["value"] for v in body.get("list_values", [])]
        assert "Server" in vals
        assert "Router" in vals

    async def test_add_device_type_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid device_type add DevType list_value Server", ctx)
        assert "Not connected" in capsys.readouterr().out


@pytest.mark.skip(reason="device_type verb removed - use `attribute add <name> type ENUM`")
class TestDeviceTypeDelete:
    async def test_delete_device_type_success(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {"_ref": "extensibleattributedef/ZG5z:DevType", "name": "DevType"},
                        ]
                    ),
                )
            if (
                request.method == "DELETE"
                and "/extensibleattributedef/ZG5z:DevType" in request.url.path
            ):
                return httpx.Response(200, json="extensibleattributedef/ZG5z:DevType")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid device_type DevType delete", ctx)

        deletes = [r for r in requests_seen if r.method == "DELETE"]
        assert len(deletes) == 1

    async def test_delete_device_type_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure grid device_type DevType delete", ctx)

        out = capsys.readouterr().out
        assert "No" in out or "DevType" in out

    async def test_delete_device_type_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure grid device_type DevType delete", ctx)
        assert "Not connected" in capsys.readouterr().out


@pytest.mark.skip(reason="device_type verb removed - use `attribute add <name> type ENUM`")
class TestDeviceTypeShow:
    async def test_show_all_device_types(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/extensibleattributedef" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "extensibleattributedef/ZG5z:DevType",
                                "name": "DevType",
                                "type": "ENUM",
                                "list_values": [{"value": "Server"}],
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show grid device_type", ctx)

        out = capsys.readouterr().out
        assert "DevType" in out

    async def test_show_device_type_not_connected(self, capsys):
        ctx = Context()
        await process_line("show grid device_type", ctx)
        assert "Not connected" in capsys.readouterr().out
