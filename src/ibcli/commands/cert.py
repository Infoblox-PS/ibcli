# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Certificate management commands.

Command shapes:

  download cert <file> [member <name>] [usage <name>]
  upload cert <file> [member <name>] [usage <name>]
  generate selfsigned cert <name> <name> [usage <name>] [days <num>]
  generate csr <name> <name> [usage <name>]

All certificate I/O is fileop-based (not CRUD) and lives in
``ctx.client.misc.fileop``:
  - download_certificate      -> fileop?_function=downloadcertificate
  - upload_certificate        -> uploadinit -> multipart POST -> uploadcertificate
  - generate_selfsigned_cert  -> fileop?_function=generateselfsignedcert
  - generate_csr              -> fileop?_function=generatecsr
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.fileop import multipart_upload, stream_download
from ibcli.registry import command, register

# ---------------------------------------------------------------------------
# Waypoints
# ---------------------------------------------------------------------------

register(
    "download",
    words="cert",
    help="Download a file (CSV export, support bundle, logs, backup) from NIOS.",
)
register("download cert", words="<file>", help="Download a certificate from a grid service.")
register("download cert <file>", words="<cr> member=<name>|usage=<name>")
register("download cert <file> member", words="<name>")
register("download cert <file> member <name>", words="<cr> usage=<name>")
register("download cert <file> member <name> usage", words="<name>")
register("download cert <file> member <name> usage <name>", words="<cr>")
register("download cert <file> usage", words="<name>")
register("download cert <file> usage <name>", words="<cr> member=<name>")

register(
    "upload",
    words="cert",
    help="Upload a file (CSV, database backup, leases, certificate) to NIOS.",
)
register("upload cert", words="<file>", help="Upload a certificate to a grid service.")
register("upload cert <file>", words="<cr> member=<name>|usage=<name>")
register("upload cert <file> member", words="<name>")
register("upload cert <file> member <name>", words="<cr> usage=<name>")
register("upload cert <file> member <name> usage", words="<name>")
register("upload cert <file> member <name> usage <name>", words="<cr>")
register("upload cert <file> usage", words="<name>")
register("upload cert <file> usage <name>", words="<cr> member=<name>")

register(
    "generate",
    words="selfsigned csr",
    help="Generate a certificate, CSR or self-signed cert on the grid.",
)
register(
    "generate selfsigned", words="cert", help="Generate a self-signed certificate on the grid."
)
register(
    "generate selfsigned cert", words="<name>", help="Generate a self-signed service certificate."
)
register("generate selfsigned cert <name>", words="<name>")
register(
    "generate selfsigned cert <name> <name>",
    words="<cr> usage=<name>|days=<num>",
)

register("generate csr", words="<name>", help="Generate a certificate signing request.")
register("generate csr <name>", words="<name>")
register(
    "generate csr <name> <name>",
    words="<cr> usage=<name>",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _arg(line: str, keyword: str) -> str | None:
    """Return the token following *keyword* in *line*, or None."""
    m = re.search(rf"\b{re.escape(keyword)}\s+(\S+)", line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# download cert <file> [member <name>] [usage <name>]
# ---------------------------------------------------------------------------


@command(
    "download cert <file>",
    words="<cr> member=<name>|usage=<name>",
    help="Download a certificate from a grid member.",
)
@command(
    "download cert <file> member <name>",
    words="<cr> usage=<name>",
    help="Download a certificate from a specific member.",
)
@command(
    "download cert <file> member <name> usage <name>",
    words="<cr>",
    help="Download a certificate with a specific usage type.",
)
@command(
    "download cert <file> usage <name>",
    words="<cr> member=<name>",
    help="Download a certificate with a specific usage type.",
)
async def cli_download_cert(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcert\s+(\S+)", line)
    if not m:
        print("  Error: destination file path required")
        return
    dest_path = m.group(1)

    member = _arg(line, "member")
    usage = _arg(line, "usage") or "ADMIN"

    kwargs: dict = {"certificate_usage": usage}
    if member:
        kwargs["member"] = member

    result = await ctx.client.misc.fileop.downloadcertificate(**kwargs)
    token = result.get("token")
    download_url = result.get("url")

    if not token or not download_url:
        print("  Error: downloadcertificate response missing token or url")
        return

    await stream_download(ctx.client, download_url, dest_path)

    await ctx.client.misc.fileop.download_complete(token=token)
    print(f"  Downloaded {dest_path}")


# ---------------------------------------------------------------------------
# upload cert <file> [member <name>] [usage <name>]
# ---------------------------------------------------------------------------


@command(
    "upload cert <file>",
    words="<cr> member=<name>|usage=<name>",
    help="Upload a certificate to a grid member.",
)
@command(
    "upload cert <file> member <name>",
    words="<cr> usage=<name>",
    help="Upload a certificate to a specific member.",
)
@command(
    "upload cert <file> member <name> usage <name>",
    words="<cr>",
    help="Upload a certificate with a specific usage type.",
)
@command(
    "upload cert <file> usage <name>",
    words="<cr> member=<name>",
    help="Upload a certificate with a specific usage type.",
)
async def cli_upload_cert(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bcert\s+(\S+)", line)
    if not m:
        print("  Error: source file path required")
        return
    source_path = m.group(1)

    member = _arg(line, "member") or ""
    usage = _arg(line, "usage") or "ADMIN"

    # Step 1: initiate upload session
    init_result = await ctx.client.misc.fileop.upload_init()
    token = init_result.get("token")
    upload_url = init_result.get("url")

    if not token or not upload_url:
        print("  Error: uploadinit response missing token or url")
        return

    # Step 2: POST the certificate bytes as multipart/form-data. The
    # http_direct_file_io endpoint rejects a raw body and does not honour the
    # session cookie - see ibcli.fileop for both requirements.
    await multipart_upload(ctx.client, upload_url, source_path)

    # Step 3: associate certificate with member/usage
    upload_kwargs: dict = {"token": token, "certificate_usage": usage}
    if member:
        upload_kwargs["member"] = member

    await ctx.client.misc.fileop.upload_certificate(**upload_kwargs)
    print(f"  Uploaded {source_path}")


# ---------------------------------------------------------------------------
# generate selfsigned cert <member> <cn> [usage <name>] [days <num>]
# ---------------------------------------------------------------------------


@command(
    "generate selfsigned cert <name> <name>",
    words="<cr> usage=<name>|days=<num>",
    help="Generate a self-signed certificate on a grid member.",
)
async def cli_generate_selfsigned(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bselfsigned cert\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: member and common_name required")
        return
    member, cn = m.group(1), m.group(2)

    usage = _arg(line, "usage") or "ADMIN"
    days_str = _arg(line, "days")
    days = 365
    if days_str is not None:
        try:
            days = int(days_str)
        except ValueError:
            print(f"  Error: days must be an integer, got: {days_str}")
            return

    payload: dict = {
        "cn": cn,
        "member": member,
        "certificate_usage": usage,
        "days_valid": days,
        "algorithm": "SHA-256",
        "key_size": 2048,
    }

    result = await ctx.client.misc.fileop.call("generateselfsignedcert", **payload)
    token = result.get("token")
    download_url = result.get("url")

    if not token or not download_url:
        print("  Error: generateselfsignedcert response missing token or url")
        return

    dest_path = f"{cn}.pem"
    await stream_download(ctx.client, download_url, dest_path)

    await ctx.client.misc.fileop.download_complete(token=token)
    print(f"  Generated self-signed certificate for {cn}")


# ---------------------------------------------------------------------------
# generate csr <member> <cn> [usage <name>]
# ---------------------------------------------------------------------------


@command(
    "generate csr <name> <name>",
    words="<cr> usage=<name>",
    help="Generate a Certificate Signing Request (CSR) on a grid member.",
)
async def cli_generate_csr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bgenerate csr\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: member and common_name required")
        return
    member, cn = m.group(1), m.group(2)

    usage = _arg(line, "usage") or "ADMIN"

    payload: dict = {
        "cn": cn,
        "member": member,
        "certificate_usage": usage,
        "algorithm": "SHA-256",
        "key_size": 2048,
    }

    result = await ctx.client.misc.fileop.call("generatecsr", **payload)
    token = result.get("token")
    download_url = result.get("url")

    if not token or not download_url:
        print("  Error: generatecsr response missing token or url")
        return

    dest_path = f"{cn}.csr"
    await stream_download(ctx.client, download_url, dest_path)

    await ctx.client.misc.fileop.download_complete(token=token)
    print(f"  Generated CSR for {cn}")
