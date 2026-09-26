# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for certificate management commands - async SDK style."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from ibcli.commands import cert  # noqa: F401 - registers handlers
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words.

    system.py (not yet converted) normally provides this. Register the minimal
    subset needed for cert commands so the parser resolves download, upload,
    and generate correctly.
    """
    COMMANDS.setdefault("NULL", CommandEntry(words="download upload generate"))


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test")


# ---------------------------------------------------------------------------
# Not-connected guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "download cert out.pem",
        "upload cert mycert.pem",
        "generate selfsigned cert ns1.lab.com www.lab.com",
        "generate csr ns1.lab.com server.lab.com",
    ],
)
async def test_cert_not_connected_prints_message(cmd, capsys):
    ctx = Context()
    await process_line(cmd, ctx)
    assert "Not connected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# download cert
# ---------------------------------------------------------------------------


async def test_download_cert_default_usage(capsys, tmp_path):
    dest = tmp_path / "cert.pem"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        # downloadcertificate fileop call
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcertificate"
        ):
            return httpx.Response(
                200,
                json={
                    "url": "https://grid.test/http_direct_file_io/req_id-X/cert.pem",
                    "token": "t1",
                },
            )
        # Actual file download
        if request.method == "GET" and "/http_direct_file_io" in path:
            return httpx.Response(200, content=b"CERT")
        # downloadcomplete acknowledgement
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"download cert {dest} member ns1.lab.com", ctx)

    out = capsys.readouterr().out
    assert "Downloaded" in out
    assert dest.read_bytes() == b"CERT"

    # Verify the fileop call carried the right parameters
    fileop_posts = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "downloadcertificate"
    ]
    assert len(fileop_posts) == 1
    body = json.loads(fileop_posts[0].content)
    assert body.get("certificate_usage") == "ADMIN"
    assert body.get("member") == "ns1.lab.com"


async def test_download_cert_custom_usage(capsys, tmp_path):
    dest = tmp_path / "cert.pem"
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcertificate"
        ):
            return httpx.Response(
                200,
                json={
                    "url": "https://grid.test/http_direct_file_io/req_id-Y/cert.pem",
                    "token": "t2",
                },
            )
        if request.method == "GET" and "/http_direct_file_io" in path:
            return httpx.Response(200, content=b"CERT")
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"download cert {dest} member ns1.lab.com usage EAP_CA", ctx)

    out = capsys.readouterr().out
    assert "Downloaded" in out

    fileop_posts = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "downloadcertificate"
    ]
    assert len(fileop_posts) == 1
    body = json.loads(fileop_posts[0].content)
    assert body.get("certificate_usage") == "EAP_CA"


# ---------------------------------------------------------------------------
# upload cert
# ---------------------------------------------------------------------------


async def test_upload_cert_default_usage(capsys, tmp_path):
    src = tmp_path / "mycert.pem"
    src.write_bytes(b"FAKECERT")
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        # uploadinit
        if request.method == "POST" and "/fileop" in path and qs.get("_function") == "uploadinit":
            return httpx.Response(
                200,
                json={
                    "url": "https://grid.test/http_direct_file_io/upload/a",
                    "token": "tok",
                },
            )
        # multipart POST of the cert bytes
        if request.method == "POST" and "/http_direct_file_io" in path:
            return httpx.Response(200, json={})
        # uploadcertificate
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "uploadcertificate"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(f"upload cert {src} member ns1.lab.com", ctx)

    out = capsys.readouterr().out
    assert "Uploaded" in out

    cert_reqs = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "uploadcertificate"
    ]
    assert len(cert_reqs) == 1
    body = json.loads(cert_reqs[0].content)
    assert body.get("certificate_usage") == "ADMIN"
    assert body.get("member") == "ns1.lab.com"
    assert body.get("token") == "tok"

    # The file bytes go up as a multipart/form-data POST carrying HTTP Basic
    # auth - Apache's /http_direct_file_io endpoint rejects a raw PUT body and
    # does not honour the session cookie.
    xfer_reqs = [r for r in requests_seen if "/http_direct_file_io" in r.url.path]
    assert len(xfer_reqs) == 1
    assert xfer_reqs[0].method == "POST"
    assert xfer_reqs[0].headers.get("content-type", "").startswith("multipart/form-data")
    assert xfer_reqs[0].headers.get("authorization", "").lower().startswith("basic ")
    assert b"FAKECERT" in xfer_reqs[0].content
    assert b'name="file"' in xfer_reqs[0].content


# ---------------------------------------------------------------------------
# generate selfsigned cert
# ---------------------------------------------------------------------------


async def test_generate_selfsigned_cert(capsys, tmp_path, monkeypatch):
    # Monkeypatch open so the generated file is written to tmp_path
    orig_open = open
    generated_path = tmp_path / "www.lab.com.pem"

    def patched_open(path, mode="r", **kwargs):
        if path == "www.lab.com.pem" and "w" in mode:
            return orig_open(str(generated_path), mode, **kwargs)
        return orig_open(path, mode, **kwargs)

    monkeypatch.setattr("builtins.open", patched_open)

    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "generateselfsignedcert"
        ):
            return httpx.Response(
                200,
                json={
                    "url": "https://grid.test/http_direct_file_io/req_id-Z/ss.pem",
                    "token": "t3",
                },
            )
        if request.method == "GET" and "/http_direct_file_io" in path:
            return httpx.Response(200, content=b"SSCERT")
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line(
            "generate selfsigned cert ns1.lab.com www.lab.com usage ADMIN days 365",
            ctx,
        )

    out = capsys.readouterr().out
    assert "Generated" in out

    gen_reqs = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "generateselfsignedcert"
    ]
    assert len(gen_reqs) == 1
    body = json.loads(gen_reqs[0].content)
    assert body["cn"] == "www.lab.com"
    assert body["member"] == "ns1.lab.com"
    assert body["certificate_usage"] == "ADMIN"


# ---------------------------------------------------------------------------
# generate csr
# ---------------------------------------------------------------------------


async def test_generate_csr(capsys, tmp_path, monkeypatch):
    orig_open = open
    generated_path = tmp_path / "server.lab.com.csr"

    def patched_open(path, mode="r", **kwargs):
        if path == "server.lab.com.csr" and "w" in mode:
            return orig_open(str(generated_path), mode, **kwargs)
        return orig_open(path, mode, **kwargs)

    monkeypatch.setattr("builtins.open", patched_open)

    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response | None:
        requests_seen.append(request)
        path = request.url.path
        qs = dict(request.url.params)
        if request.method == "POST" and "/fileop" in path and qs.get("_function") == "generatecsr":
            return httpx.Response(
                200,
                json={
                    "url": "https://grid.test/http_direct_file_io/req_id-W/csr.pem",
                    "token": "t4",
                },
            )
        if request.method == "GET" and "/http_direct_file_io" in path:
            return httpx.Response(200, content=b"CSRDATA")
        if (
            request.method == "POST"
            and "/fileop" in path
            and qs.get("_function") == "downloadcomplete"
        ):
            return httpx.Response(200, json={})
        return None

    async with connected_ctx(handler) as ctx:
        await process_line("generate csr ns1.lab.com server.lab.com usage ADMIN", ctx)

    out = capsys.readouterr().out
    assert "Generated CSR" in out

    gen_reqs = [
        r
        for r in requests_seen
        if r.method == "POST"
        and "/fileop" in r.url.path
        and r.url.params.get("_function") == "generatecsr"
    ]
    assert len(gen_reqs) == 1
    body = json.loads(gen_reqs[0].content)
    assert body["cn"] == "server.lab.com"
    assert body["member"] == "ns1.lab.com"


# ---------------------------------------------------------------------------
# Commands registered check
# ---------------------------------------------------------------------------


def test_cert_commands_registered():
    assert "download" in COMMANDS
    assert "upload" in COMMANDS
    assert "generate" in COMMANDS
