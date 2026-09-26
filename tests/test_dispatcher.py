# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import pytest

from ibcli.context import Context
from ibcli.dispatcher import process_line
from ibcli.registry import COMMANDS, CommandEntry, command


def _seed(root: str, sub: str) -> None:
    """Register a throwaway command without clobbering the shared NULL node.

    Assigning COMMANDS["NULL"] outright drops whatever other modules put
    there (`show`, `configure`, ...), which breaks unrelated tests depending
    on collection order.
    """
    from ibcli.registry import _merge_words  # type: ignore[attr-defined]

    null = COMMANDS.setdefault("NULL", CommandEntry(words=root))
    null.words = _merge_words(null.words or "", root)
    COMMANDS[root] = CommandEntry(words=sub)


async def test_process_line_dispatches_to_handler(capsys):
    called = {}

    @command("show time")
    def show_time(line, ctx):
        called["line"] = line

    COMMANDS["NULL"] = CommandEntry(words="show")
    COMMANDS["show"] = CommandEntry(words="time")
    await process_line("show time", Context())
    assert called["line"] == "show time"


async def test_process_line_applies_alias(capsys):
    called = {}

    @command("show file path")
    def show_path(line, ctx):
        called["line"] = line

    # "pwd" alias rewrites to "show debug pwd"
    COMMANDS["show"] = CommandEntry(words="debug")
    COMMANDS["show debug"] = CommandEntry(words="pwd")
    COMMANDS["show debug pwd"] = CommandEntry(func=show_path)
    COMMANDS["NULL"] = CommandEntry(words="show")
    await process_line("pwd", Context())
    assert called["line"] == "show debug pwd"


async def test_process_line_prints_incomplete(capsys):
    COMMANDS["NULL"] = CommandEntry(words="show")
    COMMANDS["show"] = CommandEntry(words="zone network")
    await process_line("show", Context())
    captured = capsys.readouterr()
    assert "Incomplete" in captured.out
    assert "zone" in captured.out and "network" in captured.out


async def test_process_line_prints_error(capsys):
    COMMANDS["NULL"] = CommandEntry(words="show")
    await process_line("bogus", Context())
    captured = capsys.readouterr()
    assert "Unknown" in captured.out


async def test_process_line_ignores_blank():
    await process_line("", Context())
    await process_line("   ", Context())
    # no exception, no stdout expected


async def test_process_line_strips_backslash_continuation(capsys):
    """'\\' + whitespace/newline mid-string is stripped, joining the fragments."""
    called = {}

    @command("xtestcont alpha")
    def _xtestcont_alpha(line, ctx):
        called["line"] = line

    COMMANDS["NULL"] = CommandEntry(words="xtestcont")
    COMMANDS["xtestcont"] = CommandEntry(words="alpha")

    # Simulate pasted multi-line input with backslash+newline continuation.
    await process_line("xtestcont \\\n   alpha", Context())
    assert called.get("line") == "xtestcont alpha"


async def test_process_line_handles_trailing_bare_backslash(capsys):
    """A trailing bare backslash is silently stripped so the command still works."""
    called = {}

    @command("xtesttrail beta")
    def _xtesttrail_beta(line, ctx):
        called["line"] = line

    COMMANDS["NULL"] = CommandEntry(words="xtesttrail")
    COMMANDS["xtesttrail"] = CommandEntry(words="beta")

    await process_line("xtesttrail beta\\", Context())
    assert called.get("line") == "xtesttrail beta"


async def test_process_line_catches_nios_error(capsys):
    from ibx_nios_sdk import NiosError

    @command("xtestnios do")
    async def _h(line, ctx):
        raise NiosError(message="simulated failure")

    COMMANDS["NULL"] = CommandEntry(words="xtestnios")
    COMMANDS["xtestnios"] = CommandEntry(words="do")

    await process_line("xtestnios do", Context())
    out = capsys.readouterr().out
    assert "Error" in out
    assert "simulated" in out


async def test_process_line_cleans_nios_wrapper(capsys):
    from ibx_nios_sdk import NiosError

    @command("xtestwrap do")
    async def _h(line, ctx):
        raise NiosError(
            message="AdmConDataError: None (IBDataConflictError: IB.Data.Conflict:Server 'web1' already exists)",
            wapi_text="IB.Data.Conflict:Server 'web1' already exists",
        )

    COMMANDS["NULL"] = CommandEntry(words="xtestwrap")
    COMMANDS["xtestwrap"] = CommandEntry(words="do")

    await process_line("xtestwrap do", Context())
    out = capsys.readouterr().out
    assert "AdmConDataError" not in out
    assert "Server 'web1' already exists" in out


async def test_process_line_mutating_verb_synthesizes_ok(capsys):
    """A mutating handler that prints nothing gets a synthesized 'OK' line."""

    @command("xtestok add")
    async def _h(line, ctx):
        pass  # silent handler

    COMMANDS["NULL"] = CommandEntry(words="xtestok")
    COMMANDS["xtestok"] = CommandEntry(words="add")

    await process_line("xtestok add", Context())
    out = capsys.readouterr().out
    assert "OK" in out


async def test_process_line_nios_wrapper_inner_unwrap(capsys):
    """The inner-wrap regex (e.g. 'FooError:bar: msg') is peeled."""
    from ibx_nios_sdk import NiosError

    @command("xtestinner do")
    async def _h(line, ctx):
        # No wapi_text, message matches _INNER_WRAP directly.
        raise NiosError(message="SomeError:mod.sub: inner-only message")

    COMMANDS["NULL"] = CommandEntry(words="xtestinner")
    COMMANDS["xtestinner"] = CommandEntry(words="do")

    await process_line("xtestinner do", Context())
    out = capsys.readouterr().out
    assert "inner-only message" in out


async def test_process_line_exists_signal_via_text(capsys):
    """Non-ConflictError NiosError with an 'already exists' text gets Skipped in idempotent mode."""
    from ibx_nios_sdk import NiosError

    @command("xtestexists do")
    async def _h(line, ctx):
        raise NiosError(
            message="AdmConDataError: thing already exists",
            wapi_text="thing already exists",
        )

    _seed("xtestexists", "do")

    await process_line("xtestexists do", Context(idempotent=True))
    out = capsys.readouterr().out
    assert "Skipped" in out


async def test_tee_proxies_attributes_and_flush(capsys):
    """The _Tee proxy forwards unknown attributes and flush() to both sinks."""
    import io

    from ibcli.dispatcher import _Tee

    a = io.StringIO()
    b = io.StringIO()
    t = _Tee(a, b)
    # write fan-out
    n = t.write("hello")
    assert n == 5
    assert a.getvalue() == "hello" and b.getvalue() == "hello"
    # flush fan-out (no error)
    t.flush()
    # __getattr__ forwards to first sink
    assert t.closed is False


async def test_process_line_idempotent_demotes_conflict(capsys):
    from ibx_nios_sdk._exceptions import ConflictError

    @command("xtestconf do")
    async def _h(line, ctx):
        raise ConflictError(
            status_code=409,
            message="AdmConDataError: None (IBDataConflictError: IB.Data.Conflict:Duplicate object 'x')",
            wapi_text="IB.Data.Conflict:Duplicate object 'x'",
        )

    COMMANDS["NULL"] = CommandEntry(words="xtestconf")
    COMMANDS["xtestconf"] = CommandEntry(words="do")

    ctx = Context(idempotent=True)
    await process_line("xtestconf do", ctx)
    out = capsys.readouterr().out
    assert "Skipped" in out
    assert "Duplicate object 'x'" in out
    assert "Error" not in out


# ---------------------------------------------------------------------------
# Last-resort exception handling
#
# A handler that raises something other than NiosError used to escape
# process_line entirely, printing a traceback and - in the REPL - killing the
# session loop on the next iteration.
# ---------------------------------------------------------------------------


async def test_process_line_catches_unexpected_exception(capsys):
    @command("xtestboom do")
    async def _h(line, ctx):
        raise ValueError("ref 'probe1' does not match wapi_type 'kerberoskey'")

    _seed("xtestboom", "do")

    await process_line("xtestboom do", Context())
    out = capsys.readouterr().out
    assert "Error: ValueError: ref 'probe1'" in out
    assert "Traceback" not in out


async def test_process_line_reraises_unexpected_exception_at_d3():
    """`-d 3` must still surface the traceback so bugs stay diagnosable."""
    import pytest

    @command("xtestboom2 do")
    async def _h(line, ctx):
        raise ValueError("boom")

    _seed("xtestboom2", "do")

    with pytest.raises(ValueError, match="boom"):
        await process_line("xtestboom2 do", Context(debug_level=3))


@pytest.mark.parametrize("level", [1, 2])
async def test_process_line_does_not_reraise_below_d3(level, capsys):
    """`-d 1`/`-d 2` are tracing levels, documented as not changing control
    flow. A handler bug there must still be a one-line error, not a dead
    REPL - see the `-d` table in docs/reference/cli-flags.md."""

    @command(f"xtestboom3{level} do")
    async def _h(line, ctx):
        raise ValueError("boom")

    _seed(f"xtestboom3{level}", "do")

    await process_line(f"xtestboom3{level} do", Context(debug_level=level))
    out = capsys.readouterr().out
    assert "Error: ValueError: boom" in out
    assert "Traceback" not in out


async def test_process_line_lets_systemexit_through():
    """`exit`/`quit` raise SystemExit by design - the net must not swallow it."""
    import pytest

    @command("xtestquit do")
    async def _h(line, ctx):
        raise SystemExit(0)

    COMMANDS["NULL"] = CommandEntry(words="xtestquit")
    COMMANDS["xtestquit"] = CommandEntry(words="do")

    with pytest.raises(SystemExit):
        await process_line("xtestquit do", Context())


# ---------------------------------------------------------------------------
# Idempotent mode must not swallow hard failures
#
# NIOS stamps `Client.Ibap.Data.Conflict` on errors that are not "already
# exists" at all. A 200-member pre-provision against an unlicensed grid
# created nothing yet reported 200 `Skipped:` lines and exit 0, because the
# Conflict code alone was taken as proof of idempotency.
# ---------------------------------------------------------------------------


async def test_idempotent_does_not_skip_licence_conflict(capsys):
    """A Conflict-coded licensing wall is an Error, not a Skip."""
    from ibx_nios_sdk import BadRequestError

    @command("xtestlicence do")
    async def _h(line, ctx):
        raise BadRequestError(
            message="AdmConDataError",
            wapi_code="Client.Ibap.Data.Conflict",
            wapi_text=(
                "The master does not have a valid Grid license installed "
                "for the member 10.64.50.223."
            ),
        )

    _seed("xtestlicence", "do")

    await process_line("xtestlicence do", Context(idempotent=True))
    out = capsys.readouterr().out
    assert "Error:" in out
    assert "Skipped:" not in out
    assert "valid Grid license" in out


async def test_idempotent_still_skips_real_exists_conflict(capsys):
    """The behaviour -i exists for must keep working."""
    from ibx_nios_sdk import BadRequestError

    @command("xtestexists do")
    async def _h(line, ctx):
        raise BadRequestError(
            message="AdmConDataError",
            wapi_code="Client.Ibap.Data.Conflict",
            wapi_text="The record 'host1.example.com' already exists.",
        )

    _seed("xtestexists", "do")

    await process_line("xtestexists do", Context(idempotent=True))
    out = capsys.readouterr().out
    assert "Skipped:" in out
    assert "Error:" not in out


async def test_http_409_is_still_treated_as_exists(capsys):
    """A real 409 carries conflict semantics in the status code itself."""
    from ibx_nios_sdk import ConflictError as _Conflict

    @command("xtest409 do")
    async def _h(line, ctx):
        raise _Conflict(message="conflict", wapi_text="object in use")

    _seed("xtest409", "do")

    await process_line("xtest409 do", Context(idempotent=True))
    assert "Skipped:" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Timeout reporting
#
# httpx timeout classes carry an empty str(), so the catch-all rendered them
# as a bare "ReadTimeout: " - technically true, useless in practice. Found by
# `show threat_protection statistics`, which takes 30.15s on a populated grid
# against the SDK's 30s default.
# ---------------------------------------------------------------------------


async def test_timeout_error_names_the_limit_and_the_remedy(capsys):
    import httpx

    @command("xtesttimeout do")
    async def _h(line, ctx):
        raise httpx.ReadTimeout("")

    _seed("xtesttimeout", "do")

    await process_line("xtesttimeout do", Context(timeout=30.0))
    out = capsys.readouterr().out
    assert "ReadTimeout" in out
    assert "30s" in out
    assert "--timeout" in out


async def test_timeout_message_reflects_the_configured_value(capsys):
    import httpx

    @command("xtesttimeout2 do")
    async def _h(line, ctx):
        raise httpx.ConnectTimeout("")

    _seed("xtesttimeout2", "do")

    await process_line("xtesttimeout2 do", Context(timeout=90.0))
    assert "90s" in capsys.readouterr().out


async def test_exception_with_no_message_renders_as_bare_class_name(capsys):
    """Never print a dangling 'SomeError: ' with nothing after the colon."""

    class _Quiet(RuntimeError):
        pass

    @command("xtestquiet do")
    async def _h(line, ctx):
        raise _Quiet("")

    _seed("xtestquiet", "do")

    await process_line("xtestquiet do", Context())
    out = capsys.readouterr().out.strip()
    assert out.endswith("_Quiet")
    assert not out.endswith(":")


# ---------------------------------------------------------------------------
# SDK model / NIOS response mismatches
#
# `Grid.restart_status` is typed `str | None` in ibx-nios-sdk 0.1.1, but NIOS
# 9.1 returns a struct. Pydantic's own rendering is a multi-line dump ending
# in a docs URL; the operator needs the field name and the fact that it isn't
# their fault.
# ---------------------------------------------------------------------------


async def test_validation_error_is_summarised_to_one_line(capsys):
    from pydantic import BaseModel

    class _Grid(BaseModel):
        restart_status: str | None = None

    @command("xtestvalid do")
    async def _h(line, ctx):
        _Grid(restart_status={"_ref": "grid:servicerestart", "failures": 0})

    _seed("xtestvalid", "do")

    await process_line("xtestvalid do", Context())
    out = capsys.readouterr().out
    assert "restart_status" in out
    assert "ibx-nios-sdk" in out
    # The pydantic docs URL and multi-line dump must not reach the operator.
    assert "errors.pydantic.dev" not in out
    assert len(out.strip().splitlines()) == 1


async def test_non_validation_errors_are_unaffected(capsys):
    @command("xtestplain do")
    async def _h(line, ctx):
        raise RuntimeError("something specific")

    _seed("xtestplain", "do")

    await process_line("xtestplain do", Context())
    out = capsys.readouterr().out
    assert "something specific" in out
    assert "ibx-nios-sdk" not in out


# ---------------------------------------------------------------------------
# WAPI per-object-type operation restrictions (ibx-nios-sdk >= 0.2.0)
#
# NIOS forbids read/create/update/delete on certain object types and the SDK
# now refuses those locally. Its message names a library argument, which a
# CLI operator cannot act on.
# ---------------------------------------------------------------------------


async def test_unsupported_operation_points_at_the_cli_flag(capsys):
    from ibx_nios_sdk import UnsupportedOperationError

    @command("xtestrestricted do")
    async def _h(line, ctx):
        raise UnsupportedOperationError(wapi_type="dtc", operation="read")

    _seed("xtestrestricted", "do")

    await process_line("xtestrestricted do", Context())
    out = capsys.readouterr().out
    assert "does not support read" in out
    assert "--allow-restricted" in out
    # The library-level phrasing must not reach the operator.
    assert "NiosClient" not in out


async def test_unsupported_operation_is_not_demoted_by_idempotent_mode(capsys):
    """`-i` is for 'already exists', not for 'this can never work'."""
    from ibx_nios_sdk import UnsupportedOperationError

    @command("xtestrestricted2 do")
    async def _h(line, ctx):
        raise UnsupportedOperationError(wapi_type="dtc", operation="read")

    _seed("xtestrestricted2", "do")

    await process_line("xtestrestricted2 do", Context(idempotent=True))
    out = capsys.readouterr().out
    assert "Error:" in out
    assert "Skipped:" not in out
