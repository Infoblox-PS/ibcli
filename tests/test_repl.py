# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import sys

from ibcli import cli


class _FakePromptSession:
    """Stand-in for prompt_toolkit.PromptSession for tests.

    Provides ``prompt_async`` (a coroutine) because ``_run_repl`` now uses
    ``await session.prompt_async()``.
    """

    def __init__(self, lines):
        self._lines = list(lines)

    async def prompt_async(self, **kwargs):
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


def test_repl_processes_lines_until_eof(monkeypatch, capsys):
    session = _FakePromptSession(["show time", "help", ""])
    monkeypatch.setattr(cli, "_make_prompt_session", lambda ctx, **kw: session)
    monkeypatch.setattr(sys, "argv", ["ibcli"])
    cli.main()
    out = capsys.readouterr().out
    assert ":" in out
    assert "tab" in out.lower()


def test_repl_prints_banner(monkeypatch, capsys):
    session = _FakePromptSession([])
    monkeypatch.setattr(cli, "_make_prompt_session", lambda ctx, **kw: session)
    monkeypatch.setattr(sys, "argv", ["ibcli"])
    cli.main()
    out = capsys.readouterr().out
    assert "Infoblox CLI" in out


def test_repl_handles_backslash_continuation_in_pasted_input(monkeypatch, capsys):
    """When prompt_toolkit delivers a line with embedded '\\\\\\n', dispatcher joins it."""
    from ibcli.registry import COMMANDS, CommandEntry, command

    captured = {}

    @command("xrepltest go")
    def _xrepltest_go(line, ctx):
        captured["line"] = line

    COMMANDS["NULL"] = CommandEntry(words="xrepltest")
    COMMANDS["xrepltest"] = CommandEntry(words="go")

    # Simulate paste-as-text: prompt returns a single string with '\' + newline.
    session = _FakePromptSession(["xrepltest \\\n    go"])
    monkeypatch.setattr(cli, "_make_prompt_session", lambda ctx, **kw: session)
    monkeypatch.setattr(sys, "argv", ["ibcli"])
    cli.main()
    # Dispatcher should have joined the continuation and dispatched correctly.
    assert captured.get("line") == "xrepltest go"
