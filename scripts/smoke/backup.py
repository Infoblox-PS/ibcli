#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Pull a full NIOS grid backup before a smoke build.

NIOS exposes backup via the fileop RPC in two stages: a ``getgriddata``
call returning a download token + download URL, then a GET of that URL.
This script handles both and writes the ``.bak`` to disk.

Usage:
    scripts/smoke/backup.py --host GRID --user USER --password PASS \\
        [--out /tmp/grid-$(date +%Y%m%d-%H%M%S).bak]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _curl(args: list[str]) -> bytes:
    try:
        return subprocess.check_output(args, stderr=subprocess.PIPE, timeout=600)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(e.stderr.decode(errors="replace"))
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--wapi-version", default="2.14")
    args = ap.parse_args()

    out = args.out or f"/tmp/nios-backup-{datetime.utcnow():%Y%m%d-%H%M%S}.bak"

    base = f"https://{args.host}/wapi/v{args.wapi_version}"
    auth = f"{args.user}:{args.password}"

    # Stage 1 - request a backup; response carries a token + URL.
    print(f"[backup] requesting backup from {args.host} ...", flush=True)
    body = _curl(
        [
            "curl",
            "-sk",
            "-u",
            auth,
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"type": "BACKUP"}',
            f"{base}/fileop?_function=getgriddata",
        ]
    )
    data = json.loads(body)
    token = data.get("token")
    url = data.get("url")
    if not token or not url:
        sys.stderr.write(f"error: unexpected fileop response: {body!r}\n")
        return 2

    # Stage 2 - download via the supplied URL (HTTPS to the same grid).
    print(f"[backup] downloading → {out}", flush=True)
    _curl(
        [
            "curl",
            "-sk",
            "-u",
            auth,
            "-o",
            out,
            url,
        ]
    )

    size = Path(out).stat().st_size
    if size < 4096:
        sys.stderr.write(f"warning: backup file is only {size} bytes - verify manually\n")

    # Stage 3 - release the server-side token (required, per NIOS docs).
    _curl(
        [
            "curl",
            "-sk",
            "-u",
            auth,
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"token": token}),
            f"{base}/fileop?_function=downloadcomplete",
        ]
    )

    print(f"[backup] done - {size:,} bytes at {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
