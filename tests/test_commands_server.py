# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.server - async SDK style."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import server  # noqa: F401  - registers handlers
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
        yield Context(client=client, online=True, host="grid.test", client_rev="2.14")


def _list(items):
    return {"result": items}


# ---------------------------------------------------------------------------
# configure server
# ---------------------------------------------------------------------------


async def test_configure_server_not_enough_args(capsys):
    ctx = Context()
    await process_line("configure server grid user admin", ctx)
    out = capsys.readouterr().out
    assert "required" in out
    assert ctx.client is None


async def test_configure_master_sets_ctx_master_ip():
    ctx = Context()
    await process_line("configure master 10.0.0.1", ctx)
    assert ctx.master_ip == "10.0.0.1"


# ---------------------------------------------------------------------------
# show server version
# ---------------------------------------------------------------------------


async def test_show_server_version_not_connected(capsys):
    ctx = Context()
    await process_line("show server version", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_show_server_version_prints(capsys):
    async with connected_ctx() as ctx:
        await process_line("show server version", ctx)
    out = capsys.readouterr().out
    assert "2.14" in out


# ---------------------------------------------------------------------------
# show grid
# ---------------------------------------------------------------------------


async def test_show_grid_not_connected(capsys):
    ctx = Context()
    await process_line("show grid", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_show_grid_queries_grid(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/grid" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {"_ref": "grid/b25lLmNsdXN0ZXIkMA:Infoblox", "name": "Infoblox"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show grid", ctx)

    out = capsys.readouterr().out
    assert "Infoblox" in out


# ---------------------------------------------------------------------------
# show views
# ---------------------------------------------------------------------------


async def test_show_views_not_connected(capsys):
    ctx = Context()
    await process_line("show views", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_show_views_lists_all(capsys):
    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and "/view" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {"_ref": "view/abc:default/true", "name": "default", "is_default": True},
                        {"_ref": "view/abc:internal/false", "name": "internal"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show views", ctx)

    out = capsys.readouterr().out
    assert "default" in out
    assert "(default)" in out
    assert "internal" in out


async def test_show_views_single(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        if request.method == "GET" and "/view" in request.url.path:
            return httpx.Response(
                200,
                json=_list(
                    [
                        {"_ref": "view/abc:external/false", "name": "external"},
                    ]
                ),
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("show views external", ctx)

    gets = [r for r in requests_seen if r.method == "GET" and "/view" in r.url.path]
    assert any("name=external" in str(r.url) for r in gets)
    assert "external" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# configure server - connection options
#
# `verify` used to be hardcoded to False here, which made -k/--insecure a
# no-op and silently disabled TLS verification for everyone. `wapi_version`
# was never passed at all.
# ---------------------------------------------------------------------------


class _Probe:
    """Minimal stand-in for the `client.grid.grid.list(...)` credential probe."""

    def __init__(self, owner):
        self._owner = owner

    def list(self, **kwargs):
        return self

    async def all(self):
        await self._owner._probe()
        return []


class _Recorder:
    """Stand-in for NiosClient that records how it was constructed."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _Recorder.last = self
        self.grid = type("_G", (), {"grid": _Probe(self)})()
        self._http = type("_H", (), {"_wapi_version": kwargs.get("wapi_version") or "2.14"})()

    async def _probe(self):
        return None

    async def aclose(self):
        return None


async def test_configure_server_honours_context_verify(monkeypatch):
    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Recorder)
    ctx = Context(verify=False)
    await process_line("configure server grid user admin password secret", ctx)
    assert _Recorder.last.kwargs["verify"] is False


async def test_configure_server_probes_credentials(monkeypatch):
    """Connecting must make an authenticated call, not just build a client."""
    probed = []

    class _Probing(_Recorder):
        async def _probe(self):
            probed.append(True)

    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Probing)
    ctx = Context()
    await process_line("configure server grid user admin password secret", ctx)
    assert probed == [True]
    assert ctx.online is True


async def test_configure_server_defaults_to_verifying_tls(monkeypatch):
    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Recorder)
    ctx = Context()  # verify defaults to True
    await process_line("configure server grid user admin password secret", ctx)
    assert _Recorder.last.kwargs["verify"] is True


async def test_configure_server_passes_wapi_version(monkeypatch):
    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Recorder)
    ctx = Context(wapi_version="2.12")
    await process_line("configure server grid user admin password secret", ctx)
    assert _Recorder.last.kwargs["wapi_version"] == "2.12"
    assert ctx.client_rev == "2.12"


async def test_configure_server_closes_client_on_login_failure(monkeypatch, capsys):
    closed = []

    class _Failing(_Recorder):
        async def _probe(self):
            raise RuntimeError("bad credentials")

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Failing)
    ctx = Context()
    await process_line("configure server grid user admin password wrong", ctx)

    assert "Error" in capsys.readouterr().out
    assert ctx.client is None
    assert ctx.online is False
    # A failed connect must not leak the httpx connection pool it opened.
    assert closed == [True]
