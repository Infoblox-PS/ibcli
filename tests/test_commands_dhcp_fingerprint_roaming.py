# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for Phase 10 Chunk B - fingerprint definitions + roaming hosts."""

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
# Fingerprint definitions
# ===========================================================================


class TestFingerprintAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fingerprint" in request.url.path:
                return httpx.Response(201, json={"_ref": "fingerprint/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure fingerprint add myfp", ctx)

        posts = _api_posts(requests_seen, "/fingerprint")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myfp"

    async def test_add_with_vendor_id(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fingerprint" in request.url.path:
                return httpx.Response(201, json={"_ref": "fingerprint/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure fingerprint add myfp vendor_id MSFT-5.0", ctx)

        body = json.loads(_api_posts(requests_seen, "/fingerprint")[0].content)
        assert body["vendor_id"] == ["MSFT-5.0"]

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/fingerprint" in request.url.path:
                return httpx.Response(201, json={"_ref": "fingerprint/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure fingerprint add myfp comment "Windows 10 FP"', ctx)

        body = json.loads(_api_posts(requests_seen, "/fingerprint")[0].content)
        assert body["comment"] == "Windows 10 FP"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure fingerprint add myfp", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFingerprintDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fingerprint" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "fingerprint/abc", "name": "myfp"}])
                )
            if request.method == "DELETE" and "/fingerprint" in request.url.path:
                return httpx.Response(200, json="fingerprint/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure fingerprint myfp delete", ctx)

        assert len(_api_deletes(requests_seen, "/fingerprint")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fingerprint" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure fingerprint nope delete", ctx)

        assert "No fingerprint found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure fingerprint myfp delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestFingerprintShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/fingerprint" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "fingerprint/abc",
                                "name": "myfp",
                                "vendor_id": ["MSFT-5.0"],
                                "comment": "Windows",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show fingerprint", ctx)

        out = capsys.readouterr().out
        assert "myfp" in out
        assert "MSFT-5.0" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/fingerprint" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "fingerprint/abc", "name": "myfp"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show fingerprint myfp", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/fingerprint" in r.url.path]
        assert gets
        assert "myfp" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show fingerprint", ctx)
        assert "Not connected" in capsys.readouterr().out


# ===========================================================================
# Roaming hosts
# ===========================================================================


class TestRoamingHostAdd:
    async def test_add_minimal(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/roaminghost" in request.url.path:
                return httpx.Response(201, json={"_ref": "roaminghost/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure roaming_host add myhost", ctx)

        posts = _api_posts(requests_seen, "/roaminghost")
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body["name"] == "myhost"

    async def test_add_with_match_client(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/roaminghost" in request.url.path:
                return httpx.Response(201, json={"_ref": "roaminghost/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure roaming_host add myhost match_client MAC_ADDRESS", ctx)

        body = json.loads(_api_posts(requests_seen, "/roaminghost")[0].content)
        assert body["match_client"] == "MAC_ADDRESS"

    async def test_add_with_comment(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "POST" and "/roaminghost" in request.url.path:
                return httpx.Response(201, json={"_ref": "roaminghost/abc"})
            return None

        async with connected_ctx(handler) as ctx:
            await process_line('configure roaming_host add myhost comment "laptop pool"', ctx)

        body = json.loads(_api_posts(requests_seen, "/roaminghost")[0].content)
        assert body["comment"] == "laptop pool"

    async def test_add_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure roaming_host add myhost", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestRoamingHostDelete:
    async def test_delete(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/roaminghost" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "roaminghost/abc", "name": "myhost"}])
                )
            if request.method == "DELETE" and "/roaminghost" in request.url.path:
                return httpx.Response(200, json="roaminghost/abc")
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure roaming_host myhost delete", ctx)

        assert len(_api_deletes(requests_seen, "/roaminghost")) == 1

    async def test_delete_not_found(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/roaminghost" in request.url.path:
                return httpx.Response(200, json=_list([]))
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("configure roaming_host nope delete", ctx)

        assert "No roaming host found" in capsys.readouterr().out

    async def test_delete_not_connected(self, capsys):
        ctx = Context()
        await process_line("configure roaming_host myhost delete", ctx)
        assert "Not connected" in capsys.readouterr().out


class TestRoamingHostShow:
    async def test_show_all(self, capsys):
        def handler(request: httpx.Request) -> httpx.Response | None:
            if request.method == "GET" and "/roaminghost" in request.url.path:
                return httpx.Response(
                    200,
                    json=_list(
                        [
                            {
                                "_ref": "roaminghost/abc",
                                "name": "myhost",
                                "match_client": "MAC_ADDRESS",
                                "mac": "aa:bb:cc:dd:ee:ff",
                                "comment": "c1",
                            },
                        ]
                    ),
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show roaming_host", ctx)

        out = capsys.readouterr().out
        assert "myhost" in out
        assert "MAC_ADDRESS" in out

    async def test_show_named(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response | None:
            requests_seen.append(request)
            if request.method == "GET" and "/roaminghost" in request.url.path:
                return httpx.Response(
                    200, json=_list([{"_ref": "roaminghost/abc", "name": "myhost"}])
                )
            return None

        async with connected_ctx(handler) as ctx:
            await process_line("show roaming_host myhost", ctx)

        gets = [r for r in requests_seen if r.method == "GET" and "/roaminghost" in r.url.path]
        assert gets
        assert "myhost" in str(gets[-1].url)

    async def test_show_not_connected(self, capsys):
        ctx = Context()
        await process_line("show roaming_host", ctx)
        assert "Not connected" in capsys.readouterr().out
