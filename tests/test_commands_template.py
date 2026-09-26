# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.template - async SDK style."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import template  # noqa: F401  - registers handlers
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
    return {"result": items}


def _api_posts(requests_seen: list, path_fragment: str = "") -> list:
    return [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/logout" not in r.url.path
        and (path_fragment == "" or path_fragment in r.url.path)
    ]


# ---------------------------------------------------------------------------
# configure template network add
# ---------------------------------------------------------------------------


async def test_add_network_template():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/networktemplate" in request.url.path:
            return httpx.Response(201, json={"_ref": "networktemplate/ZG5z:mytempl/default"})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure template network add mytempl cidr 24", ctx)

    posts = _api_posts(requests_seen, "/networktemplate")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "mytempl"
    # WAPI's networktemplate uses `netmask` (prefix length); the CLI's user
    # facing `cidr <n>` keyword maps to it.
    assert body["netmask"] == 24


async def test_add_template_with_comment_and_extattrs():
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "POST" and "/networktemplate" in request.url.path:
            return httpx.Response(201, json={"_ref": "networktemplate/ZG5z:t2/default"})
        return None

    from ibcli.commands.template import cli_add_network_template

    async with connected_ctx(handler) as ctx:
        await cli_add_network_template(
            'configure template network add t2 cidr 16 comment "corp net" set owner=alice',
            ctx,
        )

    posts = _api_posts(requests_seen, "/networktemplate")
    assert len(posts) == 1
    body = json.loads(posts[0].content)
    assert body["name"] == "t2"
    # WAPI's networktemplate uses `netmask` (prefix length); the CLI's user
    # facing `cidr <n>` keyword maps to it.
    assert body["netmask"] == 16
    assert body["comment"] == "corp net"
    assert body["extattrs"] == {"owner": {"value": "alice"}}


async def test_add_template_requires_cidr(capsys):
    from ibcli.commands.template import cli_add_network_template

    async with connected_ctx() as ctx:
        await cli_add_network_template("configure template network add mytempl", ctx)

    out = capsys.readouterr().out
    assert "cidr required" in out


async def test_add_template_not_connected(capsys):
    ctx = Context()
    await process_line("configure template network add mytempl cidr 24", ctx)
    assert "Not connected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# configure template network <name> delete
# ---------------------------------------------------------------------------


async def test_delete_network_template():
    ref = "networktemplate/ZG5z:mytempl/default"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networktemplate" in request.url.path:
            return httpx.Response(200, json=_list([{"_ref": ref, "name": "mytempl"}]))
        if request.method == "DELETE" and ref in request.url.path:
            return httpx.Response(200, json=f'"{ref}"')
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure template network mytempl delete", ctx)

    deletes = [r for r in requests_seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert ref in deletes[0].url.path


async def test_delete_template_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/networktemplate" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("configure template network nosuchtmpl delete", ctx)

    assert "No template found" in capsys.readouterr().out


async def test_delete_template_not_connected(capsys):
    ctx = Context()
    await process_line("configure template network mytempl delete", ctx)
    assert "Not connected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# show template network
# ---------------------------------------------------------------------------


async def test_show_network_template_all(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/networktemplate" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {
                            "_ref": "networktemplate/a:t1/d",
                            "name": "t1",
                            "cidr": 24,
                            "comment": "first",
                        },
                        {"_ref": "networktemplate/b:t2/d", "name": "t2", "cidr": 16},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show template network", ctx)

    out = capsys.readouterr().out
    assert "t1" in out
    assert "t2" in out
    assert "24" in out
    assert "first" in out


async def test_show_network_template_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/networktemplate" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {"_ref": "networktemplate/a:t1/d", "name": "t1", "cidr": 24},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show template network t1", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/networktemplate" in r.url.path]
    assert any("name=t1" in str(r.url) for r in gets)
    assert "t1" in capsys.readouterr().out


async def test_show_network_template_not_found(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/networktemplate" in request.url.path:
            return httpx.Response(200, json=_list([]))
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show template network nosuchtmpl", ctx)

    assert "No template found" in capsys.readouterr().out


async def test_show_template_not_connected(capsys):
    ctx = Context()
    await process_line("show template network", ctx)
    assert "Not connected" in capsys.readouterr().out
