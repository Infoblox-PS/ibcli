# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for CSV task status and error log download commands - async SDK style."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import fileops  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
    COMMANDS.setdefault("NULL", CommandEntry(words="download show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# show csv task
# ---------------------------------------------------------------------------


async def test_show_csv_task_prints_status(capsys):
    ref = "csv_import_task/ZG5z:abc123"
    task_data = {
        "status": "COMPLETED",
        "lines_processed": 100,
        "lines_failed": 2,
        "start_time": "2024-01-01T00:00:00",
        "end_time": "2024-01-01T00:01:00",
    }

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and ref in request.url.path:
            return httpx.Response(200, json=task_data)
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"show csv task {ref}", ctx)

    out = capsys.readouterr().out
    assert "COMPLETED" in out
    assert "100" in out
    assert "2" in out


async def test_show_csv_task_not_connected(capsys):
    ctx = Context()
    await process_line("show csv task csv_import_task/ZG5z:abc123", ctx)
    assert "Not connected" in capsys.readouterr().out


async def test_show_csv_task_wapi_error(capsys):
    ref = "csv_import_task/ZG5z:bad"

    def handler(request: httpx.Request) -> httpx.Response | None:
        if request.method == "GET" and ref in request.url.path:
            return httpx.Response(
                404,
                json={"Error": "NotFound", "code": "Client.Ibap.NotFound", "text": "Not found"},
            )
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"show csv task {ref}", ctx)

    out = capsys.readouterr().out
    assert "Error" in out


# ---------------------------------------------------------------------------
# download csv_errors
# ---------------------------------------------------------------------------

_ERR_URL = "https://grid.test/http_direct_file_io/req_id-E/errors.csv"
_TOKEN = "te"


async def test_download_csv_errors(tmp_path, capsys):
    dest = tmp_path / "errors.csv"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        qs = dict(request.url.params)
        if (
            request.method == "POST"
            and "/fileop" in request.url.path
            and qs.get("_function") == "csv_error_log"
        ):
            return httpx.Response(200, json={"url": _ERR_URL, "token": _TOKEN})
        if request.method == "GET" and "/http_direct_file_io" in request.url.path:
            return httpx.Response(200, content=b"error_line,reason\n1,bad data")
        if (
            request.method == "POST"
            and "/fileop" in request.url.path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"download csv_errors {dest} job-123", ctx)

    out = capsys.readouterr().out
    assert "Downloaded" in out

    # Verify the fileop function and import_id in request body
    init_reqs = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_error_log"
    ]
    assert init_reqs, "csv_error_log POST not found"
    body = json.loads(init_reqs[0].content)
    assert body.get("import_id") == "job-123"

    # Verify file content written to disk
    assert b"error_line" in dest.read_bytes()


async def test_download_csv_errors_not_connected(capsys):
    ctx = Context()
    await process_line("download csv_errors out.csv job-123", ctx)
    assert "Not connected" in capsys.readouterr().out


def test_download_csv_errors_registered():
    assert "download csv_errors <file> <name>" in COMMANDS


def test_show_csv_task_registered():
    assert "show csv task <name>" in COMMANDS
