# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

from __future__ import annotations

import logging
import sys

from ibcli.context import Context

# Level convention (matches the Perl ibcli's -d):
#   1 = top-level command trace
#   2 = HTTP method + URL + response status
#   3 = SDK request detail (params, retries, re-login)
#   4-5 = parser word-expansion internals
_HTTP_LEVEL = 2
_SDK_LEVEL = 3

_LOGGERS_CONFIGURED = False


def debug_cli(ctx: Context, level: int, msg: str) -> None:
    """Print `msg` to stderr when ctx.debug_level >= level."""
    if ctx.debug_level >= level:
        print(f"[d{level}] {msg}", file=sys.stderr)


class _Formatter(logging.Formatter):
    """Tag library log lines so they read like the rest of the -d output."""

    def __init__(self, level: int) -> None:
        super().__init__(f"[d{level}] %(message)s")


def configure_logging(debug_level: int) -> None:
    """Route httpx / SDK logging to stderr according to `debug_level`.

    Neither `httpx` nor `ibx_nios_sdk` emits anything unless its logger is
    configured, so `-d` was previously inert for HTTP: the flag set
    `ctx.debug_level` and nothing read it. `-d 2` turns on httpx's one-line
    request log (method, URL, status); `-d 3` adds the SDK's own DEBUG
    records, which include WAPI params, retry decisions and 401 re-logins.

    Called once from `cli.main`. Safe to call again - handlers are not
    stacked.
    """
    global _LOGGERS_CONFIGURED
    if debug_level < _HTTP_LEVEL or _LOGGERS_CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter(_HTTP_LEVEL))

    # httpx logs "HTTP Request: GET https://... 200 OK" at INFO.
    httpx_log = logging.getLogger("httpx")
    httpx_log.setLevel(logging.INFO)
    httpx_log.addHandler(handler)
    httpx_log.propagate = False

    if debug_level >= _SDK_LEVEL:
        sdk_handler = logging.StreamHandler(sys.stderr)
        sdk_handler.setFormatter(_Formatter(_SDK_LEVEL))
        sdk_log = logging.getLogger("ibx_nios_sdk")
        sdk_log.setLevel(logging.DEBUG)
        sdk_log.addHandler(sdk_handler)
        sdk_log.propagate = False

    _LOGGERS_CONFIGURED = True
