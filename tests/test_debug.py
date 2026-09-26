# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import logging

import pytest

from ibcli import debug as debug_mod
from ibcli.context import Context
from ibcli.debug import debug_cli


def test_debug_cli_prints_when_level_matches(capsys):
    ctx = Context(debug_level=3)
    debug_cli(ctx, 2, "hello")
    assert "[d2] hello" in capsys.readouterr().err


def test_debug_cli_silent_when_level_below(capsys):
    ctx = Context(debug_level=1)
    debug_cli(ctx, 3, "quiet")
    assert capsys.readouterr().err == ""


def test_debug_cli_default_level_zero_silent(capsys):
    debug_cli(Context(), 1, "quiet")
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# configure_logging
#
# `-d` used to set ctx.debug_level and nothing more: no HTTP tracing existed,
# despite the flag being documented as printing method/URL at level 2 and
# request detail at level 3. These pin the wiring that makes it real.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_logging():
    """configure_logging is idempotent by design; undo it between tests."""
    yield
    debug_mod._LOGGERS_CONFIGURED = False
    for name in ("httpx", "ibx_nios_sdk"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.setLevel(logging.NOTSET)
        lg.propagate = True


def test_configure_logging_noop_below_level_2():
    debug_mod.configure_logging(1)
    assert not logging.getLogger("httpx").handlers
    assert not logging.getLogger("ibx_nios_sdk").handlers


def test_configure_logging_level_2_enables_httpx_only():
    debug_mod.configure_logging(2)
    assert logging.getLogger("httpx").handlers
    assert logging.getLogger("httpx").level == logging.INFO
    # The SDK's own DEBUG records are level-3 detail, not level 2.
    assert not logging.getLogger("ibx_nios_sdk").handlers


def test_configure_logging_level_3_enables_sdk_too():
    debug_mod.configure_logging(3)
    assert logging.getLogger("httpx").handlers
    sdk = logging.getLogger("ibx_nios_sdk")
    assert sdk.handlers
    assert sdk.level == logging.DEBUG


def test_configure_logging_does_not_stack_handlers():
    debug_mod.configure_logging(3)
    before = len(logging.getLogger("httpx").handlers)
    debug_mod.configure_logging(3)
    assert len(logging.getLogger("httpx").handlers) == before


def test_configured_logger_writes_tagged_line_to_stderr(capsys):
    debug_mod.configure_logging(2)
    logging.getLogger("httpx").info("HTTP Request: GET https://grid/x 200 OK")
    err = capsys.readouterr().err
    assert "[d2] HTTP Request: GET https://grid/x 200 OK" in err
