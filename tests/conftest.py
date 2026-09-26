# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from ibx_nios_sdk import NiosClient

# `tests/integration/` hits a real grid and is opt-in via env vars - see
# tests/integration/conftest.py for how it's gated.
collect_ignore = [
    "integration",
]


Handler = Callable[[httpx.Request], httpx.Response | None]


def _default_session_handler(request: httpx.Request) -> httpx.Response:
    """Fallback transport: answers login probes and /grid/session, 501s everything else.

    The SDK logs in via ``GET /?_schema=1`` on first use (session cookie mode).
    We return a minimal 200 for that probe so tests don't get a login failure
    unless the test handler itself returns an error for that path.
    """
    # SDK login probe - must return 200 with a Set-Cookie to mark login success.
    # The SDK sends GET /wapi/v2.14/?_schema=1 on first use (session cookie mode).
    if b"_schema=1" in request.url.query:
        return httpx.Response(
            200,
            json={"supported_versions": ["2.14"]},
            headers={"Set-Cookie": "ibapauth=test-cookie; Path=/"},
        )
    if request.url.path.endswith("/grid/session"):
        return httpx.Response(
            200,
            json=[],
            headers={"Set-Cookie": "ibapauth=test-cookie; Path=/"},
        )
    return httpx.Response(
        501,
        json={"Error": f"Unhandled {request.method} {request.url.path}"},
    )


def make_client(handler: Handler | None = None, **overrides: Any) -> NiosClient:
    """Build a NiosClient wired to an httpx.MockTransport.

    Tests register a sync handler that inspects the request and returns an
    httpx.Response (or None to delegate to the default /grid/session handler).
    """

    def dispatch(request: httpx.Request) -> httpx.Response:
        if handler is not None:
            resp = handler(request)
            if resp is not None:
                return resp
        return _default_session_handler(request)

    transport = httpx.MockTransport(dispatch)
    kwargs: dict[str, Any] = {
        "grid_url": "https://grid.test",
        "username": "admin",
        "password": "secret",
        "wapi_version": "2.14",
        "_transport": transport,
    }
    kwargs.update(overrides)
    return NiosClient(**kwargs)


def json_response(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


@pytest.fixture
def make_client_fixture():
    return make_client


@pytest.fixture
async def client():
    """A NiosClient with the default 501-fallback transport; good for tests
    that only care about connect/disconnect."""
    async with make_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_commands_registry():
    try:
        from ibcli.registry import COMMANDS
    except ImportError:
        # registry hasn't been implemented yet (Task 3); no state to reset
        yield
        return
    snapshot = dict(COMMANDS)
    yield
    COMMANDS.clear()
    COMMANDS.update(snapshot)
