# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Real-grid integration test fixtures.

Tests in this directory are auto-marked `real_grid` and skipped unless all
of IBCLI_TEST_GRID, IBCLI_TEST_USER, IBCLI_TEST_PASS env vars are set.

Run with:  IBCLI_TEST_GRID=192.0.2.40 IBCLI_TEST_USER=admin \\
           IBCLI_TEST_PASS='<password>' pytest tests/integration -v
"""

import os

import pytest
import pytest_asyncio
from ibx_nios_sdk import NiosClient

from ibcli.context import Context


def pytest_collection_modifyitems(config, items):
    """Auto-mark every test in tests/integration/ as real_grid."""
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.real_grid)


@pytest.fixture(scope="session")
def grid_credentials():
    host = os.environ.get("IBCLI_TEST_GRID")
    user = os.environ.get("IBCLI_TEST_USER")
    password = os.environ.get("IBCLI_TEST_PASS")
    if not (host and user and password):
        pytest.skip(
            "Set IBCLI_TEST_GRID / IBCLI_TEST_USER / IBCLI_TEST_PASS to run "
            "real-grid integration tests."
        )
    return {"host": host, "user": user, "password": password}


@pytest_asyncio.fixture
async def grid_ctx(grid_credentials):
    """Fresh NiosClient + Context per test."""
    async with NiosClient(
        grid_url=f"https://{grid_credentials['host']}",
        username=grid_credentials["user"],
        password=grid_credentials["password"],
        verify=False,
    ) as client:
        ctx = Context(client=client, online=True, host=grid_credentials["host"])
        yield ctx


@pytest.fixture
def test_prefix():
    """Unique prefix for this test run's resources - helps cleanup and
    avoids collisions across parallel runs."""
    import uuid

    return f"ibcliit-{uuid.uuid4().hex[:8]}"
