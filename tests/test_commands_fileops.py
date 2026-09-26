# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for upload/download fileop commands - async SDK style."""

from __future__ import annotations

import json
import types
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
    COMMANDS.setdefault("NULL", CommandEntry(words="upload download show"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# Not-connected guard (all commands print "Not connected" with no client)
# ---------------------------------------------------------------------------

_ALL_COMMANDS = [
    # upload
    "upload csv myfile.csv",
    "upload csv myfile.csv object network",
    "upload leases leases.txt",
    "upload database backup.tar.gz",
    "upload expert_dhcp_conf dhcp.conf",
    "upload expert_dhcp_conf dhcp.conf member 192.168.1.1",
    # download
    "download csv out.csv object network",
    "download database backup.tar.gz",
    "download log_files logs.tar.gz syslog",
    "download log_files logs.tar.gz syslog member 192.168.1.1",
    "download lease_history leases.csv",
    "download support_bundle bundle.tar.gz",
    "download support_bundle bundle.tar.gz member 192.168.1.1",
    "download merge_log merge.log",
    "download expert_dhcp_conf dhcp.conf member infoblox.localdomain",
    "download dhcp_conf dhcp.conf member infoblox.localdomain",
    "download dns_conf dns.conf member infoblox.localdomain",
    "download dns_cache dns.cache member infoblox.localdomain",
]


@pytest.mark.parametrize("cmd", _ALL_COMMANDS)
async def test_no_client_prints_not_connected(cmd, capsys):
    ctx = Context()  # client is None
    await process_line(cmd, ctx)
    out = capsys.readouterr().out
    assert "Not connected" in out, f"Command {cmd!r} did not print 'Not connected'; got: {out!r}"


@pytest.mark.parametrize("cmd", _ALL_COMMANDS)
def test_command_is_registered(cmd):
    """Verify that the first token of every command is registered."""
    first_word = cmd.split()[0]
    matches = [k for k in COMMANDS if k == first_word or k.startswith(first_word + " ")]
    assert matches, (
        f"No COMMANDS entry found starting with {first_word!r}; "
        f"available top-level keys: {[k for k in sorted(COMMANDS) if ' ' not in k]}"
    )


# ---------------------------------------------------------------------------
# Helper: build a handler for the 3-step download protocol
# ---------------------------------------------------------------------------

_DL_URL = "https://grid.test/http_direct_file_io/req_id-D/file"
_UL_URL = "https://grid.test/http_direct_file_io/req_id-U/upload"
_TOKEN = "tok-abc"


def _make_download_handler(
    function: str,
    file_content: bytes = b"fake-file-content",
    extra_checks=None,
):
    """Return an httpx handler that implements the 3-step download protocol."""
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        if request.method == "POST" and "/fileop" in path and qs.get("_function") == function:
            return httpx.Response(200, json={"url": _DL_URL, "token": _TOKEN})
        if request.method == "GET" and "/http_direct_file_io" in path:
            return httpx.Response(200, content=file_content)
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    handler.requests_seen = requests_seen
    return handler


def _make_upload_handler(final_function: str):
    """Return an httpx handler that implements the 3-step upload protocol."""
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        if request.method == "POST" and "/fileop" in path and qs.get("_function") == "uploadinit":
            return httpx.Response(200, json={"url": _UL_URL, "token": _TOKEN})
        if request.method == "POST" and "/http_direct_file_io" in path:
            return httpx.Response(200, json={})
        if request.method == "POST" and "/fileop" in path and qs.get("_function") == final_function:
            return httpx.Response(200, json={})
        return None

    handler.requests_seen = requests_seen
    return handler


# ===========================================================================
# Download handler tests
# ===========================================================================


async def test_download_database(tmp_path, capsys):
    dest = tmp_path / "backup.tar.gz"
    handler = _make_download_handler("getgriddata")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download database {dest}", ctx)

    out = capsys.readouterr().out
    assert "Downloaded" in out
    assert dest.read_bytes() == b"fake-file-content"

    # Verify correct function and params
    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "getgriddata"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body == {"type": "BACKUP"}

    # Verify downloadcomplete was called with the token
    complete_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "downloadcomplete"
    ]
    assert len(complete_reqs) == 1
    assert json.loads(complete_reqs[0].content) == {"token": _TOKEN}


async def test_download_csv(tmp_path):
    dest = tmp_path / "out.csv"
    handler = _make_download_handler("csv_export")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download csv {dest} object network", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_export"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("_object") == "network"


async def test_download_csv_snapshot(tmp_path):
    dest = tmp_path / "snap.csv"
    handler = _make_download_handler("csv_snapshot_file")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download csv_snapshot {dest} token=abc123", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_snapshot_file"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("token") == "abc123"


async def test_download_log_files_no_member(tmp_path):
    dest = tmp_path / "logs.tar.gz"
    handler = _make_download_handler("get_log_files")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download log_files {dest} syslog", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "get_log_files"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("log_type") == "syslog"
    assert "member" not in body


async def test_download_log_files_with_member(tmp_path):
    dest = tmp_path / "logs.tar.gz"
    handler = _make_download_handler("get_log_files")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download log_files {dest} syslog member 10.0.0.1", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "get_log_files"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("log_type") == "syslog"
    assert body.get("member") == "10.0.0.1"


async def test_download_lease_history(tmp_path):
    dest = tmp_path / "leases.csv"
    handler = _make_download_handler("getleasehistoryfiles")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download lease_history {dest}", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "getleasehistoryfiles"
    ]
    assert len(init_reqs) == 1


async def test_download_support_bundle_no_member(tmp_path):
    dest = tmp_path / "bundle.tar.gz"
    handler = _make_download_handler("get_support_bundle")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download support_bundle {dest}", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "get_support_bundle"
    ]
    assert len(init_reqs) == 1
    content = init_reqs[0].content
    body = json.loads(content) if content else {}
    assert "member" not in body


async def test_download_support_bundle_with_member(tmp_path):
    dest = tmp_path / "bundle.tar.gz"
    handler = _make_download_handler("get_support_bundle")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download support_bundle {dest} member 10.0.0.1", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "get_support_bundle"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("member") == "10.0.0.1"


async def test_download_merge_log(tmp_path):
    dest = tmp_path / "merge.log"
    handler = _make_download_handler("get_log_files")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download merge_log {dest}", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "get_log_files"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("log_type") == "MERGE"


@pytest.mark.parametrize(
    "alias,wapi_type",
    [
        ("expert_dhcp_conf", "DHCP_EXPERT_MODE_CFG"),
        ("dhcp_conf", "DHCP_CFG"),
        ("dhcpv6_conf", "DHCPV6_CFG"),
        ("dns_conf", "DNS_CFG"),
        ("dns_cache", "DNS_CACHE"),
        ("dns_accel_cache", "DNS_ACCEL_CACHE"),
        ("dns_recursing_cache", "DNS_RECURSING_CACHE"),
        ("dns_stats", "DNS_STATS"),
        ("ntp_keys", "NTP_KEY_FILE"),
        ("radius_conf", "RADIUS_CFG"),
        ("traffic_capture", "TRAFFIC_CAPTURE_FILE"),
    ],
)
async def test_download_memberdata_variants(tmp_path, alias, wapi_type):
    dest = tmp_path / f"{alias}.out"
    handler = _make_download_handler("getmemberdata")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download {alias} {dest} member infoblox.localdomain", ctx)

    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "getmemberdata"
    ]
    assert len(init_reqs) == 1
    body = json.loads(init_reqs[0].content)
    assert body.get("type") == wapi_type
    assert body.get("member") == "infoblox.localdomain"


async def test_download_memberdata_requires_member(tmp_path, capsys):
    """Bare `download dns_conf <file>` is incomplete - the grammar requires member."""
    dest = tmp_path / "out"
    handler = _make_download_handler("getmemberdata")

    async with connected_ctx(handler) as ctx:
        await process_line(f"download dns_conf {dest}", ctx)

    out = capsys.readouterr().out
    assert "Incomplete" in out
    assert "member" in out


# ===========================================================================
# Upload handler tests
# ===========================================================================


async def test_upload_database(tmp_path, capsys):
    src = tmp_path / "backup.tar.gz"
    src.write_bytes(b"backup-data")
    handler = _make_upload_handler("restoredatabase")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload database {src}", ctx)

    out = capsys.readouterr().out
    assert "Uploaded" in out

    # Verify uploadinit was called
    init_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "uploadinit"
    ]
    assert len(init_reqs) == 1

    # Verify multipart POST carried the file bytes
    put_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST" and "/http_direct_file_io" in r.url.path
    ]
    assert len(put_reqs) == 1
    ct = put_reqs[0].headers.get("content-type", "")
    assert ct.startswith("multipart/form-data")
    assert b"backup-data" in put_reqs[0].content
    assert b'name="file"' in put_reqs[0].content

    # Verify restoredatabase was called with token and keep_grid_ip
    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "restoredatabase"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["token"] == _TOKEN
    assert body["keep_grid_ip"] == "YES"


async def test_upload_csv_no_object(tmp_path):
    src = tmp_path / "data.csv"
    src.write_bytes(b"col1,col2\nval1,val2")
    handler = _make_upload_handler("csv_import")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload csv {src}", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_import"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["token"] == _TOKEN
    # WAPI splits commit-mode from how-to-apply: action=START|TEST selects
    # commit vs. dry-run, operation=INSERT|OVERRIDE|... selects row semantics.
    assert body["action"] == "START"
    assert body["operation"] == "INSERT"
    assert body["on_error"] == "STOP"
    assert "_object" not in body

    # The multipart POST must carry HTTP Basic auth - Apache's
    # /http_direct_file_io endpoint does not honour the session cookie.
    put_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST" and "/http_direct_file_io" in r.url.path
    ]
    assert len(put_reqs) == 1
    assert put_reqs[0].headers.get("authorization", "").lower().startswith("basic ")


async def test_upload_csv_with_object(tmp_path):
    src = tmp_path / "data.csv"
    src.write_bytes(b"col1,col2\nval1,val2")
    handler = _make_upload_handler("csv_import")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload csv {src} object network", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_import"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["action"] == "START"
    assert body["operation"] == "CUSTOM"
    assert body["_object"] == "network"


async def test_upload_csv_mode_test(tmp_path):
    """mode=TEST → dry-run (action=TEST) while keeping operation semantics."""
    src = tmp_path / "data.csv"
    src.write_bytes(b"col1,col2\nval1,val2")
    handler = _make_upload_handler("csv_import")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload csv {src} mode=TEST operation=OVERRIDE", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "csv_import"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["action"] == "TEST"
    assert body["operation"] == "OVERRIDE"


async def test_upload_leases(tmp_path):
    src = tmp_path / "leases.txt"
    src.write_bytes(b"lease data")
    handler = _make_upload_handler("setleasehistoryfiles")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload leases {src}", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "setleasehistoryfiles"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["token"] == _TOKEN


async def test_upload_expert_dhcp_conf_no_member(tmp_path):
    src = tmp_path / "dhcp.conf"
    src.write_bytes(b"dhcp config")
    handler = _make_upload_handler("setmemberdata")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload expert_dhcp_conf {src}", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "setmemberdata"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["type"] == "DHCP_EXPERT_MODE_CFG"
    assert "member" not in body


async def test_upload_expert_dhcp_conf_with_member(tmp_path):
    src = tmp_path / "dhcp.conf"
    src.write_bytes(b"dhcp config")
    handler = _make_upload_handler("setmemberdata")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload expert_dhcp_conf {src} member 10.0.0.1", ctx)

    op_reqs = [
        r
        for r in handler.requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "setmemberdata"
    ]
    assert len(op_reqs) == 1
    body = json.loads(op_reqs[0].content)
    assert body["type"] == "DHCP_EXPERT_MODE_CFG"
    assert body["member"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# http_direct_file_io transport requirements
#
# These lock in the two undocumented NIOS behaviours that the fileop protocol
# depends on. Both were verified against a real grid; neither is expressible
# through the SDK's public API, so they live in ibcli.fileop.
# ---------------------------------------------------------------------------


async def test_download_sends_force_download_content_type(tmp_path):
    """Apache returns 415 on the file-io GET without this Content-Type.

    See docs/reference/troubleshooting.md - the header is required and is not
    part of the documented WAPI fileop contract.
    """
    handler = _make_download_handler("getgriddata")
    dest = tmp_path / "backup.bak"

    async with connected_ctx(handler) as ctx:
        await process_line(f"download database {dest}", ctx)

    gets = [
        r
        for r in handler.requests_seen
        if r.method == "GET" and "/http_direct_file_io" in r.url.path
    ]
    assert len(gets) == 1
    assert gets[0].headers.get("content-type") == "application/force-download"
    assert dest.read_bytes() == b"fake-file-content"


async def test_upload_posts_multipart_not_raw_body(tmp_path):
    """The file-io endpoint needs a multipart POST, not a raw PUT body."""
    src = tmp_path / "data.csv"
    src.write_bytes(b"col1,col2\nval1,val2")
    handler = _make_upload_handler("csv_import")

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload csv {src}", ctx)

    xfers = [r for r in handler.requests_seen if "/http_direct_file_io" in r.url.path]
    assert len(xfers) == 1
    assert xfers[0].method == "POST"
    assert xfers[0].headers.get("content-type", "").startswith("multipart/form-data")


async def test_failed_download_leaves_no_partial_file(tmp_path):
    """A dead transfer must not leave a truncated file that looks complete.

    The bytes land in a sibling `.part` and are renamed in only on success,
    so a caller that finds `dest` can trust it.
    """
    from ibcli.fileop import stream_download

    dest = tmp_path / "backup.bak"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"Error": "grid exploded"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = types.SimpleNamespace(_http=types.SimpleNamespace(_client=transport))
        with pytest.raises(httpx.HTTPStatusError):
            await stream_download(client, "https://gm/http_direct_file_io?x=1", dest)

    assert not dest.exists()
    assert not (tmp_path / "backup.bak.part").exists()


async def test_successful_download_overwrites_existing_file(tmp_path):
    """The `.part` rename must still clobber a stale file at the destination,
    the way the direct-write version did."""
    from ibcli.fileop import stream_download

    dest = tmp_path / "backup.bak"
    dest.write_bytes(b"stale")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"fresh-content")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = types.SimpleNamespace(_http=types.SimpleNamespace(_client=transport))
        await stream_download(client, "https://gm/http_direct_file_io", dest)

    assert dest.read_bytes() == b"fresh-content"
    assert not (tmp_path / "backup.bak.part").exists()
