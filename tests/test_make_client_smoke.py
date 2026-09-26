# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import httpx

from tests.conftest import json_response, make_client


async def test_make_client_session_fallback():
    async with make_client() as client:
        # Fallback transport answers /grid/session; this just proves the
        # client opens and closes cleanly against it.
        assert client is not None


async def test_make_client_custom_handler_sees_request():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        # Return a response for any /wapi/* endpoint to allow the client to proceed
        if "/wapi/" in request.url.path:
            return json_response([])
        return None  # delegate to default handler

    async with make_client(handler) as client:
        # Make a request to trigger login
        async for _ in client.grid.grid.list():
            break  # Just iterate once to trigger the request

    # Login should have made a request to /?_schema=1, grid.grid list, and logout
    paths = [str(r.url) for r in seen]
    assert len(seen) >= 2  # At least login and grid.grid request
    assert any("_schema=1" in p for p in paths)
