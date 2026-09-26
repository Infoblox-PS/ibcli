# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Tests for ibcli.commands.system - async SDK style."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from ibcli.commands import system  # noqa: F401  - triggers registration
from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _register_null():
    """Seed the NULL root entry so the parser resolves top-level words."""
    COMMANDS.setdefault(
        "NULL",
        CommandEntry(
            words="help quit bye exit history configure show upload download restart test generate"
        ),
    )


@asynccontextmanager
async def connected_ctx(handler=None):
    async with make_client(handler) as client:
        yield Context(client=client, online=True, host="grid.test", client_rev="2.14")


async def test_help_command_prints_tips(capsys):
    await process_line("help", Context())
    out = capsys.readouterr().out
    assert "tab" in out.lower()


async def test_quit_raises_system_exit():
    with pytest.raises(SystemExit):
        await process_line("quit", Context())


async def test_bye_and_exit_are_aliases():
    for cmd in ("bye", "exit"):
        with pytest.raises(SystemExit):
            await process_line(cmd, Context())


async def test_show_time_prints_current_time(capsys):
    await process_line("show time", Context())
    out = capsys.readouterr().out
    assert ":" in out


async def test_show_debug_pwd_prints_cwd(capsys):
    await process_line("show debug pwd", Context())
    out = capsys.readouterr().out
    assert "/" in out


async def test_show_debug_file_not_connected(capsys):
    await process_line("show debug file", Context())
    out = capsys.readouterr().out
    assert "Not connected" in out


async def test_show_debug_file_with_session(capsys):
    async with connected_ctx() as ctx:
        await process_line("show debug file", ctx)
    out = capsys.readouterr().out
    assert "host=grid.test" in out
    assert "version=2.14" in out
    assert "base_url" in out


async def test_show_debug_session_not_connected(capsys):
    await process_line("show debug session", Context())
    out = capsys.readouterr().out
    assert "Not connected" in out


async def test_show_debug_session_with_session(capsys):
    async with connected_ctx() as ctx:
        await process_line("show debug session", ctx)
    out = capsys.readouterr().out
    assert "host=grid.test" in out
