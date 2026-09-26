# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from ibcli.context import Context


async def test_context_defaults():
    ctx = Context()
    assert ctx.client is None
    assert ctx.online is False
    assert ctx.prompt == "server ? > "
    assert ctx.debug_level == 0


async def test_context_connect_sets_client(monkeypatch):
    from tests.conftest import make_client

    captured = {}

    class _Wrapper:
        def __init__(self, **kw):
            captured.update(kw)
            self._inner = make_client()

        async def __aenter__(self):
            return await self._inner.__aenter__()

        async def __aexit__(self, *a):
            return await self._inner.__aexit__(*a)

    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Wrapper)

    ctx = Context(debug_level=0)
    async with ctx.connect(
        host="grid.test", user="admin", password="secret", verify=True, wapi_version="2.14"
    ) as live:
        assert live.client is not None
        assert live.online is True
    assert captured["grid_url"] == "https://grid.test"
    assert captured["username"] == "admin"
    assert captured["wapi_version"] == "2.14"


async def test_connect_defaults_to_context_connection_options(monkeypatch):
    """`connect()` must build the same client `configure server` does -
    otherwise --timeout / --allow-restricted apply on one path only."""
    from tests.conftest import make_client

    captured = {}

    class _Wrapper:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self._inner = make_client()

        async def __aenter__(self):
            return await self._inner.__aenter__()

        async def __aexit__(self, *a):
            return await self._inner.__aexit__(*a)

    monkeypatch.setattr("ibx_nios_sdk.NiosClient", _Wrapper)

    ctx = Context(verify=False, wapi_version="2.13", timeout=90.0, enforce_restrictions=False)
    async with ctx.connect(host="grid.test", user="admin", password="secret"):
        pass

    assert captured["verify"] is False
    assert captured["wapi_version"] == "2.13"
    assert captured["timeout"] == 90.0
    assert captured["enforce_restrictions"] is False
