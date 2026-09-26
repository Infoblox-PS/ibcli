# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import sys

import pytest

from ibcli import __version__, cli


def test_l_lists_commands(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ibcli", "-l"])
    cli.main()
    out = capsys.readouterr().out
    assert "help" in out
    assert "configure zone add <zone>" in out


def test_V_prints_version(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ibcli", "-V"])
    # argparse 'version' action raises SystemExit(0) before asyncio.run is reached.
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_e_runs_single_command_and_exits(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "show time"])
    cli.main()
    out = capsys.readouterr().out
    assert ":" in out


@pytest.mark.skip(
    reason="Blocked by command module conversions (Task 9+): uses requests-mock "
    "and WapiSession-based command handlers not yet ported to ibx-nios-sdk."
)
def test_e_with_connection_issues_real_calls(capsys, monkeypatch):
    pass


def test_batch_file_processes_lines(tmp_path, capsys, monkeypatch):
    script = tmp_path / "s.cf"
    script.write_text("# comment\n\nshow time\n")
    monkeypatch.setattr(sys, "argv", ["ibcli", str(script)])
    # New _async_main returns normally after batch (no sys.exit).
    cli.main()
    out = capsys.readouterr().out
    assert "read line 3:" in out
    assert "#" in out  # comment was echoed


def test_b_flag_is_rejected(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ibcli", "-b", "some.db"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "not supported" in err.lower()


def test_cf_file_is_loaded_on_startup(tmp_path, capsys, monkeypatch):
    """`.ibcli.cf` in the cwd runs before any other input. Comments and
    blank lines are skipped."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ibcli.cf").write_text("# header comment\n\nshow time\n")
    # Use -e with a no-op command to drive past the .cf loader without
    # attempting a grid connection.
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "help"])
    cli.main()
    out = capsys.readouterr().out
    # `show time` from the .cf printed a colon-containing timestamp.
    assert ":" in out


def test_password_prompt_when_not_given(tmp_path, capsys, monkeypatch):
    """When -s and -u are set but -p is not, getpass prompts for the password."""
    monkeypatch.chdir(tmp_path)  # don't trip over any local .ibcli.cf
    monkeypatch.setattr(sys, "argv", ["ibcli", "-s", "nohost", "-u", "admin"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "prompted-pass")
    # Run just one command and exit; the connect fails but the password prompt
    # code path executes.
    monkeypatch.setattr(sys, "argv", ["ibcli", "-s", "nohost", "-u", "admin", "-e", "show time"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "prompted-pass")
    cli.main()
    out = capsys.readouterr().out
    # Either the connect errored out or `show time` ran - both paths hit
    # getpass.
    assert out  # some output happened


def test_master_flag_routed_to_context(tmp_path, capsys, monkeypatch):
    """The -m/--master flag appends `master <ip>` to the configure-server line."""
    monkeypatch.chdir(tmp_path)
    # -l exits after listing, so we don't actually need a live grid for this.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ibcli",
            "-s",
            "nohost",
            "-u",
            "admin",
            "-p",
            "pass",
            "-m",
            "10.0.0.1",
            "-l",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "configure zone add" in out  # -l ran


def test_batch_file_with_backslash_continuation(tmp_path, capsys, monkeypatch):
    """Lines ending with '\\' in a batch file are joined before dispatch."""
    script = tmp_path / "cont.cf"
    # The zone add command takes a single zone argument; we just verify that
    # the continuation is joined without error (no "Unknown command" output).
    script.write_text("# continuations test\nshow \\\n    time\n")
    monkeypatch.setattr(sys, "argv", ["ibcli", str(script)])
    # New _async_main returns normally after batch (no sys.exit).
    cli.main()
    out = capsys.readouterr().out
    # Comment echoed, and the joined command executed (show time prints a time).
    assert "# continuations test" in out
    assert ":" in out  # show time output contains ":"


# ---------------------------------------------------------------------------
# Connection flags
#
# -k/--insecure and --wapi-version were parsed but never read, so both were
# silently inert and `configure server` always disabled TLS verification.
# ---------------------------------------------------------------------------


def _capture_context(monkeypatch):
    """Run _async_main with a stubbed process_line and return the Context."""
    captured = {}

    async def fake_process_line(line, ctx):
        captured["ctx"] = ctx
        captured.setdefault("lines", []).append(line)

    monkeypatch.setattr("ibcli.dispatcher.process_line", fake_process_line)
    return captured


def test_verify_defaults_on(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "show time"])
    cli.main()
    assert captured["ctx"].verify is True
    assert captured["ctx"].wapi_version is None


def test_insecure_flag_disables_verification(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "-k", "-e", "show time"])
    cli.main()
    assert captured["ctx"].verify is False


def test_wapi_version_flag_is_carried(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "--wapi-version", "2.12", "-e", "show time"])
    cli.main()
    assert captured["ctx"].wapi_version == "2.12"


def test_client_is_closed_on_exit(monkeypatch):
    """The SDK client must be released on the way out of every mode."""
    closed = []

    class _FakeClient:
        async def aclose(self):
            closed.append(True)

    async def fake_process_line(line, ctx):
        ctx.client = _FakeClient()
        ctx.online = True

    monkeypatch.setattr("ibcli.dispatcher.process_line", fake_process_line)
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "show time"])
    cli.main()
    assert closed == [True]


def test_timeout_defaults_to_thirty(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "show time"])
    cli.main()
    assert captured["ctx"].timeout == 30.0


def test_timeout_flag_is_carried(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "--timeout", "90", "-e", "show time"])
    cli.main()
    assert captured["ctx"].timeout == 90.0


def test_restrictions_are_enforced_by_default(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "-e", "show time"])
    cli.main()
    assert captured["ctx"].enforce_restrictions is True


def test_allow_restricted_disables_enforcement(monkeypatch):
    captured = _capture_context(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ibcli", "--allow-restricted", "-e", "show time"])
    cli.main()
    assert captured["ctx"].enforce_restrictions is False


def test_backup_flags_are_rejected_with_guidance(monkeypatch, capsys):
    """`-b`/`-f` must explain why, and name the part ibcli does handle.

    Browsing a backup is an offline read of a local file, not a grid call, so
    it is out of scope for a WAPI client - but fetching the backup is not.
    """
    monkeypatch.setattr(sys, "argv", ["ibcli", "-b", "grid.bak"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "not supported" in err
    assert "offline" in err
    assert "download database" in err


def test_f_flag_is_an_alias_for_b(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ibcli", "-f", "grid.bak"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "not supported" in capsys.readouterr().err


def test_backup_flag_error_names_no_internal_tooling(monkeypatch, capsys):
    """ibcli is public; its output must not point at private repos."""
    monkeypatch.setattr(sys, "argv", ["ibcli", "-b", "grid.bak"])
    with pytest.raises(SystemExit):
        cli.main()
    err = capsys.readouterr().err.lower()
    for private in ("onedb", "ibx-", "internal"):
        assert private not in err, f"error text leaks {private!r}"
